from django.contrib import admin
from .models import SyncLog, ProcessedEvent


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ('branch', 'direction', 'payload_type', 'records_count', 'status', 'created_at')
    list_filter = ('direction', 'status', 'payload_type', 'created_at')
    search_fields = ('branch__name', 'branch__branch_code', 'error_message')
    readonly_fields = ('created_at',)


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ('entity_type', 'global_id', 'branch', 'processed_at')
    list_filter = ('entity_type', 'processed_at')
    search_fields = ('global_id', 'branch__branch_code')
    readonly_fields = ('processed_at',)
