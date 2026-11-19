from django.db import models
from branches.models import Branch


class DailyBranchSummary(models.Model):
    """
    Lightweight daily operational summary synced from physical edge stores.
    The Hub uses these daily summaries to dynamically compute Weekly, Monthly,
    and Annual consolidated financial reports on demand.
    """
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='daily_summaries')
    summary_date = models.DateField(db_index=True)
    sales_count = models.IntegerField(default=0)
    gross_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    expenses_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_cashflow = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    fiscalised_count = models.IntegerField(default=0)
    tender_breakdown = models.JSONField(default=dict, blank=True)
    cashier_breakdown = models.JSONField(default=list, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Daily Branch Summary"
        verbose_name_plural = "Daily Branch Summaries"
        unique_together = [('branch', 'summary_date')]
        ordering = ['-summary_date', 'branch__branch_code']

    def __str__(self):
        return f"{self.branch.branch_code} — {self.summary_date}: ${self.gross_sales}"


class ReportExport(models.Model):
    """Logs generated consolidated exports (CSV/PDF) for audit and history."""
    report_type = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    generated_by = models.CharField(max_length=150, default='System Manager')
    file_name = models.CharField(max_length=255)
    records_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Report Export"
        verbose_name_plural = "Report Exports"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.report_type} ({self.created_at.strftime('%Y-%m-%d')})"
