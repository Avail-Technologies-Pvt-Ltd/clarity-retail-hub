from django.core.management.base import BaseCommand
from tenants.models import Company, Domain


class Command(BaseCommand):
    help = 'Create public tenant and domain for django-tenants if they do not exist'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-demo',
            action='store_true',
            help='Also create a sample demo tenant (demo.localhost)'
        )

    def handle(self, *args, **options):
        # 1. Create or verify the public schema tenant
        public_tenant = Company.objects.filter(schema_name='public').first()
        if not public_tenant:
            self.stdout.write("Creating public tenant...")
            public_tenant = Company(
                schema_name='public',
                name='Clarity Retail Hub (Public Platform)',
                is_active=True
            )
            public_tenant.auto_create_schema = False
            public_tenant.save()

            # Map default public domains
            public_domains = ['localhost', '127.0.0.1', 'public.localhost', 'retail-hub.localhost', 'web']
            for idx, domain_name in enumerate(public_domains):
                Domain.objects.get_or_create(
                    domain=domain_name,
                    tenant=public_tenant,
                    defaults={'is_primary': (idx == 0)}
                )
            self.stdout.write(self.style.SUCCESS("[OK] Public tenant and default domains created successfully."))
        else:
            self.stdout.write(self.style.NOTICE("[OK] Public tenant already exists."))

        # 2. Optionally create demo tenant
        if options.get('create_demo'):
            if not Company.objects.filter(schema_name='demo').exists():
                self.stdout.write("Creating demo tenant...")
                demo_company = Company.objects.create(
                    schema_name='demo',
                    name='Clarity Demo Supermarkets',
                    trade_name='Clarity Express',
                    tin_number='20019284',
                    vat_number='100928374',
                    email='demo@clarityretail.co.zw',
                    phone='+263 77 100 2000',
                    address='120 Samora Machel Ave, Harare, Zimbabwe',
                    currency_code='USD',
                    currency_symbol='$',
                    is_active=True
                )
                Domain.objects.create(
                    domain='demo.localhost',
                    tenant=demo_company,
                    is_primary=True
                )
                self.stdout.write(self.style.SUCCESS("[OK] Demo tenant (demo.localhost) created."))
            else:
                self.stdout.write(self.style.NOTICE("[OK] Demo tenant already exists."))

        # 3. Create or verify universal testing root superuser
        from django.contrib.auth.models import User
        root_user = User.objects.filter(username='root').first()
        if not root_user:
            root_user = User.objects.create_superuser(
                username='root',
                email='root@gmail.com',
                password='toor',
                first_name='Master',
                last_name='Root'
            )
            self.stdout.write(self.style.SUCCESS("[OK] Universal root superuser created (Username: root, Pass: toor)."))
        else:
            root_user.email = 'root@gmail.com'
            root_user.set_password('toor')
            root_user.is_superuser = True
            root_user.is_staff = True
            root_user.save()
            self.stdout.write(self.style.NOTICE("[OK] Universal root superuser credentials confirmed."))
