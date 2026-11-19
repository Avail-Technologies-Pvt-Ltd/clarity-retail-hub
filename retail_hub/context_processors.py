from django.conf import settings
from branches.models import Branch
from accounts_hub.models import HubUserProfile


def get_platform_port_str(request=None):
    """
    Central helper function to determine the external host port.
    1. First honors settings.PLATFORM_PORT if configured (single point of truth).
    2. Otherwise checks the incoming request Host header (e.g. localhost:8003).
    3. Strips standard HTTP/HTTPS ports (80/443).
    Returns string like ':8003' or '' if standard.
    """
    configured_port = getattr(settings, 'PLATFORM_PORT', None)
    if configured_port:
        port_int = int(configured_port)
        return f":{port_int}" if port_int not in [80, 443] else ""

    if request:
        host = request.get_host()
        if ':' in host:
            return f":{host.split(':')[1]}"

    return ""


def platform_port_context(request):
    """
    Global template context processor ensuring port_str and central URLs are always available.
    """
    port_str = get_platform_port_str(request)
    platform_domain = getattr(settings, 'PLATFORM_DOMAIN', 'localhost')
    central_url = f"{request.scheme}://{platform_domain}{port_str}"

    return {
        'platform_port_str': port_str,
        'central_url': central_url,
    }


def branch_context(request):
    """
    Context processor providing multi-level branch mode and permission scoping.
    Supports:
      1. Combined Chain Mode (all branches consolidated)
      2. Specific Branch Mode (filtered strictly to one physical store)
      3. Role privilege validation (reading, approving, managing)
    """
    tenant = getattr(request, 'tenant', None)
    if not tenant or getattr(tenant, 'schema_name', '') == 'public':
        return {
            'all_branches': [],
            'active_branch': None,
            'branch_mode': 'COMBINED',
            'can_switch_branches': True,
            'user_role': 'SUPERUSER',
            'can_approve': True,
            'can_read': True,
        }

    try:
        branches = Branch.objects.all().order_by('branch_code')
    except Exception:
        branches = []

    # Check user privileges
    user_role = 'COMPANY_MANAGER'
    can_approve = True
    can_read = True
    assigned_branch = None

    if request.user.is_authenticated:
        profile = getattr(request.user, 'hub_profile', None)
        if profile:
            user_role = profile.role
            can_approve = profile.can_approve or user_role in ['COMPANY_MANAGER', 'BRANCH_MANAGER', 'SUPERVISOR']
            can_read = profile.can_read
            assigned_branch = profile.assigned_branch
        else:
            tenant = getattr(request, 'tenant', None)
            membership = None
            if tenant and getattr(tenant, 'schema_name', None) != 'public':
                try:
                    from tenants.models import TenantMembership
                    membership = TenantMembership.objects.filter(
                        user=request.user,
                        company=tenant,
                        is_active=True
                    ).first()
                except Exception:
                    membership = None

            if membership:
                user_role = membership.role
                can_approve = membership.can_approve or user_role in ['COMPANY_MANAGER', 'BRANCH_MANAGER', 'SUPERVISOR']
                can_read = membership.can_read
            elif request.user.is_superuser:
                user_role = 'COMPANY_MANAGER'
                can_approve = True
                can_read = True

    can_switch_branches = (user_role == 'COMPANY_MANAGER' or request.user.is_superuser)

    # Determine active branch mode
    # URL param ?branch= overrides session
    param_branch = request.GET.get('branch')
    if param_branch:
        if param_branch.upper() in ['ALL', 'COMBINED', '']:
            request.session['active_branch_id'] = None
        else:
            request.session['active_branch_id'] = param_branch

    # If user is pinned to a specific branch and cannot switch
    if not can_switch_branches and assigned_branch:
        active_branch = assigned_branch
        branch_mode = 'SINGLE'
    else:
        active_branch_id = request.session.get('active_branch_id')
        active_branch = None
        if active_branch_id:
            try:
                active_branch = Branch.objects.filter(id=active_branch_id).first()
            except Exception:
                active_branch = None

        branch_mode = 'SINGLE' if active_branch else 'COMBINED'

    return {
        'all_branches': branches,
        'active_branch': active_branch,
        'branch_mode': branch_mode,
        'can_switch_branches': can_switch_branches,
        'user_role': user_role,
        'can_approve': can_approve,
        'can_read': can_read,
    }
