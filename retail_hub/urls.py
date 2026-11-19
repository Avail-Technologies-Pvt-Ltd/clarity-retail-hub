# urls.py — Tenant schema routing for Clarity Retail Hub
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from tenants import views as tenant_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sso/auth/', tenant_views.sso_tenant_login, name='sso_tenant_login'),
    path('login/', tenant_views.user_login, name='user_login'),
    path('logout/', tenant_views.user_logout, name='user_logout'),
    path('password-recovery/', tenant_views.password_recovery, name='password_recovery'),
    path('workspaces/', tenant_views.workspaces_list, name='workspaces_list'),
    path('workspaces/select/<str:schema_name>/', tenant_views.select_workspace, name='select_workspace'),
    path('exit-workspace/', tenant_views.exit_workspace, name='exit_workspace'),
    path('system-admin/', tenant_views.system_admin_dashboard, name='system_admin_dashboard'),
    path('workspaces/toggle/<int:company_id>/', tenant_views.toggle_tenant_status, name='toggle_tenant_status'),
    path('', include('dashboard.urls')),
    path('branches/', include('branches.urls')),
    path('sync/', include('sync_gateway.urls')),
    path('reports/', include('reports.urls')),
    path('marketplace/', include('marketplace.urls')),
    path('subscriptions/', include('subscriptions.urls')),
    path('accounts/', include('accounts_hub.urls')),
    path('notifications/', include('notifications.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
