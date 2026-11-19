from django.db import models
from branches.models import Branch


class SyncLog(models.Model):
    DIRECTION_CHOICES = [
        ('PUSH', 'Edge Push (Incoming from LAN)'),
        ('PULL', 'Edge Pull (Outgoing to LAN)'),
    ]
    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('WARNING', 'Warning / Partial'),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='sync_logs')
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default='PUSH')
    payload_type = models.CharField(max_length=50, default='BATCH')
    records_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS')
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sync Log"
        verbose_name_plural = "Sync Logs"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.branch.branch_code} - {self.payload_type} ({self.status}) at {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class ProcessedEvent(models.Model):
    """
    Idempotency registry.
    Tracks processed event global_ids per branch to guarantee exactly-once processing of incoming LAN sync payloads.
    """
    global_id = models.CharField(max_length=128, db_index=True)
    entity_type = models.CharField(max_length=50, help_text="e.g. Sale, Stock, Expense, Customer")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='processed_events')
    payload_data = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Processed Event"
        verbose_name_plural = "Processed Events"
        unique_together = [('global_id', 'branch')]
        ordering = ['-processed_at']

    def __str__(self):
        return f"{self.entity_type}:{self.global_id} ({self.branch.branch_code})"
