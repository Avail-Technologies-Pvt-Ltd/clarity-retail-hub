from django.db import models
from django.conf import settings
from branches.models import Branch


class HubUserProfile(models.Model):
    """
    Tenant employee profile implementing the 4 universal Clarity user tiers:
    Staff, Supervisor, Branch Manager, and Company Manager.
    """
    ROLE_CHOICES = [
        ('STAFF', 'Store Staff (POS & Operations)'),
        ('SUPERVISOR', 'Supervisor (Approvals & Oversight)'),
        ('BRANCH_MANAGER', 'Branch Manager (Store Lead)'),
        ('COMPANY_MANAGER', 'Company Manager (Executive / All Branches)'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hub_profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='STAFF')
    assigned_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_members')
    phone = models.CharField(max_length=50, blank=True, default='')
    job_title = models.CharField(max_length=100, blank=True, default='Retail Associate')
    is_active = models.BooleanField(default=True)
    can_approve = models.BooleanField(default=False, help_text="Can approve discounts, returns, and inventory adjustments")
    can_read = models.BooleanField(default=True, help_text="Can view transactions and store reports")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ['role', 'user__username']

    def __str__(self):
        branch_str = self.assigned_branch.branch_code if self.assigned_branch else "All Branches"
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()} - {branch_str})"
