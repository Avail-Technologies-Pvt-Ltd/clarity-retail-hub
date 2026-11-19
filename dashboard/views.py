from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from branches.models import Branch, InterBranchTransferBuffer
from reports.models import DailyBranchSummary
from sync_gateway.models import ProcessedEvent, SyncLog
from retail_hub.decorators import staff_required
from decimal import Decimal


@staff_required
def dashboard_home(request):
    """
    Tenant executive dashboard.
    Prioritizes the core pillars:
      1. Live Financial Pulse: Today, Week, Month, and Annual Performance.
      2. Branch-Correlated Breakdown: Sales and contribution per branch.
      3. Multi-Branch Store Network: Single Main Branch Authority and edge online presence.
      4. Inter-Branch Stock Transfer Buffer: Live in-transit dispatches between stores.
    """
    tenant = getattr(request, 'tenant', None)
    branches = Branch.objects.all().order_by('branch_code')
    active_branches = branches.filter(status='ACTIVE')
    main_branch = branches.filter(is_main_branch=True).first()

    active_branch_id = request.session.get('active_branch_id')
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    # 1. Financial KPIs from DailyBranchSummary across periods
    summaries_qs = DailyBranchSummary.objects.all().select_related('branch')
    if active_branch_id:
        summaries_qs = summaries_qs.filter(branch_id=active_branch_id)

    # Today
    today_summaries = summaries_qs.filter(summary_date=today)
    today_gross = float(sum((s.gross_sales for s in today_summaries), Decimal('0.00')))
    today_sales_count = sum(s.sales_count for s in today_summaries)
    today_net_cashflow = float(sum((s.net_cashflow for s in today_summaries), Decimal('0.00')))
    today_expenses = float(sum((s.expenses_total for s in today_summaries), Decimal('0.00')))

    # This Week (WTD)
    week_summaries = summaries_qs.filter(summary_date__gte=week_start, summary_date__lte=today)
    week_gross = float(sum((s.gross_sales for s in week_summaries), Decimal('0.00')))
    week_sales_count = sum(s.sales_count for s in week_summaries)
    week_net_cashflow = float(sum((s.net_cashflow for s in week_summaries), Decimal('0.00')))
    week_expenses = float(sum((s.expenses_total for s in week_summaries), Decimal('0.00')))

    # This Month (MTD)
    month_summaries = summaries_qs.filter(summary_date__gte=month_start, summary_date__lte=today)
    month_gross = float(sum((s.gross_sales for s in month_summaries), Decimal('0.00')))
    month_sales_count = sum(s.sales_count for s in month_summaries)
    month_net_cashflow = float(sum((s.net_cashflow for s in month_summaries), Decimal('0.00')))
    month_expenses = float(sum((s.expenses_total for s in month_summaries), Decimal('0.00')))

    # This Year (YTD)
    year_summaries = summaries_qs.filter(summary_date__gte=year_start, summary_date__lte=today)
    year_gross = float(sum((s.gross_sales for s in year_summaries), Decimal('0.00')))
    year_sales_count = sum(s.sales_count for s in year_summaries)
    year_net_cashflow = float(sum((s.net_cashflow for s in year_summaries), Decimal('0.00')))
    year_expenses = float(sum((s.expenses_total for s in year_summaries), Decimal('0.00')))

    # Fallback to legacy ProcessedEvent if no DailyBranchSummary records exist yet
    if not summaries_qs.exists():
        sales_events = ProcessedEvent.objects.filter(entity_type='Sale')
        if active_branch_id:
            sales_events = sales_events.filter(branch_id=active_branch_id)
        legacy_count = sales_events.count()
        legacy_gross = 0.0
        for ev in sales_events:
            d = ev.payload_data or {}
            legacy_gross += float(d.get('total') or d.get('total_amount') or 0.0)
        today_gross = legacy_gross
        today_sales_count = legacy_count
        today_net_cashflow = legacy_gross
        week_gross = legacy_gross
        week_sales_count = legacy_count
        week_net_cashflow = legacy_gross
        month_gross = legacy_gross
        month_sales_count = legacy_count
        month_net_cashflow = legacy_gross
        year_gross = legacy_gross
        year_sales_count = legacy_count
        year_net_cashflow = legacy_gross

    # 2. Correlated Branch Breakdown (Essential for Mobile & Executive Pulse)
    branch_performance = []
    for b in branches:
        b_today = [s for s in today_summaries if s.branch_id == b.id]
        b_today_gross = float(sum((s.gross_sales for s in b_today), Decimal('0.00')))
        b_today_count = sum(s.sales_count for s in b_today)

        b_week = [s for s in week_summaries if s.branch_id == b.id]
        b_week_gross = float(sum((s.gross_sales for s in b_week), Decimal('0.00')))
        b_week_count = sum(s.sales_count for s in b_week)

        b_month = [s for s in month_summaries if s.branch_id == b.id]
        b_month_gross = float(sum((s.gross_sales for s in b_month), Decimal('0.00')))
        b_month_count = sum(s.sales_count for s in b_month)

        b_year = [s for s in year_summaries if s.branch_id == b.id]
        b_year_gross = float(sum((s.gross_sales for s in b_year), Decimal('0.00')))
        b_year_count = sum(s.sales_count for s in b_year)

        pct_today = round((b_today_gross / today_gross * 100), 1) if today_gross > 0 else 0
        pct_week = round((b_week_gross / week_gross * 100), 1) if week_gross > 0 else 0
        pct_month = round((b_month_gross / month_gross * 100), 1) if month_gross > 0 else 0
        pct_year = round((b_year_gross / year_gross * 100), 1) if year_gross > 0 else 0

        branch_performance.append({
            'branch': b,
            'today_gross': b_today_gross,
            'today_count': b_today_count,
            'pct_today': pct_today,
            'week_gross': b_week_gross,
            'week_count': b_week_count,
            'pct_week': pct_week,
            'month_gross': b_month_gross,
            'month_count': b_month_count,
            'pct_month': pct_month,
            'year_gross': b_year_gross,
            'year_count': b_year_count,
            'pct_year': pct_year,
        })

    # 3. Inter-Branch Stock Buffer Activity
    buffer_qs = InterBranchTransferBuffer.objects.select_related('source_branch', 'destination_branch')
    if active_branch_id:
        buffer_qs = buffer_qs.filter(destination_branch_id=active_branch_id)

    in_transit_count = buffer_qs.filter(status='IN_TRANSIT').count()
    completed_transfers_count = buffer_qs.filter(status='RECEIVED').count()
    recent_transfers = buffer_qs.order_by('-dispatched_at')[:6]

    # 4. Recent Daily Summaries Feed (Authoritative daily records)
    recent_summaries = summaries_qs.order_by('-summary_date')[:6]

    # 5. Catalog & Live Matrix Items
    total_products_synced = ProcessedEvent.objects.filter(entity_type='Product').count()

    context = {
        'company': tenant,
        'branches': branches,
        'main_branch': main_branch,
        'total_branches_count': branches.count(),
        'active_branches_count': active_branches.count(),

        # Real-time Prioritized Financial Metrics across All Periods
        'today_gross': today_gross,
        'today_sales_count': today_sales_count,
        'today_net_cashflow': today_net_cashflow,
        'today_expenses': today_expenses,

        'week_gross': week_gross,
        'week_sales_count': week_sales_count,
        'week_net_cashflow': week_net_cashflow,
        'week_expenses': week_expenses,

        'month_gross': month_gross,
        'month_sales_count': month_sales_count,
        'month_net_cashflow': month_net_cashflow,
        'month_expenses': month_expenses,

        'year_gross': year_gross,
        'year_sales_count': year_sales_count,
        'year_net_cashflow': year_net_cashflow,
        'year_expenses': year_expenses,

        # Correlated Branch Breakdown
        'branch_performance': branch_performance,

        # Aliases for compatibility
        'mtd_gross': month_gross,
        'mtd_sales_count': month_sales_count,
        'total_gross_revenue': round(year_gross, 2),
        'total_sales_count': year_sales_count,

        # Inter-Branch Stock Buffer
        'in_transit_count': in_transit_count,
        'completed_transfers_count': completed_transfers_count,
        'recent_transfers': recent_transfers,

        # Feeds & Catalog
        'recent_summaries': recent_summaries,
        'total_products_synced': total_products_synced,
        'currency_symbol': getattr(tenant, 'currency_symbol', '$'),
    }
    return render(request, 'dashboard/dashboard.html', context)
