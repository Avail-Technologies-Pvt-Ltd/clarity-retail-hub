from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Company(TenantMixin):
    """
    Tenant model for Clarity Retail Hub.
    Each company represents a distinct retail enterprise with one or more branches.
    Stored in the shared 'public' schema, while each company gets its own isolated Postgres schema.
    """
    name = models.CharField(max_length=200, help_text="Legal or business name of the retail company")
    trade_name = models.CharField(max_length=200, blank=True, null=True, help_text="Trading name / Store brand")
    tin_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Taxpayer Identification Number (TIN)")
    vat_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="VAT Registration Number")
    prz_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="PRZ Number")

    # Primary contact
    email = models.EmailField(blank=True, null=True, help_text="Primary administrative contact email")
    phone = models.CharField(max_length=50, blank=True, null=True, help_text="Primary business phone")
    address = models.TextField(blank=True, null=True, help_text="Physical head office address")

    # Localization
    currency_code = models.CharField(max_length=10, default="USD")
    currency_symbol = models.CharField(max_length=5, default="$")
    timezone = models.CharField(max_length=50, default="Africa/Harare")

    # Subscription & Lifecycle
    is_active = models.BooleanField(default=True, help_text="Controls access to this tenant's workspace")
    created_on = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Automatically create the PostgreSQL schema upon save
    auto_create_schema = True

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ['-created_on']

    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    """
    Domain routing model for django-tenants.
    Maps subdomains or custom domains (e.g., 'harare-store.clarityhub.co.zw' or 'store1.localhost')
    to specific Company schemas.
    """
    pass


class TenantMembership(models.Model):
    """
    Shared-schema link granting a user access and privileges to one or more Company workspaces.
    Used for multi-business selection on login.
    """
    ROLE_CHOICES = [
        ('COMPANY_MANAGER', 'Company Manager (Executive / All Branches)'),
        ('BRANCH_MANAGER', 'Branch Manager (Store Lead)'),
        ('SUPERVISOR', 'Supervisor (Shift Oversight & Approvals)'),
        ('STAFF', 'Staff (Read & Operations)'),
    ]

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='tenant_memberships')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='COMPANY_MANAGER')
    can_approve = models.BooleanField(default=True, help_text="Can approve discounts, high-value sales, and refunds")
    can_read = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tenant Membership"
        verbose_name_plural = "Tenant Memberships"
        unique_together = ('user', 'company')
        ordering = ['company__name']

    def __str__(self):
        return f"{self.user.username} @ {self.company.name} ({self.get_role_display()})"


class CommunityPlatform(models.Model):
    """
    Catalog of sibling platforms in the Clarity Community Suite.
    Administered in Django Admin like a product directory: name, role, description,
    server URL, icon, badge, order, and active status.
    """
    code = models.CharField(max_length=50, unique=True, help_text="Slug identifier, e.g. 'retail_lan', 'wholesale_hub'")
    name = models.CharField(max_length=150, help_text="Platform display title, e.g. 'Clarity Wholesale'")
    role_title = models.CharField(max_length=150, help_text="Subtitle/role, e.g. 'Bulk Distribution & Depots'")
    server_url = models.CharField(max_length=255, default='#', help_text="Full external or LAN server link, e.g. 'http://localhost:8001/' or 'https://wholesale.clarityhub.co.zw'")
    server_label = models.CharField(max_length=80, default="Launch Platform Server", help_text="Button text on the platform card")
    icon_class = models.CharField(max_length=80, default="fa-solid fa-server", help_text="FontAwesome icon class")
    accent_color = models.CharField(max_length=30, default="#14b8a6", help_text="Hex color for badges and highlights")
    badge_label = models.CharField(max_length=50, blank=True, null=True, help_text="Optional banner pill, e.g. 'Active Server', 'Current Hub'")
    description = models.TextField(help_text="Detailed overview of platform duties and capabilities")
    feature_1 = models.CharField(max_length=150, blank=True, null=True)
    feature_2 = models.CharField(max_length=150, blank=True, null=True)
    feature_3 = models.CharField(max_length=150, blank=True, null=True)
    is_current_platform = models.BooleanField(default=False, help_text="Marks this application itself")
    is_active = models.BooleanField(default=True, help_text="Show or hide on public and member portals")
    display_order = models.IntegerField(default=0, help_text="Lower numbers appear first")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Community Platform Listing"
        verbose_name_plural = "Community Platform Listings"
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.name} ({self.server_url})"


