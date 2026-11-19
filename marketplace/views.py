import uuid
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from .models import MarketplaceProfile, StockRequest
from retail_hub.decorators import staff_required, branch_manager_required


def _ok(title, message, **extra):
    return JsonResponse({'type': 'success', 'title': title, 'message': message, **extra})

def _err(title, message, status=400):
    return JsonResponse({'type': 'error', 'title': title, 'message': message}, status=status)


@staff_required
def marketplace_home(request):
    """
    B2B Exchange & Marketplace Management for Retailers.
    Manages marketplace opt-in discovery, stock procurement requests, and wholesaler connections.
    """
    tenant = getattr(request, 'tenant', None)
    profile = MarketplaceProfile.get()
    stock_requests = StockRequest.objects.all().order_by('-created_at')

    context = {
        'page_title': 'B2B Marketplace & Exchange',
        'tenant': tenant,
        'profile': profile,
        'stock_requests': stock_requests,
        'open_requests_count': stock_requests.filter(status='OPEN').count(),
        'currency_symbol': getattr(tenant, 'currency_symbol', '$'),
    }
    return render(request, 'marketplace/marketplace_home.html', context)


@branch_manager_required
def ajax_toggle_optin(request):
    """
    Toggles retailer's opt-in status on Clarity Exchange.
    """
    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST requests allowed.', 405)

    profile = MarketplaceProfile.get()
    new_status = not profile.is_opted_in
    profile.is_opted_in = new_status
    if new_status and not profile.date_opted_in:
        profile.date_opted_in = timezone.now()

    # Optional profile fields
    tagline = request.POST.get('company_tagline')
    phone = request.POST.get('contact_phone')
    email = request.POST.get('contact_email')
    if tagline is not None:
        profile.company_tagline = tagline.strip()
    if phone is not None:
        profile.contact_phone = phone.strip()
    if email is not None:
        profile.contact_email = email.strip()

    profile.save()

    status_msg = "Your store is now discoverable by verified wholesalers on Clarity Exchange." if new_status else "Your store is in Private ERP mode. Marketplace participation paused."
    return _ok(
        'Marketplace Status Updated',
        status_msg,
        is_opted_in=profile.is_opted_in
    )


@branch_manager_required
def ajax_create_request(request):
    """
    Creates a new retailer procurement stock request broadcast to wholesalers.
    """
    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST requests allowed.', 405)

    item_name = request.POST.get('item_name', '').strip()
    category = request.POST.get('category', '').strip() or 'General Retail'
    quantity_str = request.POST.get('quantity_needed', '1')
    target_price_str = request.POST.get('target_unit_price', '')
    location = request.POST.get('preferred_location', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not item_name:
        return _err('Validation Error', 'Item name or description is required.')

    try:
        quantity = max(1, int(quantity_str))
    except ValueError:
        quantity = 1

    target_price = None
    if target_price_str:
        try:
            target_price = float(target_price_str)
        except ValueError:
            target_price = None

    req_ref = f"REQ-{uuid.uuid4().hex[:8].upper()}"

    stock_req = StockRequest.objects.create(
        reference=req_ref,
        item_name=item_name,
        category=category,
        quantity_needed=quantity,
        target_unit_price=target_price,
        preferred_location=location,
        notes=notes,
        status='OPEN'
    )

    return _ok(
        'Procurement Request Broadcast',
        f"Stock request #{stock_req.reference} has been posted to Clarity Exchange for wholesaler quotes."
    )


@branch_manager_required
def ajax_cancel_request(request, req_id):
    """Cancels an existing stock request."""
    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST requests allowed.', 405)

    stock_req = get_object_or_404(StockRequest, id=req_id)
    stock_req.status = 'CANCELLED'
    stock_req.save(update_fields=['status', 'updated_at'])

    return _ok('Request Cancelled', f"Procurement request #{stock_req.reference} marked as cancelled.")
