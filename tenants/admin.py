from django.contrib import admin
from django_tenants.admin import TenantAdminMixin
from .models import Company, Domain


@admin.register(Company)
class CompanyAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'trade_name', 'tin_number', 'currency_code', 'is_active', 'created_on')
    search_fields = ('name', 'schema_name', 'trade_name', 'tin_number', 'email')
    list_filter = ('is_active', 'currency_code', 'created_on')
    readonly_fields = ('created_on', 'updated_at')
    fieldsets = (
        ("Tenant Schema Identification", {
            "fields": ("schema_name", "name", "trade_name", "is_active")
        }),
        ("Fiscal & Tax Identifiers", {
            "fields": ("tin_number", "vat_number", "prz_number")
        }),
        ("Contact Information", {
            "fields": ("email", "phone", "address")
        }),
        ("Locale Settings", {
            "fields": ("currency_code", "currency_symbol", "timezone")
        }),
        ("Timestamps", {
            "fields": ("created_on", "updated_at")
        }),
    )


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    search_fields = ('domain', 'tenant__name', 'tenant__schema_name')
    list_filter = ('is_primary',)


from .models import CommunityPlatform

@admin.register(CommunityPlatform)
class CommunityPlatformAdmin(admin.ModelAdmin):
    list_display = ('name', 'role_title', 'server_url', 'server_label', 'display_order', 'is_current_platform', 'is_active')
    list_editable = ('server_url', 'server_label', 'display_order', 'is_active')
    search_fields = ('name', 'code', 'server_url', 'role_title')
    list_filter = ('is_active', 'is_current_platform')
    fieldsets = (
        ("Platform Identity", {
            "fields": ("code", "name", "role_title", "is_current_platform", "badge_label")
        }),
        ("Server Connection & Link", {
            "fields": ("server_url", "server_label")
        }),
        ("Visuals & Theme", {
            "fields": ("icon_class", "accent_color", "display_order", "is_active")
        }),
        ("Overview & Key Features", {
            "fields": ("description", "feature_1", "feature_2", "feature_3")
        }),
    )

