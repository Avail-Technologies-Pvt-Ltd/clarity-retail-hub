from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from .models import Branch, PendingApproval, InterBranchTransferBuffer
from retail_hub.decorators import staff_required, branch_manager_required, company_manager_required


def _ok(title, message, **extra):
    return JsonResponse({'type': 'success', 'title': title, 'message': message, **extra})

def _err(title, message, status=400):
    return JsonResponse({'type': 'error', 'title': title, 'message': message}, status=status)

def _warn(title, message, status=400):
    return JsonResponse({'type': 'warning', 'title': title, 'message': message}, status=status)


@staff_required
def branches_page(request):
    """
    Tenant branch directory and edge sync monitoring dashboard.
    """
    branches = Branch.objects.all().order_by('branch_code')
    active_count = branches.filter(status='ACTIVE').count()
    main_branch = branches.filter(is_main_branch=True).first()
    
    # If no main branch has been designated yet, default the first active branch or HQ
    if not main_branch and branches.exists():
        candidate = branches.filter(is_headquarters=True).first() or branches.first()
        if candidate:
            candidate.is_main_branch = True
            candidate.save(update_fields=['is_main_branch'])
            main_branch = candidate

    from django.db.models import Max
    max_version = branches.aggregate(max_v=Max('version'))['max_v'] or 1

    context = {
        'branches': branches.select_related('directory_sync_state'),
        'total_count': branches.count(),
        'active_count': active_count,
        'main_branch': main_branch,
        'max_version': max_version,
        'tenant_name': getattr(request.tenant, 'name', 'Retail Workspace'),
    }
    return render(request, 'branches/branches_list.html', context)


@require_POST
@branch_manager_required
def branch_create(request):
    """
    Add a new branch store to the current tenant company.
    Accepts LAN auto-generated branch key and optional main branch designation.
    """
    name = (request.POST.get('name') or '').strip()
    branch_code = (request.POST.get('branch_code') or '').strip().upper()
    manager_name = (request.POST.get('manager_name') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    email = (request.POST.get('email') or '').strip()
    address = (request.POST.get('address') or '').strip()
    lan_key = (request.POST.get('lan_branch_key') or '').strip()
    is_hq = request.POST.get('is_headquarters') in ['on', 'true', '1']
    is_main = request.POST.get('is_main_branch') in ['on', 'true', '1']

    if not name or not branch_code:
        return _err('Validation Error', 'Store name and unique branch code are required.')

    if Branch.objects.filter(branch_code=branch_code).exists():
        return _warn('Duplicate Code', f"A store with branch code '{branch_code}' already exists in your workspace.")

    # If first branch ever created, make it main by default
    if not Branch.objects.exists():
        is_main = True

    try:
        branch = Branch(
            name=name,
            branch_code=branch_code,
            manager_name=manager_name,
            phone=phone,
            email=email,
            address=address,
            lan_branch_key=lan_key or None,
            is_headquarters=is_hq,
            is_main_branch=is_main,
            status='ACTIVE'
        )
        branch.save()
        return _ok(
            'Branch Registered',
            f"Store '{branch.name}' [{branch.branch_code}] created successfully.",
            branch_id=str(branch.id),
            sync_token=branch.sync_token,
            is_main=branch.is_main_branch
        )
    except Exception as e:
        return _err('Creation Error', f"Failed to register branch: {str(e)}", status=500)


@require_POST
@branch_manager_required
def branch_update(request, branch_id):
    """
    Update an existing branch's details, manager, banking info, or headquarters status.
    """
    branch = get_object_or_404(Branch, id=branch_id)
    name = (request.POST.get('name') or '').strip()
    manager_name = (request.POST.get('manager_name') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    email = (request.POST.get('email') or '').strip()
    address = (request.POST.get('address') or '').strip()
    bank_name = (request.POST.get('bank_name') or '').strip()
    bank_account_number = (request.POST.get('bank_account_number') or '').strip()
    is_hq = request.POST.get('is_headquarters') in ['on', 'true', '1']

    if not name:
        return _err('Validation Error', 'Store name cannot be empty.')

    branch.name = name
    branch.manager_name = manager_name
    branch.phone = phone
    branch.email = email
    branch.address = address
    branch.bank_name = bank_name
    branch.bank_account_number = bank_account_number
    branch.is_headquarters = is_hq
    branch.save()

    return _ok(
        'Store Updated',
        f"Details for store '{branch.name}' [{branch.branch_code}] updated successfully."
    )


@require_POST
@company_manager_required
def ajax_set_main_branch(request, branch_id):
    """
    Designates the single authoritative Main Branch for resolving UUID conflicts.
    Automatically unsets any previously designated main branch.
    """
    branch = get_object_or_404(Branch, id=branch_id)
    if branch.is_main_branch:
        return _ok('Already Main', f"'{branch.name}' is already designated as the Main Branch.")

    branch.is_main_branch = True
    branch.save()  # Branch.save() automatically unsets all other main branches

    return _ok(
        'Main Branch Updated',
        f"'{branch.name}' [{branch.branch_code}] is now the primary source-of-truth for catalog conflicts."
    )


@require_POST
@branch_manager_required
def branch_toggle_status(request, branch_id):
    """
    Toggles branch status between ACTIVE and SUSPENDED.
    """
    branch = get_object_or_404(Branch, id=branch_id)
    if branch.is_main_branch and branch.status == 'ACTIVE':
        return _warn(
            'Cannot Suspend Main Branch',
            'You cannot suspend the primary Main Branch. Please designate another Main Branch first.'
        )

    branch.status = 'SUSPENDED' if branch.status == 'ACTIVE' else 'ACTIVE'
    branch.save(update_fields=['status'])
    
    return _ok(
        'Status Changed',
        f"Store '{branch.name}' is now {branch.status}.",
        new_status=branch.status
    )


@require_POST
@branch_manager_required
def branch_token_regenerate(request, branch_id):
    """
    Regenerate edge node sync token for security or re-installation.
    """
    branch = get_object_or_404(Branch, id=branch_id)
    new_token = branch.refresh_sync_token()
    # Reset hardware pairing so newly paired terminal can register cleanly
    branch.hardware_fingerprint = None
    branch.pairing_status = 'UNPAIRED'
    branch.save(update_fields=['hardware_fingerprint', 'pairing_status'])

    return _ok(
        'Token Regenerated',
        f"New sync token generated for {branch.name}. Hardware lock reset for re-pairing.",
        sync_token=new_token
    )


@require_POST
@branch_manager_required
def branch_lock_toggle(request, branch_id):
    """
    Admin control to unlock hardware binding or revoke branch key.
    """
    branch = get_object_or_404(Branch, id=branch_id)
    action = request.POST.get('action', 'unlock')

    if action == 'unlock':
        branch.hardware_fingerprint = None
        branch.pairing_status = 'UNPAIRED'
        branch.save(update_fields=['hardware_fingerprint', 'pairing_status'])
        return _ok('Hardware Unlocked', f"Branch key for '{branch.name}' is now unlocked for new hardware pairing.")
    elif action == 'revoke':
        branch.pairing_status = 'REVOKED'
        branch.save(update_fields=['pairing_status'])
        return _ok('Key Revoked', f"Sync access for '{branch.name}' has been revoked.")

    return _err('Invalid Action', 'Unknown lock action.')


@staff_required
def transfers_buffer_view(request):
    """
    Cloud buffer relay viewer for inter-branch stock transfers.
    Displays all in-transit items and historical restock events.
    """
    tenant = getattr(request, 'tenant', None)
    transfers = InterBranchTransferBuffer.objects.all().select_related('source_branch', 'destination_branch')
    
    # Filter by branch if active_branch_id is in session or query
    active_branch_id = request.session.get('active_branch_id')
    if active_branch_id:
        transfers = transfers.filter(
            Q(source_branch_id=active_branch_id) | Q(destination_branch_id=active_branch_id)
        )

    context = {
        'page_title': 'Inter-Branch Stock Transfer Buffer',
        'tenant': tenant,
        'tenant_name': getattr(request.tenant, 'name', 'Retail Workspace'),
        'transfers': transfers[:50],
        'in_transit_count': transfers.filter(status='IN_TRANSIT').count(),
        'received_count': transfers.filter(status='RECEIVED').count(),
    }
    return render(request, 'branches/transfers_buffer.html', context)


@staff_required
def approvals_list(request):
    """
    Supervisor Approval Queue view for edge transactions.
    """
    tenant = getattr(request, 'tenant', None)
    approvals = PendingApproval.objects.all().select_related('branch')

    context = {
        'page_title': 'Supervisor Approvals Queue',
        'tenant': tenant,
        'approvals': approvals[:50],
        'pending_count': approvals.filter(status='PENDING').count(),
    }
    return render(request, 'branches/approvals_list.html', context)


@require_POST
@branch_manager_required
def ajax_review_approval(request, approval_id):
    """
    Review and approve or reject a pending edge transaction.
    """
    approval = get_object_or_404(PendingApproval, id=approval_id)
    decision = request.POST.get('decision', 'APPROVED')
    notes = (request.POST.get('notes') or '').strip()

    if decision not in ['APPROVED', 'REJECTED']:
        return _err('Invalid Decision', 'Decision must be APPROVED or REJECTED.')

    approval.status = decision
    approval.reviewed_by = request.user.get_full_name() or request.user.username
    approval.reviewed_at = timezone.now()
    approval.review_notes = notes
    approval.save()

    return _ok(
        f"Transaction {decision.capitalize()}",
        f"Approval #{approval.reference} has been marked as {decision}."
    )
