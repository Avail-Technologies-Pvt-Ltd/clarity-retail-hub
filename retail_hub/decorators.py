from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_validator(allowed_roles):
    """
    Custom permission and role validator matching the pattern in the old LAN system.
    Validates that the logged-in user possesses one of the allowed roles,
    granting full pass-through to superusers.
    
    If unauthorized:
      - Returns JSON error for AJAX requests
      - Redirects to workspaces or raises PermissionDenied for HTML requests
    """
    def decorator(fn):
        @wraps(fn)
        @login_required(login_url='user_login')
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({
                        'custome_status': "Error",
                        'error_type': "Authentication",
                        'message': "Authentication required. Please log in."
                    }, status=401)
                return redirect('user_login')

            # Superusers always pass
            if user.is_superuser:
                return fn(request, *args, **kwargs)

            # Determine user roles from hub profile and tenant membership
            user_roles = set()
            
            # Hub Profile (Tenant schema user)
            profile = getattr(user, 'hub_profile', None)
            if profile and profile.role:
                user_roles.add(profile.role)

            # Tenant Membership (Shared public schema mapping for multi-tenant users)
            tenant = getattr(request, 'tenant', None)
            if tenant and getattr(tenant, 'schema_name', None) != 'public':
                try:
                    from tenants.models import TenantMembership
                    membership = TenantMembership.objects.filter(
                        user=user,
                        company=tenant,
                        is_active=True
                    ).first()
                    if membership and membership.role:
                        user_roles.add(membership.role)
                except Exception:
                    pass

            # If user has roles property or list attached
            roles_attr = getattr(user, 'roles', None)
            if roles_attr:
                if isinstance(roles_attr, (list, tuple, set)):
                    user_roles.update(roles_attr)
                elif isinstance(roles_attr, str):
                    user_roles.add(roles_attr)

            # Check matching role
            is_allowed = any(role in user_roles for role in allowed_roles)

            if not is_allowed:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.method == 'POST':
                    return JsonResponse({
                        'status': 'error',
                        'type': 'error',
                        'title': 'Access Restricted',
                        'message': 'You do not have permission to perform this action. Contact your administrator for access.',
                        'error_code': 'PERMISSION_DENIED',
                        'required_roles': allowed_roles,
                        # Backward-compatibility with legacy LAN handlers
                        'custome_status': 'Error',
                        'error_type': 'Authorisation',
                    }, status=403)
                
                # For GET views, redirect to referer or workspaces with access message
                referer = request.META.get('HTTP_REFERER')
                if referer and referer != request.build_absolute_uri():
                    return redirect(referer)
                return redirect('workspaces_list')

            return fn(request, *args, **kwargs)
        return wrapper
    return decorator


def company_manager_required(fn):
    """Restricts view to Executive Company Managers and Superusers."""
    return role_validator(['COMPANY_MANAGER'])(fn)


def branch_manager_required(fn):
    """Restricts view to Store Leads, Company Managers, and Superusers."""
    return role_validator(['COMPANY_MANAGER', 'BRANCH_MANAGER'])(fn)


def supervisor_required(fn):
    """Restricts view to Supervisors, Branch Managers, Company Managers, and Superusers."""
    return role_validator(['COMPANY_MANAGER', 'BRANCH_MANAGER', 'SUPERVISOR'])(fn)


def staff_required(fn):
    """Allows all active staff tiers and above."""
    return role_validator(['COMPANY_MANAGER', 'BRANCH_MANAGER', 'SUPERVISOR', 'STAFF'])(fn)
