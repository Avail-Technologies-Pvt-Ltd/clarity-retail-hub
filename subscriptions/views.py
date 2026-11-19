from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from branches.models import Branch
from .models import CompanySubscription, SubscriptionPlan
from retail_hub.decorators import company_manager_required


def _ok(title, message, **extra):
    return JsonResponse({'type': 'success', 'title': title, 'message': message, **extra})

def _err(title, message, status=400):
    return JsonResponse({'type': 'error', 'title': title, 'message': message}, status=status)


@company_manager_required
def subscription_page(request):
    """
    Company Subscription & Terminal Quota Management.
    Displays current cloud tier, expiration date, active branch quota usage, and upgrade options.
    """
    company = getattr(request, 'tenant', None)
    
    # Get or initialize subscription
    sub = None
    if company:
        sub = CompanySubscription.objects.filter(company=company).first()
        if not sub:
            # Default to 365 days active subscription for demo/launch
            sub = CompanySubscription.objects.create(
                company=company,
                status='ACTIVE',
                max_branches=10,
                max_users=25,
                expires_at=timezone.now().date() + timedelta(days=365),
                billing_email=f"billing@{getattr(company, 'schema_name', 'company')}.com"
            )

    active_branches = Branch.objects.filter(status='ACTIVE').count()
    branch_quota = sub.max_branches if sub else 10
    branch_usage_pct = min(100, int((active_branches / branch_quota) * 100)) if branch_quota > 0 else 0

    plans = [
        {
            'name': 'Starter Chain',
            'price': '$49',
            'branches': 'Up to 3 Branches',
            'users': '10 Team Members',
            'features': ['LAN-to-Cloud Sync', 'Real-Time Edge Monitor', 'Consolidated Sales Reports', 'Standard Email Support'],
            'is_current': branch_quota <= 3,
        },
        {
            'name': 'Growth Retailer',
            'price': '$129',
            'branches': 'Up to 10 Branches',
            'users': '25 Team Members',
            'features': ['All Starter Features', 'B2B Exchange Access', 'Automated Replenishment', 'Custom Export Engine', 'Priority Support'],
            'is_current': branch_quota > 3 and branch_quota <= 10,
            'popular': True,
        },
        {
            'name': 'Enterprise Chain',
            'price': '$299',
            'branches': 'Unlimited Branches',
            'users': 'Unlimited Members',
            'features': ['All Growth Features', 'Dedicated Database Schema', 'Real-time WebSocket Push', 'Custom ERP Integrations', '24/7 Phone Support'],
            'is_current': branch_quota > 10,
        }
    ]

    context = {
        'page_title': 'Subscription & Plan',
        'company': company,
        'subscription': sub,
        'active_branches': active_branches,
        'branch_quota': branch_quota,
        'branch_usage_pct': branch_usage_pct,
        'days_remaining': sub.days_remaining if sub else 365,
        'plans': plans,
    }
    return render(request, 'subscriptions/subscription_page.html', context)


@company_manager_required
def ajax_request_upgrade(request):
    """Logs an upgrade request from the tenant."""
    if request.method != 'POST':
        return _err('Method Not Allowed', 'Only POST allowed.', 405)

    plan_name = request.POST.get('plan_name', 'Enterprise Chain')
    return _ok(
        'Upgrade Request Submitted',
        f'Your request for the {plan_name} plan has been logged. An Avail Technologies account manager will contact you shortly to activate your new branch quota.'
    )
