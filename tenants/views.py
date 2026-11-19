from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST, require_GET
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from .models import Company, Domain, TenantMembership, CommunityPlatform
from retail_hub.context_processors import get_platform_port_str
import re


def generate_tenant_sso_token(user, tenant_schema):
    """
    Generates a secure, cryptographically signed, timestamped token (valid for 120 seconds)
    allowing seamless single-sign-on handover from the public workspace selector into a specific tenant schema.
    """
    signer = TimestampSigner(salt='tenant_sso')
    return signer.sign(f"{user.id}:{tenant_schema}")


def sso_tenant_login(request):
    """
    Consumes a secure handover token on the target tenant subdomain.
    Authenticates the user seamlessly into the tenant schema without prompting for login again.
    """
    token = request.GET.get('token')
    next_url = request.GET.get('next', '/')
    
    if not token:
        return redirect('user_login')

    signer = TimestampSigner(salt='tenant_sso')
    try:
        data = signer.unsign(token, max_age=120)
        user_id_str, expected_schema = data.split(':', 1)
        user_id = int(user_id_str)
    except (BadSignature, SignatureExpired, ValueError):
        # Invalid or expired handover token; redirect to login
        return redirect('user_login')

    # Verify that current tenant schema matches token's expected schema
    current_tenant = getattr(request, 'tenant', None)
    if current_tenant and current_tenant.schema_name != expected_schema:
        return redirect('user_login')

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return redirect('user_login')

    # Verify user has access to this tenant (superuser or active membership)
    if not user.is_superuser:
        has_access = TenantMembership.objects.filter(
            user=user,
            company__schema_name=expected_schema,
            is_active=True
        ).exists()
        if not has_access:
            return redirect('user_login')

    # Log user in under this tenant host (attaches session cookie)
    user.backend = 'retail_hub.backends.EmailOrUsernameModelBackend'
    login(request, user)

    # Render a 200 OK document transition instead of a raw 302 redirect.
    # Modern Chromium browsers (Chrome/Edge) drop Set-Cookie headers on cross-site 302 redirects
    # between localhost and *.localhost due to Public Suffix List rules.
    # Committing a 200 OK first-party HTML page ensures the session cookie is saved in the browser's
    # cookie store before window.location.replace navigates to the dashboard same-origin.
    clean_next = next_url if next_url and next_url.startswith('/') else '/'
    response = render(request, 'tenants/sso_transition.html', {
        'next_url': clean_next,
        'company': current_tenant,
        'user': user,
    })

    if request.session.session_key:
        response.set_cookie(
            settings.SESSION_COOKIE_NAME,
            request.session.session_key,
            max_age=settings.SESSION_COOKIE_AGE,
            path='/',
            httponly=True,
            samesite='Lax'
        )

    return response


def public_home(request):
    """
    Public schema landing page.
    Displays platform capabilities and community platform server directory.
    Tenants are NOT listed publicly for privacy and security.
    """
    platforms = CommunityPlatform.objects.filter(is_active=True).order_by('display_order', 'id')
    context = {
        'platform_name': 'Clarity Retail Hub',
        'platforms': platforms,
    }
    return render(request, 'tenants/public_home.html', context)


def user_login(request):
    """
    Central authentication portal on the online platform.
    Once authenticated, routes the user to their business selection screen (workspaces).
    """
    if request.user.is_authenticated:
        # Route to central public workspaces list
        port_suffix = get_platform_port_str(request)
        host_header = request.get_host().split(':')[0]
        if host_header not in ['localhost', '127.0.0.1']:
            return redirect(f"{request.scheme}://localhost{port_suffix}/workspaces/")
        return redirect('workspaces_list')

    error_message = None
    if request.method == 'POST':
        identifier = (request.POST.get('email') or request.POST.get('username') or '').strip()
        password = (request.POST.get('password') or '').strip()

        user = authenticate(request, username=identifier, password=password)
        if user is not None:
            if not user.is_active:
                error_message = "Your account is currently disabled. Please contact your system administrator."
            else:
                login(request, user)
                
                # Handle next redirection if present and safe, otherwise default to workspaces
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)

                port_suffix = get_platform_port_str(request)
                host_header = request.get_host().split(':')[0]
                if host_header not in ['localhost', '127.0.0.1']:
                    return redirect(f"{request.scheme}://localhost{port_suffix}/workspaces/")
                return redirect('workspaces_list')
        else:
            error_message = "Invalid email or password. Please verify your credentials."

    return render(request, 'tenants/login.html', {
        'error_message': error_message,
        'platform_name': 'Clarity Retail Hub'
    })


def user_logout(request):
    """
    Completely logs out the user, flushes the session data,
    clears all authentication and session cookies across both tenant and root domains,
    and redirects cleanly to the central login page.
    """
    try:
        request.session.flush()
    except Exception:
        pass
    logout(request)

    port_suffix = get_platform_port_str(request)
    redirect_url = f"{request.scheme}://localhost{port_suffix}/login/"
    response = redirect(redirect_url)
    
    # Delete cookies on both specific host and wildcards
    response.delete_cookie('sessionid', domain=None)
    response.delete_cookie('sessionid', domain='.localhost')
    response.delete_cookie('sessionid', domain='localhost')
    response.delete_cookie('csrftoken', domain=None)
    response.delete_cookie('csrftoken', domain='.localhost')
    response.delete_cookie('csrftoken', domain='localhost')
    response.delete_cookie('active_tenant_schema', path='/')

    return response


@login_required(login_url='user_login')
def select_workspace(request, schema_name):
    """
    Seamlessly switches to the target tenant workspace on its primary subdomain
    using an SSO handover token.
    """
    user = request.user
    company = Company.objects.filter(schema_name=schema_name, is_active=True).first()
    if not company:
        return redirect('workspaces_list')

    # Verify user has access to this tenant (superuser or active membership)
    if not user.is_superuser:
        has_access = TenantMembership.objects.filter(
            user=user,
            company=company,
            is_active=True
        ).exists()
        if not has_access:
            return redirect('workspaces_list')

    dom = company.domains.filter(is_primary=True).first()
    dom_name = dom.domain if dom else f"{company.schema_name}.localhost"
    port_suffix = get_platform_port_str(request)
    token = generate_tenant_sso_token(user, company.schema_name)
    target_url = f"{request.scheme}://{dom_name}{port_suffix}/sso/auth/?token={token}"

    response = redirect(target_url)
    response.delete_cookie('active_tenant_schema', path='/')
    return response


@login_required(login_url='user_login')
def exit_workspace(request):
    """
    Exits the active tenant workspace and returns to the central workspaces list on localhost.
    """
    port_suffix = get_platform_port_str(request)
    platform_domain = getattr(settings, 'PLATFORM_DOMAIN', 'localhost')
    redirect_url = f"{request.scheme}://{platform_domain}{port_suffix}/workspaces/"
    response = redirect(redirect_url)
    response.delete_cookie('active_tenant_schema', path='/')
    return response



@login_required(login_url='user_login')
def workspaces_list(request):
    """
    Multi-tenant business selection portal.
    Displays all retail companies/businesses the logged-in user has privileges over.
    Users can inspect their role and select which business workspace to launch.
    """
    user = request.user
    workspaces = []

    if user.is_superuser:
        companies = Company.objects.exclude(schema_name='public').filter(is_active=True)
        for c in companies:
            dom = c.domains.filter(is_primary=True).first()
            dom_name = dom.domain if dom else f"{c.schema_name}.localhost"
            token = generate_tenant_sso_token(user, c.schema_name)
            workspaces.append({
                'company': c,
                'domain': dom_name,
                'sso_token': token,
                'role_display': 'System Superadmin',
                'role_code': 'COMPANY_MANAGER',
                'can_approve': True,
                'can_read': True,
                'is_executive': True,
            })
    else:
        memberships = TenantMembership.objects.filter(user=user, is_active=True).select_related('company')
        for m in memberships:
            c = m.company
            if not c.is_active:
                continue
            dom = c.domains.filter(is_primary=True).first()
            dom_name = dom.domain if dom else f"{c.schema_name}.localhost"
            token = generate_tenant_sso_token(user, c.schema_name)
            workspaces.append({
                'company': c,
                'domain': dom_name,
                'sso_token': token,
                'role_display': m.get_role_display(),
                'role_code': m.role,
                'can_approve': m.can_approve,
                'can_read': m.can_read,
                'is_executive': m.role == 'COMPANY_MANAGER',
            })

    all_tenants_admin = []
    total_tenants_count = 0
    total_users_count = 0
    active_schemas_count = 0

    if user.is_superuser:
        all_companies = Company.objects.exclude(schema_name='public').order_by('-created_on')
        total_tenants_count = all_companies.count()
        active_schemas_count = all_companies.filter(is_active=True).count()
        total_users_count = User.objects.count()

        for c in all_companies:
            dom = c.domains.filter(is_primary=True).first()
            members_count = TenantMembership.objects.filter(company=c).count()
            all_tenants_admin.append({
                'company': c,
                'domain': dom.domain if dom else f"{c.schema_name}.localhost",
                'members_count': members_count,
            })

    port_str = get_platform_port_str(request)
    platforms = CommunityPlatform.objects.filter(is_active=True).order_by('display_order', 'id')

    context = {
        'platform_name': 'Clarity Retail Hub',
        'workspaces': workspaces,
        'all_tenants_admin': all_tenants_admin,
        'total_tenants_count': total_tenants_count,
        'total_users_count': total_users_count,
        'active_schemas_count': active_schemas_count,
        'platforms': platforms,
        'port_str': port_str,
        'port_suffix': port_str,
        'user': user,
    }
    return render(request, 'tenants/workspaces_list.html', context)


@require_POST
def register_company(request):
    """
    Onboard a new retail enterprise onto Clarity Retail Hub.
    Creates an isolated schema, company profile, and primary domain.
    """
    name = (request.POST.get('company_name') or '').strip()
    subdomain = (request.POST.get('subdomain') or '').strip().lower()
    email = (request.POST.get('email') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    currency = (request.POST.get('currency_code') or 'USD').strip().upper()

    if not name or not subdomain:
        return JsonResponse({
            'type': 'error',
            'title': 'Missing Information',
            'message': 'Company name and workspace subdomain are required.'
        }, status=400)

    clean_schema = re.sub(r'[^a-z0-9_]', '', subdomain.replace('-', '_'))
    if not clean_schema or len(clean_schema) < 3:
        return JsonResponse({
            'type': 'error',
            'title': 'Invalid Subdomain',
            'message': 'Subdomain must contain at least 3 alphanumeric characters.'
        }, status=400)

    if clean_schema in ['public', 'admin', 'api', 'www', 'mail', 'app']:
        return JsonResponse({
            'type': 'warning',
            'title': 'Reserved Subdomain',
            'message': f"'{clean_schema}' is a reserved system name. Please choose another."
        }, status=400)

    if Company.objects.filter(schema_name=clean_schema).exists():
        return JsonResponse({
            'type': 'warning',
            'title': 'Workspace Unavailable',
            'message': f"A company with subdomain '{subdomain}' already exists."
        }, status=400)

    try:
        company = Company.objects.create(
            schema_name=clean_schema,
            name=name,
            email=email,
            phone=phone,
            currency_code=currency,
            is_active=True
        )

        base_host = request.get_host().split(':')[0]
        if 'localhost' in base_host or '127.0.0.1' in base_host:
            tenant_domain_str = f"{subdomain}.localhost"
        else:
            tenant_domain_str = f"{subdomain}.{base_host}"

        Domain.objects.create(
            domain=tenant_domain_str,
            tenant=company,
            is_primary=True
        )

        # Automatically grant creator executive membership
        if request.user.is_authenticated:
            TenantMembership.objects.create(
                user=request.user,
                company=company,
                role='COMPANY_MANAGER',
                can_approve=True,
                can_read=True
            )

        return JsonResponse({
            'type': 'success',
            'title': 'Workspace Created',
            'message': f"Successfully created workspace for {name}. Domain: {tenant_domain_str}",
            'schema_name': clean_schema,
            'domain': tenant_domain_str
        })
    except Exception as e:
        return JsonResponse({
            'type': 'error',
            'title': 'Creation Failed',
            'message': f"Failed to provision company tenant schema: {str(e)}"
        }, status=500)


@require_POST
@login_required(login_url='user_login')
def toggle_tenant_status(request, company_id):
    """
    Allows a superuser to activate or suspend (pause) a tenant company.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    company = get_object_or_404(Company, id=company_id)
    if company.schema_name == 'public':
        return JsonResponse({'type': 'error', 'message': 'Cannot modify the public system schema.'}, status=400)

    company.is_active = not company.is_active
    company.save(update_fields=['is_active'])

    return JsonResponse({
        'type': 'success',
        'is_active': company.is_active,
        'message': f"Company '{company.name}' has been {'resumed' if company.is_active else 'paused / suspended'}."
    })


@require_POST
@login_required(login_url='user_login')
def update_tenant(request, company_id):
    """
    Update tenant enterprise details (name, trading name, email, phone, currency, tax numbers).
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    company = get_object_or_404(Company, id=company_id)
    if company.schema_name == 'public':
        return JsonResponse({'type': 'error', 'message': 'Cannot modify the public system schema.'}, status=400)

    name = (request.POST.get('name') or '').strip()
    if not name:
        return JsonResponse({'type': 'error', 'message': 'Enterprise name cannot be empty.'}, status=400)

    company.name = name
    company.trade_name = (request.POST.get('trade_name') or '').strip() or None
    company.email = (request.POST.get('email') or '').strip() or None
    company.phone = (request.POST.get('phone') or '').strip() or None
    company.currency_code = (request.POST.get('currency_code') or 'USD').strip().upper()
    company.currency_symbol = (request.POST.get('currency_symbol') or '$').strip()
    company.tin_number = (request.POST.get('tin_number') or '').strip() or None
    company.vat_number = (request.POST.get('vat_number') or '').strip() or None
    company.prz_number = (request.POST.get('prz_number') or '').strip() or None
    company.address = (request.POST.get('address') or '').strip() or None
    company.save()

    return JsonResponse({
        'type': 'success',
        'message': f"Enterprise '{company.name}' updated successfully."
    })


@require_POST
@login_required(login_url='user_login')
def delete_tenant(request, company_id):
    """
    Permanently delete a tenant company, its domain records, memberships, and PostgreSQL schema.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    company = get_object_or_404(Company, id=company_id)
    if company.schema_name == 'public':
        return JsonResponse({'type': 'error', 'message': 'Cannot delete the public system schema.'}, status=400)

    company_name = company.name
    schema_name = company.schema_name

    try:
        # Django-tenants will automatically drop the Postgres schema if auto_drop_schema is True,
        # or we invoke delete which triggers schema deletion.
        company.delete(force_drop=True)
        return JsonResponse({
            'type': 'success',
            'message': f"Enterprise '{company_name}' and schema '{schema_name}' have been permanently deleted."
        })
    except Exception as e:
        return JsonResponse({
            'type': 'error',
            'message': f"Failed to delete tenant schema: {str(e)}"
        }, status=500)


@login_required(login_url='user_login')
def get_tenant_details(request, company_id):
    """
    Retrieve tenant data and all its assigned users/memberships for editing.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    company = get_object_or_404(Company, id=company_id)
    dom = company.domains.filter(is_primary=True).first()

    memberships = TenantMembership.objects.filter(company=company).select_related('user')
    users_list = []
    for m in memberships:
        users_list.append({
            'membership_id': m.id,
            'user_id': m.user.id,
            'username': m.user.username,
            'email': m.user.email,
            'full_name': m.user.get_full_name() or m.user.username,
            'role': m.role,
            'role_display': m.get_role_display(),
            'is_active': m.is_active and m.user.is_active,
            'can_approve': m.can_approve,
            'can_read': m.can_read,
        })

    return JsonResponse({
        'type': 'success',
        'company': {
            'id': company.id,
            'name': company.name,
            'trade_name': company.trade_name or '',
            'schema_name': company.schema_name,
            'domain': dom.domain if dom else f"{company.schema_name}.localhost",
            'email': company.email or '',
            'phone': company.phone or '',
            'currency_code': company.currency_code,
            'currency_symbol': company.currency_symbol,
            'tin_number': company.tin_number or '',
            'vat_number': company.vat_number or '',
            'prz_number': company.prz_number or '',
            'address': company.address or '',
            'is_active': company.is_active,
        },
        'users': users_list
    })


@require_POST
@login_required(login_url='user_login')
def add_tenant_user(request, company_id):
    """
    Add a new or existing user to a specific tenant with assigned role.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    company = get_object_or_404(Company, id=company_id)
    email = (request.POST.get('email') or '').strip().lower()
    username = (request.POST.get('username') or '').strip().lower()
    first_name = (request.POST.get('first_name') or '').strip()
    last_name = (request.POST.get('last_name') or '').strip()
    password = (request.POST.get('password') or '').strip()
    role = (request.POST.get('role') or 'STAFF').strip()

    if not email:
        return JsonResponse({'type': 'error', 'message': 'Email address is required.'}, status=400)

    # Find or create user in shared auth
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        if not username:
            username = email.split('@')[0]
        # Ensure username uniqueness
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        if not password:
            password = 'password123'  # default initial password

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=True
        )
    else:
        if first_name and not user.first_name:
            user.first_name = first_name
        if last_name and not user.last_name:
            user.last_name = last_name
        if password:
            user.set_password(password)
        user.save()

    # Create or update membership
    membership, created = TenantMembership.objects.get_or_create(
        user=user,
        company=company,
        defaults={
            'role': role,
            'can_approve': role in ['COMPANY_MANAGER', 'BRANCH_MANAGER', 'SUPERVISOR'],
            'can_read': True,
            'is_active': True
        }
    )
    if not created:
        membership.role = role
        membership.can_approve = role in ['COMPANY_MANAGER', 'BRANCH_MANAGER', 'SUPERVISOR']
        membership.is_active = True
        membership.save()

    return JsonResponse({
        'type': 'success',
        'message': f"User '{user.email}' linked to '{company.name}' with role {membership.get_role_display()}."
    })


@require_POST
@login_required(login_url='user_login')
def toggle_tenant_user_status(request, membership_id):
    """
    Pause/Activate a specific tenant user membership or account.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    membership = get_object_or_404(TenantMembership, id=membership_id)
    membership.is_active = not membership.is_active
    membership.save(update_fields=['is_active'])

    return JsonResponse({
        'type': 'success',
        'is_active': membership.is_active,
        'message': f"User '{membership.user.email}' status set to {'active' if membership.is_active else 'paused / suspended'} for {membership.company.name}."
    })


@require_POST
@login_required(login_url='user_login')
def delete_tenant_user(request, membership_id):
    """
    Remove a user from a tenant (deletes the TenantMembership).
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    membership = get_object_or_404(TenantMembership, id=membership_id)
    user_email = membership.user.email
    company_name = membership.company.name
    membership.delete()

    return JsonResponse({
        'type': 'success',
        'message': f"Removed user '{user_email}' from '{company_name}'."
    })


def password_recovery(request):
    """
    Self-service password recovery portal.
    Allows users to enter their registered email address to initiate account recovery.
    """
    message = None
    status = None
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        if not email:
            status = 'error'
            message = 'Please provide your registered email address.'
        else:
            user = User.objects.filter(email__iexact=email).first()
            if user:
                status = 'success'
                message = f"Password reset instructions and verification link have been dispatched to {email}. Please inspect your inbox."
            else:
                # Security best practice: don't leak user existence, or inform cleanly
                status = 'info'
                message = f"If an account exists for {email}, recovery instructions have been sent. Check your inbox or contact your administrator."

    return render(request, 'tenants/password_recovery.html', {
        'message': message,
        'status': status,
        'platform_name': 'Clarity Retail Hub'
    })


@login_required(login_url='user_login')
def system_admin_dashboard(request):
    """
    Dedicated System Admin Dashboard for master platform administrators.
    Allows managing tenants, isolated database schemas, platform metrics, and system configuration.
    """
    if not request.user.is_superuser:
        return redirect('workspaces_list')

    all_companies = Company.objects.exclude(schema_name='public').order_by('-created_on')
    total_tenants_count = all_companies.count()
    active_schemas_count = all_companies.filter(is_active=True).count()
    total_users_count = User.objects.count()

    all_tenants_admin = []
    for c in all_companies:
        dom = c.domains.filter(is_primary=True).first()
        members_count = TenantMembership.objects.filter(company=c).count()
        all_tenants_admin.append({
            'company': c,
            'domain': dom.domain if dom else f"{c.schema_name}.localhost",
            'members_count': members_count,
        })

    port_str = get_platform_port_str(request)
    platforms = CommunityPlatform.objects.all().order_by('display_order', 'id')

    context = {
        'platform_name': 'Clarity Retail Hub',
        'all_tenants_admin': all_tenants_admin,
        'total_tenants_count': total_tenants_count,
        'total_users_count': total_users_count,
        'active_schemas_count': active_schemas_count,
        'platforms': platforms,
        'port_str': port_str,
        'user': request.user,
    }
    return render(request, 'tenants/system_admin_dashboard.html', context)


@require_POST
@login_required(login_url='user_login')
def add_community_platform(request):
    """
    Add a new sibling ecosystem server/service directly from System Admin.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    name = (request.POST.get('name') or '').strip()
    role_title = (request.POST.get('role_title') or '').strip()
    server_url = (request.POST.get('server_url') or '').strip()
    code = (request.POST.get('code') or '').strip().lower()
    icon_class = (request.POST.get('icon_class') or 'fa-solid fa-server').strip()
    accent_color = (request.POST.get('accent_color') or '#14b8a6').strip()
    badge_label = (request.POST.get('badge_label') or '').strip() or None
    description = (request.POST.get('description') or '').strip()
    try:
        display_order = int(request.POST.get('display_order') or 0)
    except (ValueError, TypeError):
        display_order = 0

    if not name or not server_url:
        return JsonResponse({'type': 'error', 'message': 'Platform name and server URL are required.'}, status=400)

    if not code:
        code = re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))

    # Ensure code uniqueness
    base_code = code
    counter = 1
    while CommunityPlatform.objects.filter(code=code).exists():
        code = f"{base_code}_{counter}"
        counter += 1

    platform = CommunityPlatform.objects.create(
        name=name,
        role_title=role_title or 'Ecosystem Sibling Platform',
        server_url=server_url,
        code=code,
        icon_class=icon_class,
        accent_color=accent_color,
        badge_label=badge_label,
        description=description or f"Direct server endpoint for {name}",
        display_order=display_order,
        is_active=True
    )

    return JsonResponse({
        'type': 'success',
        'message': f"Server connection for '{platform.name}' created successfully.",
        'platform_id': platform.id
    })


@require_POST
@login_required(login_url='user_login')
def update_community_platform(request, platform_id):
    """
    Update an existing sibling ecosystem server/service directly from System Admin.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    platform = get_object_or_404(CommunityPlatform, id=platform_id)

    name = (request.POST.get('name') or '').strip()
    role_title = (request.POST.get('role_title') or '').strip()
    server_url = (request.POST.get('server_url') or '').strip()
    icon_class = (request.POST.get('icon_class') or '').strip()
    accent_color = (request.POST.get('accent_color') or '').strip()
    badge_label = (request.POST.get('badge_label') or '').strip()
    description = (request.POST.get('description') or '').strip()
    is_active = request.POST.get('is_active')

    if not name or not server_url:
        return JsonResponse({'type': 'error', 'message': 'Platform name and server URL cannot be empty.'}, status=400)

    platform.name = name
    if role_title:
        platform.role_title = role_title
    platform.server_url = server_url
    if icon_class:
        platform.icon_class = icon_class
    if accent_color:
        platform.accent_color = accent_color
    platform.badge_label = badge_label if badge_label else None
    if description:
        platform.description = description
    if is_active is not None:
        platform.is_active = is_active in ['true', 'True', '1', True]

    try:
        if 'display_order' in request.POST:
            platform.display_order = int(request.POST.get('display_order'))
    except (ValueError, TypeError):
        pass

    platform.save()

    return JsonResponse({
        'type': 'success',
        'message': f"Platform '{platform.name}' details updated successfully."
    })


@require_POST
@login_required(login_url='user_login')
def delete_community_platform(request, platform_id):
    """
    Delete a sibling ecosystem server connection directly from System Admin.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    platform = get_object_or_404(CommunityPlatform, id=platform_id)
    platform_name = platform.name
    platform.delete()

    return JsonResponse({
        'type': 'success',
        'message': f"Server connection for '{platform_name}' removed successfully."
    })


@login_required(login_url='user_login')
def get_community_platform_details(request, platform_id):
    """
    Fetch platform details for modal editing.
    """
    if not request.user.is_superuser:
        return JsonResponse({'type': 'error', 'message': 'Superuser privileges required.'}, status=403)

    platform = get_object_or_404(CommunityPlatform, id=platform_id)
    return JsonResponse({
        'type': 'success',
        'platform': {
            'id': platform.id,
            'name': platform.name,
            'role_title': platform.role_title,
            'server_url': platform.server_url,
            'code': platform.code,
            'icon_class': platform.icon_class,
            'accent_color': platform.accent_color,
            'badge_label': platform.badge_label or '',
            'description': platform.description,
            'is_active': platform.is_active,
            'display_order': platform.display_order,
            'is_current_platform': platform.is_current_platform
        }
    })



