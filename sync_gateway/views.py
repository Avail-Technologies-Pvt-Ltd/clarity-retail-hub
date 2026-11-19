from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q
from branches.models import Branch, InterBranchTransferBuffer
from subscriptions.models import CompanySubscription
from .models import SyncLog, ProcessedEvent
from retail_hub.decorators import staff_required
import json


def _authenticate_branch(request):
    """
    Extract and authenticate branch sync token from request headers or auth payload.
    Supports either the generated 48-char sync_token or the memorable lan_branch_key.
    """
    token = request.headers.get('X-Branch-Token') or request.META.get('HTTP_X_BRANCH_TOKEN')
    if not token and request.method == 'POST':
        try:
            body = json.loads(request.body)
            token = body.get('sync_token') or body.get('branch_key')
        except Exception:
            token = None
    if not token:
        return None
    token = str(token).strip()
    return Branch.objects.filter(Q(sync_token=token) | Q(lan_branch_key=token), status='ACTIVE').first()


def _get_hardware_fingerprint(request, body_dict=None):
    """Extracts hardware fingerprint from header or request body."""
    fp = request.headers.get('X-Hardware-Fingerprint') or request.META.get('HTTP_X_HARDWARE_FINGERPRINT')
    if not fp and body_dict:
        fp = body_dict.get('hardware_fingerprint')
    return (fp or '').strip() or None


@csrf_exempt
@require_POST
def sync_ping(request):
    """
    Heartbeat ping endpoint for Clarity Retail LAN nodes.
    Endpoint: POST /sync/ping/
    Headers: X-Branch-Token: <token>, X-Hardware-Fingerprint: <hash>
    """
    branch = _authenticate_branch(request)
    if not branch:
        return JsonResponse({
            'status': 'error',
            'message': 'Unauthorized. Invalid or missing branch sync token.'
        }, status=401)

    now = timezone.now()
    body_data = {}
    try:
        body_data = json.loads(request.body) if request.body else {}
    except Exception:
        pass

    # 1. Anti-Theft Hardware Signature Verification
    hw_fp = _get_hardware_fingerprint(request, body_data)
    if branch.pairing_status == 'PAIRED_LOCKED' and branch.hardware_fingerprint:
        if hw_fp and hw_fp != branch.hardware_fingerprint:
            return JsonResponse({
                'status': 'error',
                'approval': 'REJECTED',
                'message': 'Hardware signature mismatch. This branch key is locked to another physical terminal.'
            }, status=403)
    elif hw_fp and branch.pairing_status == 'UNPAIRED':
        # Lock to the first connecting machine
        branch.hardware_fingerprint = hw_fp
        branch.pairing_status = 'PAIRED_LOCKED'
        branch.paired_at = now
        # Capture IP
        branch.paired_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        branch.save(update_fields=['hardware_fingerprint', 'pairing_status', 'paired_at', 'paired_ip'])

    # 2. Update edge version & last ping
    branch.last_ping_at = now
    if body_data.get('version'):
        branch.edge_version = body_data.get('version')
    branch.save(update_fields=['last_ping_at', 'edge_version'])

    # 3. Licensing & 60-Day Grace Period Verification
    tenant = getattr(request, 'tenant', None)
    sub = CompanySubscription.objects.filter(company=tenant).first() if tenant else None
    
    is_approved = True
    days_left = 60
    sub_status = 'TRIAL'

    if sub:
        days_left = sub.days_remaining
        sub_status = sub.status
        is_approved = sub.is_valid or (sub.days_remaining > 0)
    elif tenant:
        # Default 60 days grace from tenant registration
        delta = (now.date() - tenant.created_on.date()).days
        days_left = max(0, 60 - delta)
        is_approved = (days_left > 0)

    # 4. Count pending inter-branch transfers waiting in buffer for this branch
    pending_transfers_count = InterBranchTransferBuffer.objects.filter(
        destination_branch=branch,
        status='IN_TRANSIT'
    ).count()

    return JsonResponse({
        'status': 'success',
        'approval': 'APPROVED' if is_approved else 'EXPIRED',
        'sub_status': sub_status,
        'grace_days_remaining': days_left,
        'message': f'Heartbeat acknowledged for {branch.name}',
        'server_time': now.isoformat(),
        'branch_code': branch.branch_code,
        'is_main_branch': branch.is_main_branch,
        'pairing_status': branch.pairing_status,
        'pending_transfers_count': pending_transfers_count,
    })


@csrf_exempt
@require_POST
def sync_push(request):
    """
    Ingestion endpoint for Retail LAN outbox sync events.
    Enforces Main Branch conflict priority and buffers inter-branch stock transfers.
    Endpoint: POST /sync/push/
    """
    branch = _authenticate_branch(request)
    if not branch:
        return JsonResponse({
            'status': 'error',
            'message': 'Unauthorized. Invalid or missing branch sync token.'
        }, status=401)

    try:
        body = json.loads(request.body)
        events = body.get('events', [])
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Invalid JSON payload: {str(e)}'
        }, status=400)

    now = timezone.now()
    accepted = []
    skipped = []

    # Find the designated Main Branch in this tenant schema
    main_branch = Branch.objects.filter(is_main_branch=True).first()
    is_sending_main = branch.is_main_branch or (main_branch and main_branch.id == branch.id)

    for ev in events:
        gid = ev.get('global_id')
        entity_type = ev.get('entity_type', 'Entity')
        payload = ev.get('data', {})
        if not gid:
            continue

        # Handle Inter-Branch Stock Transfers (Buffer Queue)
        if entity_type == 'InterBranchTransfer':
            from decimal import Decimal
            ref = payload.get('reference') or f"TR-{gid[:8]}"
            action = payload.get('action', 'DISPATCH')
            dest_code = payload.get('destination_branch_code', '')
            dest_branch = Branch.objects.filter(branch_code=dest_code).first()
            if not dest_branch and payload.get('destination_branch_id'):
                dest_branch = Branch.objects.filter(id=payload.get('destination_branch_id')).first()
            if not dest_branch and payload.get('destination_branch_name'):
                dest_branch = Branch.objects.filter(name__iexact=payload.get('destination_branch_name')).first()

            if action == 'DISPATCH' and dest_branch:
                InterBranchTransferBuffer.objects.update_or_create(
                    reference=ref,
                    defaults={
                        'source_branch': branch,
                        'destination_branch': dest_branch,
                        'product_uuid': payload.get('product_uuid', gid),
                        'product_name': payload.get('product_name', 'Stock Item'),
                        'batch_number': payload.get('batch_number'),
                        'expiry_date': payload.get('expiry_date'),
                        'cost_price': Decimal(str(payload.get('cost_price', 0.0) or 0.0)),
                        'selling_price': Decimal(str(payload.get('selling_price', 0.0) or 0.0)),
                        'quantity': Decimal(str(payload.get('quantity', 1.0))),
                        'status': 'IN_TRANSIT',
                        'notes': payload.get('notes', ''),
                        'dispatched_by': payload.get('dispatched_by', branch.manager_name or 'Store Dispatcher'),
                    }
                )
            elif action == 'RECEIVE':
                transfer = InterBranchTransferBuffer.objects.filter(reference=ref).first()
                if transfer:
                    # Concurrency Lock: Check that transfer is still in transit
                    if transfer.status == 'CANCELLED':
                        errors.append({'global_id': gid, 'error': 'TRANSFER_RECALLED', 'message': f'Transfer #{ref} was recalled/cancelled by {transfer.source_branch.name}.'})
                        continue
                    if transfer.status in ['RECEIVED', 'PARTIAL_RECEIPT']:
                        errors.append({'global_id': gid, 'error': 'ALREADY_RECEIVED', 'message': f'Transfer #{ref} has already been received.'})
                        continue

                    received_qty = payload.get('qty_received')
                    if received_qty is not None:
                        transfer.qty_received = Decimal(str(received_qty))
                        if transfer.qty_received < transfer.quantity:
                            transfer.status = 'PARTIAL_RECEIPT'
                        else:
                            transfer.status = 'RECEIVED'
                    else:
                        transfer.qty_received = transfer.quantity
                        transfer.status = 'RECEIVED'

                    transfer.discrepancy_reason = payload.get('discrepancy_reason', '')
                    transfer.received_at = now
                    transfer.received_by = payload.get('received_by', branch.manager_name or 'Store Receiver')
                    transfer.save(update_fields=['status', 'qty_received', 'discrepancy_reason', 'received_at', 'received_by'])

            elif action == 'CANCEL':
                transfer = InterBranchTransferBuffer.objects.filter(reference=ref).first()
                if transfer:
                    # Concurrency Lock: Cannot cancel if already received by destination!
                    if transfer.status in ['RECEIVED', 'PARTIAL_RECEIPT']:
                        errors.append({'global_id': gid, 'error': 'ALREADY_RECEIVED', 'message': f'Cannot recall: Transfer #{ref} has already been accepted and restocked by {transfer.destination_branch.name}.'})
                        continue

                    transfer.status = 'CANCELLED'
                    transfer.discrepancy_reason = payload.get('reason', payload.get('discrepancy_reason', 'Recalled and cancelled by source branch'))
                    transfer.received_at = now
                    transfer.received_by = payload.get('cancelled_by', branch.manager_name or 'Store Dispatcher')
                    transfer.save(update_fields=['status', 'discrepancy_reason', 'received_at', 'received_by'])

            elif action == 'REJECT':
                transfer = InterBranchTransferBuffer.objects.filter(reference=ref).first()
                if transfer:
                    transfer.status = 'REJECTED'
                    transfer.discrepancy_reason = payload.get('discrepancy_reason', payload.get('notes', 'Rejected by receiver'))
                    transfer.received_at = now
                    transfer.received_by = payload.get('received_by', branch.manager_name or 'Store Receiver')
                    transfer.save(update_fields=['status', 'discrepancy_reason', 'received_at', 'received_by'])

            accepted.append(gid)
            continue

        # Handle Daily Operational Summary (Source of Truth for Daily, Weekly, Monthly, Annual Reports)
        if entity_type == 'DailySummary':
            from decimal import Decimal
            from reports.models import DailyBranchSummary
            summary_date_str = payload.get('date') or payload.get('summary_date')
            if summary_date_str:
                try:
                    from datetime import datetime as dt
                    sum_date = dt.strptime(str(summary_date_str)[:10], '%Y-%m-%d').date()
                    DailyBranchSummary.objects.update_or_create(
                        branch=branch,
                        summary_date=sum_date,
                        defaults={
                            'sales_count': int(payload.get('sales_count', 0)),
                            'gross_sales': Decimal(str(payload.get('gross_sales', 0.0))),
                            'vat_amount': Decimal(str(payload.get('vat_amount', 0.0))),
                            'net_sales': Decimal(str(payload.get('net_sales', 0.0))),
                            'expenses_total': Decimal(str(payload.get('expenses_total', 0.0))),
                            'net_cashflow': Decimal(str(payload.get('net_cashflow', 0.0))),
                            'fiscalised_count': int(payload.get('fiscalised_count', 0)),
                            'tender_breakdown': payload.get('tender_breakdown', {}),
                            'cashier_breakdown': payload.get('cashier_breakdown', []),
                        }
                    )
                    accepted.append(gid)
                    continue
                except Exception:
                    pass

        # MAIN BRANCH CONFLICT RULE FOR PRODUCT ATTRIBUTES:
        # If sending branch is NOT main, and a product event for this global_id already exists from the Main Branch,
        # we do NOT allow the non-main branch to overwrite product name, barcode, or category.
        if entity_type == 'Product' and not is_sending_main:
            main_product_event = ProcessedEvent.objects.filter(
                entity_type='Product',
                global_id=gid,
                branch__is_main_branch=True
            ).first()

            if main_product_event and main_product_event.payload_data:
                # Retain authoritative master attributes from Main Branch
                auth_data = main_product_event.payload_data
                payload['name'] = auth_data.get('name', payload.get('name'))
                payload['barcode'] = auth_data.get('barcode', payload.get('barcode'))
                payload['category'] = auth_data.get('category', payload.get('category'))
                payload['oem_number'] = auth_data.get('oem_number', payload.get('oem_number'))

        # Idempotency check: exactly-once processing per branch
        if ProcessedEvent.objects.filter(global_id=gid, branch=branch).exists():
            skipped.append(gid)
            continue

        # Ingest event into tenant schema
        ProcessedEvent.objects.create(
            global_id=gid,
            entity_type=entity_type,
            branch=branch,
            payload_data=payload
        )
        accepted.append(gid)

    branch.last_sync_at = now
    branch.last_ping_at = now
    branch.save(update_fields=['last_sync_at', 'last_ping_at'])

    # Record sync log
    SyncLog.objects.create(
        branch=branch,
        direction='PUSH',
        payload_type='OUTBOX_BATCH',
        records_count=len(events),
        status='SUCCESS' if not skipped or accepted else 'WARNING',
        error_message=f"Processed: {len(accepted)}, Skipped (already synced): {len(skipped)}"
    )

    return JsonResponse({
        'status': 'success',
        'message': f'Sync batch accepted: {len(accepted)} processed, {len(skipped)} deduplicated.',
        'accepted_count': len(accepted),
        'skipped_count': len(skipped),
        'acknowledged_ids': accepted + skipped,
        'server_time': now.isoformat()
    })


@csrf_exempt
@require_GET
def sync_branches_pull(request):
    """
    Endpoint for edge branch LANs to pull authoritative company branch directory.
    Tracks which version was received by each branch in BranchDirectorySyncState.
    """
    branch = _authenticate_branch(request)
    if not branch:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized.'}, status=401)

    since_version = int(request.GET.get('since_version', 0) or 0)
    
    from django.db.models import Max
    max_version = Branch.objects.aggregate(max_v=Max('version'))['max_v'] or 1

    # Fetch branches in tenant
    branches_qs = Branch.objects.all().order_by('branch_code')
    if since_version > 0:
        branches_qs = branches_qs.filter(version__gt=since_version)

    branches_data = []
    for b in branches_qs:
        branches_data.append({
            'id': str(b.id),
            'branch_code': b.branch_code,
            'name': b.name,
            'address': b.address or '',
            'phone': b.phone or '',
            'email': b.email or '',
            'manager_name': b.manager_name or '',
            'is_main_branch': b.is_main_branch,
            'status': b.status,
            'version': b.version,
            'is_self': (b.id == branch.id),
        })

    # Update Directory Sync State for this subscriber branch
    from branches.models import BranchDirectorySyncState
    BranchDirectorySyncState.objects.update_or_create(
        subscriber_branch=branch,
        defaults={
            'last_synced_version': max_version,
            'last_synced_at': timezone.now()
        }
    )

    return JsonResponse({
        'status': 'success',
        'current_version': max_version,
        'subscriber_branch_code': branch.branch_code,
        'count': len(branches_data),
        'branches': branches_data,
    })


@csrf_exempt
@require_GET
def sync_pending_transfers(request):
    """
    Endpoint for edge branch LANs to pull pending incoming stock transfers.
    Returns all buffered transfers where destination_branch == calling branch and status == 'IN_TRANSIT'.
    """
    branch = _authenticate_branch(request)
    if not branch:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized.'}, status=401)

    pending = InterBranchTransferBuffer.objects.filter(
        destination_branch=branch,
        status='IN_TRANSIT'
    ).order_by('dispatched_at')

    transfers_data = []
    for t in pending:
        transfers_data.append({
            'transfer_uuid': str(t.transfer_uuid),
            'reference': t.reference,
            'source_branch_code': t.source_branch.branch_code,
            'source_branch_name': t.source_branch.name,
            'product_uuid': t.product_uuid,
            'product_name': t.product_name,
            'batch_number': t.batch_number,
            'expiry_date': t.expiry_date.isoformat() if t.expiry_date else None,
            'cost_price': float(t.cost_price),
            'selling_price': float(t.selling_price),
            'quantity': float(t.quantity),
            'notes': t.notes,
            'dispatched_by': t.dispatched_by,
            'dispatched_at': t.dispatched_at.isoformat(),
        })

    return JsonResponse({
        'status': 'success',
        'branch_code': branch.branch_code,
        'count': len(transfers_data),
        'transfers': transfers_data,
    })


@csrf_exempt
@require_GET
def sync_outgoing_transfers_status(request):
    """
    Endpoint for edge branch LANs to check the status of outgoing transfers dispatched by this branch.
    Returns status updates (e.g. RECEIVED, PARTIAL_RECEIPT, REJECTED) so source branch can update its local records
    and emit arrival notifications to dispatchers.
    """
    branch = _authenticate_branch(request)
    if not branch:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized.'}, status=401)

    since_str = request.GET.get('since')
    from django.db.models import Q
    transfers_qs = InterBranchTransferBuffer.objects.filter(
        Q(source_branch=branch) | Q(destination_branch=branch, status='CANCELLED')
    ).exclude(status='IN_TRANSIT').order_by('-received_at')

    if since_str:
        try:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(since_str)
            if dt:
                transfers_qs = transfers_qs.filter(received_at__gte=dt)
        except Exception:
            pass

    status_data = []
    for t in transfers_qs[:50]:
        status_data.append({
            'reference': t.reference,
            'status': t.status,
            'destination_branch_code': t.destination_branch.branch_code,
            'destination_branch_name': t.destination_branch.name,
            'product_uuid': t.product_uuid,
            'product_name': t.product_name,
            'batch_number': t.batch_number,
            'quantity': float(t.quantity),
            'qty_received': float(t.qty_received) if t.qty_received is not None else float(t.quantity),
            'discrepancy_reason': t.discrepancy_reason or '',
            'received_by': t.received_by or 'Store Staff',
            'received_at': t.received_at.isoformat() if t.received_at else None,
        })

    return JsonResponse({
        'status': 'success',
        'branch_code': branch.branch_code,
        'count': len(status_data),
        'transfers': status_data,
    })


@csrf_exempt
@require_GET
def sync_catalog_pull(request):
    """
    Endpoint for edge branch LANs to pull authoritative catalog updates from the Main Branch.
    Returns products created or approved by the Main Branch.
    """
    branch = _authenticate_branch(request)
    if not branch:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized.'}, status=401)

    main_branch = Branch.objects.filter(is_main_branch=True).first()
    if not main_branch:
        return JsonResponse({'status': 'success', 'count': 0, 'products': []})

    product_events = ProcessedEvent.objects.filter(
        branch=main_branch,
        entity_type='Product'
    ).order_by('-processed_at')

    products_data = []
    seen_gids = set()
    for ev in product_events:
        if ev.global_id in seen_gids:
            continue
        seen_gids.add(ev.global_id)
        p = ev.payload_data or {}
        products_data.append({
            'global_id': ev.global_id,
            'name': p.get('name', ''),
            'barcode': p.get('barcode', ''),
            'category': p.get('category', ''),
            'selling_price': float(p.get('selling_price', 0.0) or 0.0),
            'cost_price': float(p.get('cost_price', 0.0) or 0.0),
            'status': p.get('status', True),
        })

    return JsonResponse({
        'status': 'success',
        'main_branch_code': main_branch.branch_code,
        'count': len(products_data),
        'products': products_data
    })


@require_GET
@staff_required
def sync_status_dashboard(request):
    """
    Tenant UI view: sync monitor showing edge branches and recent ingestion logs.
    """
    branches = Branch.objects.all().order_by('branch_code')
    recent_logs = SyncLog.objects.all()[:25]
    context = {
        'branches': branches,
        'recent_logs': recent_logs,
        'tenant_name': getattr(request.tenant, 'name', 'Retail Workspace'),
    }
    return render(request, 'sync_gateway/sync_status.html', context)
