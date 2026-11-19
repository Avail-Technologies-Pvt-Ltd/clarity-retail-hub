from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
    """Catalog of available subscription tiers in Clarity Retail Hub."""
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_branches = models.IntegerField(default=5)
    max_users = models.IntegerField(default=15)
    features_list = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (${self.monthly_price}/mo)"


class CompanySubscription(models.Model):
    """
    Shared schema table tracking tenant subscription status, limits, and expiration.
    """
    STATUS_CHOICES = [
        ('TRIAL', 'Active Trial'),
        ('ACTIVE', 'Active Subscription'),
        ('PAST_DUE', 'Past Due'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    ]

    company = models.OneToOneField('tenants.Company', on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    max_branches = models.IntegerField(default=10)
    max_users = models.IntegerField(default=25)
    start_date = models.DateField(default=timezone.now)
    expires_at = models.DateField(null=True, blank=True)
    last_payment_date = models.DateField(null=True, blank=True)
    billing_email = models.EmailField(blank=True, default='')
    billing_phone = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Subscription"
        verbose_name_plural = "Company Subscriptions"

    def __str__(self):
        return f"{self.company.name} — {self.status} (Expires: {self.expires_at or 'Never'})"

    @property
    def is_valid(self):
        if self.status not in ['ACTIVE', 'TRIAL']:
            return False
        if self.expires_at and self.expires_at < timezone.now().date():
            return False
        return True

    @property
    def days_remaining(self):
        if not self.expires_at:
            return 999
        delta = self.expires_at - timezone.now().date()
        return max(0, delta.days)

    @property
    def is_in_warning_grace(self):
        """Returns True if expired within the last 7 days (warning stage before hard lock)."""
        if self.is_valid:
            return False
        if not self.expires_at:
            return False
        delta = (timezone.now().date() - self.expires_at).days
        return 0 < delta <= 7

    @property
    def is_hard_locked(self):
        """Returns True if expired more than 7 days ago (hard lock POS stage)."""
        if self.is_valid:
            return False
        if not self.expires_at:
            return False
        delta = (timezone.now().date() - self.expires_at).days
        return delta > 7

