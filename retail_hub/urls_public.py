# urls_public.py — Public schema routing for Clarity Retail Hub
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from tenants import views as tenant_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sso/auth/', tenant_views.sso_tenant_login, name='sso_tenant_login'),
    path('', tenant_views.public_home, name='public_home'),
    path('login/', tenant_views.user_login, name='user_login'),
    path('logout/', tenant_views.user_logout, name='user_logout'),
    path('password-recovery/', tenant_views.password_recovery, name='password_recovery'),
    path('workspaces/', tenant_views.workspaces_list, name='workspaces_list'),
    path('workspaces/select/<str:schema_name>/', tenant_views.select_workspace, name='select_workspace'),
    path('exit-workspace/', tenant_views.exit_workspace, name='exit_workspace'),
    path('system-admin/', tenant_views.system_admin_dashboard, name='system_admin_dashboard'),
    path('workspaces/toggle/<int:company_id>/', tenant_views.toggle_tenant_status, name='toggle_tenant_status'),
    path('workspaces/update/<int:company_id>/', tenant_views.update_tenant, name='update_tenant'),
    path('workspaces/delete/<int:company_id>/', tenant_views.delete_tenant, name='delete_tenant'),
    path('workspaces/details/<int:company_id>/', tenant_views.get_tenant_details, name='get_tenant_details'),
    path('workspaces/users/add/<int:company_id>/', tenant_views.add_tenant_user, name='add_tenant_user'),
    path('workspaces/users/toggle/<int:membership_id>/', tenant_views.toggle_tenant_user_status, name='toggle_tenant_user_status'),
    path('workspaces/users/delete/<int:membership_id>/', tenant_views.delete_tenant_user, name='delete_tenant_user'),
    path('workspaces/platforms/add/', tenant_views.add_community_platform, name='add_community_platform'),
    path('workspaces/platforms/update/<int:platform_id>/', tenant_views.update_community_platform, name='update_community_platform'),
    path('workspaces/platforms/delete/<int:platform_id>/', tenant_views.delete_community_platform, name='delete_community_platform'),
    path('workspaces/platforms/details/<int:platform_id>/', tenant_views.get_community_platform_details, name='get_community_platform_details'),
    path('register/', tenant_views.register_company, name='register_company'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
