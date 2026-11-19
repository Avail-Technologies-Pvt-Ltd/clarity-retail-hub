from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from tenants.models import Company
from subscriptions.models import SubscriptionPlan, CompanySubscription


class SubscriptionGraceAndLifecycleTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            schema_name='testco',
            name='Test Retail Enterprise'
        )
        self.plan = SubscriptionPlan.objects.create(
            code='starter',
            name='Starter Chain',
            monthly_price=49.00
        )

    def test_active_subscription_validity(self):
        sub = CompanySubscription.objects.create(
            company=self.company,
            plan=self.plan,
            status='ACTIVE',
            expires_at=timezone.now().date() + timedelta(days=30)
        )
        self.assertTrue(sub.is_valid)
        self.assertFalse(sub.is_in_warning_grace)
        self.assertFalse(sub.is_hard_locked)
        self.assertGreaterEqual(sub.days_remaining, 29)

    def test_warning_grace_period_first_7_days_after_expiry(self):
        """Within 7 days of expiration, system enters warning grace stage."""
        sub = CompanySubscription.objects.create(
            company=self.company,
            plan=self.plan,
            status='ACTIVE',
            expires_at=timezone.now().date() - timedelta(days=3)
        )
        self.assertFalse(sub.is_valid)
        self.assertTrue(sub.is_in_warning_grace)
        self.assertFalse(sub.is_hard_locked)

    def test_hard_locked_after_warning_grace(self):
        """More than 7 days after expiration, system enters hard-lock stage."""
        sub = CompanySubscription.objects.create(
            company=self.company,
            plan=self.plan,
            status='EXPIRED',
            expires_at=timezone.now().date() - timedelta(days=10)
        )
        self.assertFalse(sub.is_valid)
        self.assertFalse(sub.is_in_warning_grace)
        self.assertTrue(sub.is_hard_locked)
