from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User
from django.urls import reverse
from django.conf import settings
from tenants.models import Company, Domain, TenantMembership
from tenants.views import generate_tenant_sso_token, sso_tenant_login, select_workspace, exit_workspace


class TenantSubdomainRoutingAndSSOTests(TestCase):
    def setUp(self):
        # Create public tenant
        self.public_company = Company.objects.create(
            name='Public Platform',
            schema_name='public',
            is_active=True
        )
        Domain.objects.create(
            domain='localhost',
            tenant=self.public_company,
            is_primary=True
        )

        # Create demo tenant
        self.demo_company = Company.objects.create(
            name='Clarity Demo Supermarkets',
            schema_name='demo',
            is_active=True
        )
        self.demo_domain = Domain.objects.create(
            domain='demo.localhost',
            tenant=self.demo_company,
            is_primary=True
        )

        # Create a test user
        self.user = User.objects.create_user(
            username='store_manager',
            email='manager@demo.com',
            password='testpassword123'
        )

        # Membership in demo company
        TenantMembership.objects.create(
            user=self.user,
            company=self.demo_company,
            role='COMPANY_MANAGER',
            is_active=True
        )

        self.factory = RequestFactory()

    def test_sso_token_generation_and_consumption(self):
        token = generate_tenant_sso_token(self.user, 'demo')
        self.assertTrue(token)

        request = self.factory.get(f'/sso/auth/?token={token}', HTTP_HOST='demo.localhost:8003')
        request.tenant = self.demo_company
        # Django session middleware emulation
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()

        response = sso_tenant_login(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Launching Workspace', response.content.decode())
        self.assertIn('window.location.replace', response.content.decode())

    def test_select_workspace_redirects_to_subdomain_sso(self):
        request = self.factory.get('/workspaces/select/demo/', HTTP_HOST='localhost:8003')
        request.user = self.user
        request.tenant = self.public_company
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()

        response = select_workspace(request, 'demo')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('http://demo.localhost:8003/sso/auth/?token='))

    def test_exit_workspace_redirects_to_public_workspaces(self):
        request = self.factory.get('/exit-workspace/', HTTP_HOST='demo.localhost:8003')
        request.user = self.user
        request.tenant = self.demo_company
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()

        response = exit_workspace(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/workspaces/'))
