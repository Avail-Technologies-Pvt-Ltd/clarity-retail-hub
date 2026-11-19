from django.shortcuts import render, get_object_or_404
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from branches.models import Branch
from .models import HubUserProfile
from retail_hub.decorators import role_validator, company_manager_required, staff_required


def _ok(title, message, **extra):
    return JsonResponse({'type': 'success', 'title': title, 'message': message, **extra})

def _err(title, message, status=400):
    return JsonResponse({'type': 'error', 'title': title, 'message': message}, status=status)


@role_validator(['COMPANY_MANAGER', 'BRANCH_MANAGER'])
def team_list(request):
    """
    Team & User Management implementing the 4 universal tiers:
    Staff, Supervisor, Branch Manager, and Company Manager.
    """
    tenant = getattr(request, 'tenant', None)
    branches = Branch.objects.all().order_by('branch_code')
    users = User.objects.all().select_related('hub_profile').order_by('-date_joined')

    # Ensure all users have a HubUserProfile
    for u in users:
        if not hasattr(u, 'hub_profile'):
            HubUserProfile.objects.create(
                user=u,
                role='COMPANY_MANAGER' if u.is_superuser else 'STAFF',
                job_title='Administrator' if u.is_superuser else 'Retail Associate'
            )

    # Re-query with profiles
    users = User.objects.all().select_related('hub_profile', 'hub_profile__assigned_branch').order_by('-date_joined')

    context = {
        'page_title': 'Team & User Roles',
        'tenant': tenant,
        'users': users,
        'branches': branches,
        'total_members': users.count(),
        'roles': HubUserProfile.ROLE_CHOICES,
    }
    return render(request, 'accounts_hub/team_list.html', context)


@company_manager_required
def ajax_save_user(request):
    """Creates or updates a tenant user and assigns role and branch."""
    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST requests allowed.', 405)

    user_id = request.POST.get('user_id')
    username = request.POST.get('username', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    role = request.POST.get('role', 'STAFF')
    job_title = request.POST.get('job_title', 'Retail Associate').strip()
    branch_id = request.POST.get('branch_id')
    phone = request.POST.get('phone', '').strip()
    password = request.POST.get('password', '').strip()

    if not username:
        return _err('Validation Error', 'Username is required.')

    branch = None
    if branch_id and branch_id != 'ALL':
        branch = Branch.objects.filter(id=branch_id).first()

    if user_id:
        user = get_object_or_404(User, id=user_id)
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        if password:
            user.set_password(password)
        user.save()

        profile, _ = HubUserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.job_title = job_title
        profile.assigned_branch = branch
        profile.phone = phone
        profile.save()

        return _ok('Team Member Updated', f"User '{user.username}' successfully updated.")
    else:
        if User.objects.filter(username=username).exists():
            return _err('Username Exists', f"Username '{username}' is already in use.")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password or 'ClarityRetail2026!',
            first_name=first_name,
            last_name=last_name
        )

        HubUserProfile.objects.create(
            user=user,
            role=role,
            job_title=job_title,
            assigned_branch=branch,
            phone=phone,
            is_active=True
        )

        return _ok('Team Member Added', f"User '{username}' created with role {role}.")


@company_manager_required
def ajax_toggle_user_status(request, user_id):
    """Toggles active status of a team member."""
    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST allowed.', 405)

    user = get_object_or_404(User, id=user_id)
    if user.is_superuser:
        return _err('Action Denied', 'Superuser status cannot be deactivated.')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])

    profile = getattr(user, 'hub_profile', None)
    if profile:
        profile.is_active = user.is_active
        profile.save(update_fields=['is_active'])

    state_str = "activated" if user.is_active else "deactivated"
    return _ok('User Status Updated', f"User '{user.username}' has been {state_str}.")


@login_required(login_url='user_login')
def ajax_update_profile(request):
    """Updates logged-in user profile details (name, email, phone, job title)."""
    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST allowed.', 405)
    if not request.user.is_authenticated:
        return _err('Unauthorized', 'Please log in to update your profile.', 401)

    user = request.user
    user.first_name = request.POST.get('first_name', '').strip()
    user.last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    if email:
        user.email = email
    user.save()

    profile, _ = HubUserProfile.objects.get_or_create(user=user)
    phone = request.POST.get('phone', '').strip()
    job_title = request.POST.get('job_title', '').strip()
    if phone:
        profile.phone = phone
    if job_title:
        profile.job_title = job_title
    profile.save()

    return _ok('Profile Updated', 'Your profile details have been successfully saved.', full_name=user.get_full_name() or user.username)


@login_required(login_url='user_login')
def ajax_change_password(request):
    """Changes password for the currently logged-in user."""
    from django.contrib.auth import update_session_auth_hash

    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST allowed.', 405)
    if not request.user.is_authenticated:
        return _err('Unauthorized', 'Please log in to change password.', 401)

    new_password = request.POST.get('new_password', '').strip()
    confirm_password = request.POST.get('confirm_password', '').strip()

    if not new_password or len(new_password) < 6:
        return _err('Validation Error', 'Password must be at least 6 characters long.')
    if new_password != confirm_password:
        return _err('Validation Error', 'New password and confirmation do not match.')

    user = request.user
    user.set_password(new_password)
    user.save()
    update_session_auth_hash(request, user)

    return _ok('Password Changed', 'Your password has been updated successfully.')
