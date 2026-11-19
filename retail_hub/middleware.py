from django.shortcuts import redirect
from django.conf import settings
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import (
    get_tenant_model,
    get_tenant_domain_model,
    get_public_schema_name,
    remove_www,
)
from django.db import connection
from django.core.exceptions import DisallowedHost
from django.http import HttpResponseNotFound
from django.urls import set_urlconf
from .context_processors import get_platform_port_str


class RetailHubTenantMiddleware(TenantMainMiddleware):
    """
    Intelligent Multi-Tenant Resolution Middleware.
    Supports both:
      1. Standard subdomain routing (e.g. demo.localhost or acme.myretailhub.com)
      2. Cookie/Session-based tenant switching on localhost/127.0.0.1
         Allows users to:
           visit public [public info] -> login -> [list of tenants associated with account + admin]
           -> pick one and access directly WITHOUT needing to log in again!
    """

    def process_request(self, request):
        connection.set_schema_to_public()
        try:
            hostname = self.hostname_from_request(request)
        except DisallowedHost:
            return HttpResponseNotFound()

        domain_model = get_tenant_domain_model()
        tenant_model = get_tenant_model()

        # If accessed via root host (localhost or 127.0.0.1)
        if hostname in ['localhost', '127.0.0.1']:
            # Fallback to public tenant on localhost (Option 1: Subdomain routing)
            # The root host (localhost:8003) is strictly reserved for the public portal,
            # system authentication, and the workspaces selection portal.
            try:
                public_tenant = self.get_tenant(domain_model, 'localhost')
            except domain_model.DoesNotExist:
                public_tenant = tenant_model.objects.filter(schema_name='public').first()

            if public_tenant:
                public_tenant.domain_url = hostname
                request.tenant = public_tenant
                connection.set_tenant(request.tenant)
                if hasattr(settings, 'PUBLIC_SCHEMA_URLCONF'):
                    request.urlconf = settings.PUBLIC_SCHEMA_URLCONF
                    set_urlconf(request.urlconf)
                return None

        # Standard domain/subdomain resolution for external hostnames
        try:
            tenant = self.get_tenant(domain_model, hostname)
        except domain_model.DoesNotExist:
            default_tenant = self.no_tenant_found(request, hostname)
            return default_tenant

        tenant.domain_url = hostname
        request.tenant = tenant
        connection.set_tenant(request.tenant)
        self.setup_url_routing(request)


class HostNormalizationMiddleware:
    """
    Normalizes IP addresses (127.0.0.1) or raw hosts to standard domain (localhost or PLATFORM_DOMAIN).
    In multi-tenant setups with wildcard session cookies (SESSION_COOKIE_DOMAIN = .localhost),
    browsers (Chrome, Edge, Firefox) reject domain cookies if the user browses via an IP address (127.0.0.1).
    This middleware transparently redirects 127.0.0.1:8003 to localhost:8003 so cookies work seamlessly.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host_header = request.get_host().split(':')[0]
        if host_header == '127.0.0.1':
            port_suffix = get_platform_port_str(request)
            target_domain = getattr(settings, 'PLATFORM_DOMAIN', 'localhost')
            target_url = f"{request.scheme}://{target_domain}{port_suffix}{request.get_full_path()}"
            return redirect(target_url)

        return self.get_response(request)
