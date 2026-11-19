from django.contrib import admin
from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch_code', 'status', 'is_headquarters', 'manager_name', 'phone', 'last_sync_at', 'last_ping_at')
    list_filter = ('status', 'is_headquarters', 'created_at')
    search_fields = ('name', 'branch_code', 'manager_name', 'phone', 'sync_token')
    readonly_fields = ('sync_token', 'created_at', 'updated_at', 'last_sync_at', 'last_ping_at')
    fieldsets = (
        ("Store Identity", {
            "fields": ("name", "branch_code", "status", "is_headquarters")
        }),
        ("Management & Location", {
            "fields": ("manager_name", "address", "phone", "email")
        }),
        ("Sync Edge Integration", {
            "fields": ("sync_token", "last_sync_at", "last_ping_at", "edge_version")
        }),
        ("Banking / Settlement", {
            "fields": ("bank_name", "bank_account_number")
        }),
        ("System Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )
