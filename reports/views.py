import csv
import json
from datetime import datetime, timedelta, date
from decimal import Decimal
from django.shortcuts import render
from django.http import HttpResponse
from django.utils import timezone
from branches.models import Branch, InterBranchTransferBuffer
from sync_gateway.models import ProcessedEvent
from .models import DailyBranchSummary, ReportExport
from retail_hub.decorators import staff_required, supervisor_required


def _parse_date_bounds(request):
    """
    Computes effective start and end dates from timeframe parameters.
    Supports:
      - 'daily': single target date
      - 'weekly': Monday-Sunday range for the week containing target date
      - 'monthly': 1st to last day of selected month/year
      - 'annual': Jan 1 to Dec 31 of selected year
    """
    period = request.GET.get('period') or request.GET.get('tab', 'daily')
    date_str = request.GET.get('date', '').strip()
    month_str = request.GET.get('month', '').strip()
    year_str = request.GET.get('year', '').strip()
    today = timezone.now().date()

    if period == 'weekly':
        target_date = today
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                target_date = today
        start_date = target_date - timedelta(days=target_date.weekday())
        end_date = start_date + timedelta(days=6)
        period_key = f"{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}"
        period_label = f"Week of {start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')}"
        return start_date, end_date, 'weekly', period_key, period_label

    elif period == 'monthly':
        y = today.year
        m = today.month
        if year_str:
            try: y = int(year_str)
            except ValueError: pass
        if month_str:
            try: m = int(month_str)
            except ValueError: pass
        start_date = date(y, m, 1)
        next_month = date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
        end_date = next_month - timedelta(days=1)
        return start_date, end_date, 'monthly', f"{y}-{m:02d}", start_date.strftime('%B %Y')

    elif period == 'annual':
        y = today.year
        if year_str:
            try: y = int(year_str)
            except ValueError: pass
        start_date = date(y, 1, 1)
        end_date = date(y, 12, 31)
        return start_date, end_date, 'annual', str(y), f"Year {y}"

    else:
        target_date = today
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                target_date = today
        return target_date, target_date, 'daily', target_date.strftime('%Y-%m-%d'), target_date.strftime('%d %B %Y')


@staff_required
def reports_dashboard(request):
    """
    Consolidated Multi-Branch Cloud Reports & Buffer Analytics.
    Dynamic Calculation Architecture:
      - Daily Reports: aggregate DailyBranchSummary for target date (or fallback to ProcessedEvents)
      - Weekly Reports: sum DailyBranchSummary across 7 days (Mon-Sun) on demand
      - Monthly Reports: aggregate DailyBranchSummary across month days on demand
      - Annual Reports: aggregate DailyBranchSummary across 12 calendar months on demand
      - Stock & Valuation: real-time stock levels across stores and in-transit buffers
    """
    tenant = getattr(request, 'tenant', None)
    branches = Branch.objects.all().order_by('branch_code')

    # Selected tab: 'daily', 'weekly', 'monthly', 'annual', 'stock'
    active_tab = request.GET.get('tab', 'daily')
    if active_tab not in ['daily', 'weekly', 'monthly', 'annual', 'stock', 'users', 'sales']:
        active_tab = 'daily'

    # Branch scoping
    branch_param = request.GET.get('branch')
    if branch_param == 'ALL':
        active_branch_id = None
    elif branch_param:
        active_branch_id = branch_param
    else:
        active_branch_id = request.session.get('active_branch_id')

    selected_branch = None
    if active_branch_id:
        selected_branch = branches.filter(id=active_branch_id).first()

    # Pre-fetch DailyBranchSummary records
    summary_qs = DailyBranchSummary.objects.select_related('branch')
    if selected_branch:
        summary_qs = summary_qs.filter(branch=selected_branch)

    # Pre-fetch synced event collections for legacy fallback & stock matrix
    sales_qs = ProcessedEvent.objects.filter(entity_type='Sale').select_related('branch')
    expenses_qs = ProcessedEvent.objects.filter(entity_type='Expense').select_related('branch')
    products_qs = ProcessedEvent.objects.filter(entity_type='Product').select_related('branch')
    stocks_qs = ProcessedEvent.objects.filter(entity_type='Stock').select_related('branch')
    batches_qs = ProcessedEvent.objects.filter(entity_type='Batch').select_related('branch')

    if selected_branch:
        sales_qs = sales_qs.filter(branch=selected_branch)
        expenses_qs = expenses_qs.filter(branch=selected_branch)
        products_qs = products_qs.filter(branch=selected_branch)
        stocks_qs = stocks_qs.filter(branch=selected_branch)
        batches_qs = batches_qs.filter(branch=selected_branch)

    # Date parsing
    start_date, end_date, period_mode, period_key, period_label = _parse_date_bounds(request)
    today = timezone.now().date()

    # Navigation helpers for week
    prev_week_date = (start_date - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week_date = (start_date + timedelta(days=7)).strftime('%Y-%m-%d')

    # ─────────────────────────────────────────────────────────────────
    # 1. DAILY REPORT PROCESSING
    # ─────────────────────────────────────────────────────────────────
    daily_sales = []
    daily_gross = 0.0
    daily_vat = 0.0
    daily_expenses_total = 0.0
    daily_cashier_map = {}
    daily_branch_map = {}
    daily_tender_map = {'USD Cash': 0.0, 'ZiG': 0.0, 'Swipe / Card': 0.0, 'Other': 0.0}
    daily_sales_count = 0

    # Check DailyBranchSummary first (Platform calculation philosophy)
    daily_summaries = list(summary_qs.filter(summary_date=start_date))

    if daily_summaries:
        daily_gross = float(sum(s.gross_sales for s in daily_summaries))
        daily_vat = float(sum(s.vat_amount for s in daily_summaries))
        daily_expenses_total = float(sum(s.expenses_total for s in daily_summaries))
        daily_sales_count = sum(s.sales_count for s in daily_summaries)

        for s in daily_summaries:
            b_code = s.branch.branch_code if s.branch else 'HQ'
            b_name = s.branch.name if s.branch else 'Store'

            daily_branch_map[b_code] = {
                'code': b_code,
                'name': b_name,
                'count': s.sales_count,
                'gross': float(s.gross_sales)
            }

            for c in (s.cashier_breakdown or []):
                c_name = c.get('cashier', 'Store Cashier')
                c_cnt = int(c.get('count', 0))
                c_gross = float(c.get('gross', 0.0))
                if c_name not in daily_cashier_map:
                    daily_cashier_map[c_name] = {'cashier': c_name, 'count': 0, 'gross': 0.0}
                daily_cashier_map[c_name]['count'] += c_cnt
                daily_cashier_map[c_name]['gross'] += c_gross

            for method, amt in (s.tender_breakdown or {}).items():
                daily_tender_map[method] = round(daily_tender_map.get(method, 0.0) + float(amt), 2)

            daily_sales.append({
                'reference': f"SUM-{s.branch.branch_code}-{start_date.strftime('%Y%m%d')}",
                'branch_code': b_code,
                'branch_name': b_name,
                'total': float(s.gross_sales),
                'vat': float(s.vat_amount),
                'cashier': f"{s.sales_count} Transactions",
                'is_fiscal': s.fiscalised_count > 0,
                'time': 'Daily Summary',
            })
    else:
        # Fallback to individual ProcessedEvent items
        for ev in sales_qs.order_by('-processed_at'):
            data = ev.payload_data or {}
            tot = float(data.get('total') or data.get('total_amount') or 0.0)
            subtot = float(data.get('subtotal') or (tot / 1.15 if tot else 0.0))
            vat = float(data.get('vat_amount') or (tot - subtot if tot else 0.0))
            raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
            sale_date_str = raw_date[:10]

            try:
                sale_date_obj = datetime.strptime(sale_date_str, '%Y-%m-%d').date()
            except ValueError:
                sale_date_obj = ev.processed_at.date()

            if sale_date_obj != start_date:
                continue

            ref = str(data.get('reference') or data.get('sale_number') or f"SALE-{ev.id}")
            cashier = str(data.get('cashier') or 'Store Cashier').strip() or 'Store Cashier'
            is_fiscal = bool(data.get('is_fiscalised', False))
            b_code = ev.branch.branch_code if ev.branch else 'HQ'
            b_name = ev.branch.name if ev.branch else 'Store'

            daily_gross += tot
            daily_vat += vat
            daily_sales_count += 1

            if cashier not in daily_cashier_map:
                daily_cashier_map[cashier] = {'cashier': cashier, 'count': 0, 'gross': 0.0}
            daily_cashier_map[cashier]['count'] += 1
            daily_cashier_map[cashier]['gross'] += tot

            if b_code not in daily_branch_map:
                daily_branch_map[b_code] = {'code': b_code, 'name': b_name, 'count': 0, 'gross': 0.0}
            daily_branch_map[b_code]['count'] += 1
            daily_branch_map[b_code]['gross'] += tot

            daily_sales.append({
                'reference': ref,
                'branch_code': b_code,
                'branch_name': b_name,
                'total': round(tot, 2),
                'vat': round(vat, 2),
                'cashier': cashier,
                'is_fiscal': is_fiscal,
                'time': raw_date[11:16] if 'T' in raw_date else '12:00',
            })

        for ev in expenses_qs:
            data = ev.payload_data or {}
            amt = float(data.get('amount') or 0.0)
            raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
            exp_date_str = raw_date[:10]
            try:
                exp_date_obj = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
            except ValueError:
                exp_date_obj = ev.processed_at.date()

            if exp_date_obj == start_date:
                daily_expenses_total += amt

    daily_net_cashflow = daily_gross - daily_expenses_total

    # Filter daily expenses detail list (if present)
    daily_expenses_list = []
    for ev in expenses_qs:
        data = ev.payload_data or {}
        amt = float(data.get('amount') or 0.0)
        raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
        try:
            exp_date_obj = datetime.strptime(raw_date[:10], '%Y-%m-%d').date()
        except ValueError:
            exp_date_obj = ev.processed_at.date()

        if exp_date_obj == start_date:
            daily_expenses_list.append({
                'name': data.get('name', 'Petty Cash / Store Expense'),
                'amount': round(amt, 2),
                'branch_code': ev.branch.branch_code if ev.branch else 'HQ',
            })

    # ─────────────────────────────────────────────────────────────────
    # 2. WEEKLY REPORT PROCESSING (DYNAMIC CALCULATION ON DEMAND)
    # ─────────────────────────────────────────────────────────────────
    weekly_gross = 0.0
    weekly_vat = 0.0
    weekly_expenses_total = 0.0
    weekly_sales_count = 0
    weekly_days = []
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    weekly_summaries = list(summary_qs.filter(summary_date__gte=start_date, summary_date__lte=end_date))
    has_weekly_summaries = len(weekly_summaries) > 0

    for i in range(7):
        day_date = start_date + timedelta(days=i)
        day_str = day_date.strftime('%Y-%m-%d')
        day_name = day_names[day_date.weekday()]

        if has_weekly_summaries:
            day_sums = [s for s in weekly_summaries if s.summary_date == day_date]
            d_count = sum(s.sales_count for s in day_sums)
            d_gross = float(sum(s.gross_sales for s in day_sums))
            d_vat = float(sum(s.vat_amount for s in day_sums))
            d_exp = float(sum(s.expenses_total for s in day_sums))
            d_net = d_gross - d_exp
        else:
            # Fallback to ProcessedEvents when no summaries exist
            d_count = 0
            d_gross = 0.0
            d_vat = 0.0
            d_exp = 0.0
            for ev in sales_qs:
                data = ev.payload_data or {}
                raw_date = str(data.get('date_added') or ev.processed_at.isoformat())[:10]
                if raw_date == day_str:
                    tot = float(data.get('total') or 0.0)
                    d_count += 1
                    d_gross += tot
                    d_vat += float(data.get('vat_amount') or 0.0)
            for ev in expenses_qs:
                data = ev.payload_data or {}
                raw_date = str(data.get('date_added') or ev.processed_at.isoformat())[:10]
                if raw_date == day_str:
                    d_exp += float(data.get('amount') or 0.0)
            d_net = d_gross - d_exp

        weekly_gross += d_gross
        weekly_vat += d_vat
        weekly_expenses_total += d_exp
        weekly_sales_count += d_count
        weekly_days.append({
            'day_name': day_name,
            'date': day_str,
            'sales_count': d_count,
            'gross': round(d_gross, 2),
            'vat': round(d_vat, 2),
            'expenses': round(d_exp, 2),
            'net': round(d_net, 2)
        })

    weekly_net_profit = weekly_gross - weekly_expenses_total

    # ─────────────────────────────────────────────────────────────────
    # 3. MONTHLY REPORT PROCESSING (DYNAMIC CALCULATION ON DEMAND)
    # ─────────────────────────────────────────────────────────────────
    monthly_gross = 0.0
    monthly_vat = 0.0
    monthly_expenses_total = 0.0
    monthly_days_map = {}

    target_year = start_date.year if period_mode == 'monthly' else today.year
    target_month = start_date.month if period_mode == 'monthly' else today.month

    # Initialize all days of the month
    num_days = (date(target_year + (1 if target_month == 12 else 0), 1 if target_month == 12 else target_month + 1, 1) - timedelta(days=1)).day
    for d in range(1, num_days + 1):
        d_str = f"{target_year}-{target_month:02d}-{d:02d}"
        monthly_days_map[d_str] = {'day': d, 'date': d_str, 'sales_count': 0, 'gross': 0.0, 'vat': 0.0, 'expenses': 0.0, 'net': 0.0}

    monthly_summaries = list(summary_qs.filter(summary_date__year=target_year, summary_date__month=target_month))
    has_monthly_summaries = len(monthly_summaries) > 0

    if has_monthly_summaries:
        for s in monthly_summaries:
            d_str = s.summary_date.strftime('%Y-%m-%d')
            if d_str in monthly_days_map:
                monthly_days_map[d_str]['sales_count'] += s.sales_count
                monthly_days_map[d_str]['gross'] += float(s.gross_sales)
                monthly_days_map[d_str]['vat'] += float(s.vat_amount)
                monthly_days_map[d_str]['expenses'] += float(s.expenses_total)
                monthly_days_map[d_str]['net'] = monthly_days_map[d_str]['gross'] - monthly_days_map[d_str]['expenses']
                monthly_gross += float(s.gross_sales)
                monthly_vat += float(s.vat_amount)
                monthly_expenses_total += float(s.expenses_total)
    else:
        # Fallback to ProcessedEvents
        for ev in sales_qs:
            data = ev.payload_data or {}
            tot = float(data.get('total') or data.get('total_amount') or 0.0)
            subtot = float(data.get('subtotal') or (tot / 1.15 if tot else 0.0))
            vat = float(data.get('vat_amount') or (tot - subtot if tot else 0.0))
            raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
            d_str = raw_date[:10]

            if d_str in monthly_days_map:
                monthly_days_map[d_str]['sales_count'] += 1
                monthly_days_map[d_str]['gross'] += tot
                monthly_days_map[d_str]['vat'] += vat
                monthly_days_map[d_str]['net'] += tot
                monthly_gross += tot
                monthly_vat += vat

        for ev in expenses_qs:
            data = ev.payload_data or {}
            amt = float(data.get('amount') or 0.0)
            raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
            d_str = raw_date[:10]
            if d_str in monthly_days_map:
                monthly_days_map[d_str]['expenses'] += amt
                monthly_days_map[d_str]['net'] -= amt
                monthly_expenses_total += amt

    monthly_net_profit = monthly_gross - monthly_expenses_total
    monthly_days_list = sorted(monthly_days_map.values(), key=lambda x: x['day'])

    # ─────────────────────────────────────────────────────────────────
    # 4. ANNUAL REPORT PROCESSING (DYNAMIC CALCULATION ON DEMAND)
    # ─────────────────────────────────────────────────────────────────
    annual_year = start_date.year if period_mode == 'annual' else today.year
    annual_gross = 0.0
    annual_vat = 0.0
    annual_expenses_total = 0.0
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    annual_months_map = {}
    for m_idx in range(1, 13):
        annual_months_map[m_idx] = {
            'month_num': m_idx,
            'month_name': month_names[m_idx - 1],
            'sales_count': 0,
            'gross': 0.0,
            'vat': 0.0,
            'expenses': 0.0,
            'net': 0.0
        }

    annual_summaries = list(summary_qs.filter(summary_date__year=annual_year))
    has_annual_summaries = len(annual_summaries) > 0

    if has_annual_summaries:
        for s in annual_summaries:
            m_idx = s.summary_date.month
            if m_idx in annual_months_map:
                annual_months_map[m_idx]['sales_count'] += s.sales_count
                annual_months_map[m_idx]['gross'] += float(s.gross_sales)
                annual_months_map[m_idx]['vat'] += float(s.vat_amount)
                annual_months_map[m_idx]['expenses'] += float(s.expenses_total)
                annual_months_map[m_idx]['net'] = annual_months_map[m_idx]['gross'] - annual_months_map[m_idx]['expenses']
                annual_gross += float(s.gross_sales)
                annual_vat += float(s.vat_amount)
                annual_expenses_total += float(s.expenses_total)
    else:
        # Fallback to ProcessedEvents
        for ev in sales_qs:
            data = ev.payload_data or {}
            tot = float(data.get('total') or 0.0)
            vat = float(data.get('vat_amount') or 0.0)
            raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
            try:
                d_obj = datetime.strptime(raw_date[:10], '%Y-%m-%d').date()
                if d_obj.year == annual_year and d_obj.month in annual_months_map:
                    annual_months_map[d_obj.month]['sales_count'] += 1
                    annual_months_map[d_obj.month]['gross'] += tot
                    annual_months_map[d_obj.month]['vat'] += vat
                    annual_months_map[d_obj.month]['net'] += tot
                    annual_gross += tot
                    annual_vat += vat
            except Exception:
                pass

        for ev in expenses_qs:
            data = ev.payload_data or {}
            amt = float(data.get('amount') or 0.0)
            raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
            try:
                d_obj = datetime.strptime(raw_date[:10], '%Y-%m-%d').date()
                if d_obj.year == annual_year and d_obj.month in annual_months_map:
                    annual_months_map[d_obj.month]['expenses'] += amt
                    annual_months_map[d_obj.month]['net'] -= amt
                    annual_expenses_total += amt
            except Exception:
                pass

    annual_net_profit = annual_gross - annual_expenses_total
    annual_months_list = [annual_months_map[i] for i in range(1, 13)]

    # ─────────────────────────────────────────────────────────────────
    # 5. STOCK & VALUATION PROCESSING
    # ─────────────────────────────────────────────────────────────────
    stock_qty_map = {}
    for ev in stocks_qs:
        data = ev.payload_data or {}
        p_name = (data.get('product_name') or '').strip()
        qty = float(data.get('quantity') or 0.0)
        stock_qty_map[p_name] = stock_qty_map.get(p_name, 0.0) + qty

    inventory_items = []
    total_units_on_hand = 0.0
    total_cost_val = 0.0
    total_retail_val = 0.0
    low_stock_count = 0
    out_of_stock_count = 0

    for ev in products_qs:
        data = ev.payload_data or {}
        name = (data.get('name') or '').strip()
        cat = (data.get('category') or 'General').strip()
        barcode = (data.get('barcode') or '').strip()
        cost_price = float(data.get('cost_price') or 0.0)
        selling_price = float(data.get('selling_price') or 0.0)
        b_code = ev.branch.branch_code if ev.branch else 'HQ'

        qty = stock_qty_map.get(name, 0.0)
        cost_v = qty * cost_price
        retail_v = qty * selling_price

        if qty <= 0:
            out_of_stock_count += 1
            status_tag = 'OUT_OF_STOCK'
        elif qty <= 10:
            low_stock_count += 1
            status_tag = 'LOW_STOCK'
        else:
            status_tag = 'IN_STOCK'

        total_units_on_hand += qty
        total_cost_val += cost_v
        total_retail_val += retail_v

        inventory_items.append({
            'name': name,
            'category': cat,
            'barcode': barcode,
            'branch_code': b_code,
            'quantity': qty,
            'cost_price': round(cost_price, 2),
            'selling_price': round(selling_price, 2),
            'retail_val': round(retail_v, 2),
            'status_tag': status_tag,
        })

    # Sort inventory
    inventory_items.sort(key=lambda x: (0 if x['status_tag'] in ['OUT_OF_STOCK', 'LOW_STOCK'] else 1, -x['retail_val']))

    # Context assembly
    context = {
        'page_title': 'Reports & Analytics',
        'tenant': tenant,
        'branches': branches,
        'active_tab': active_tab,
        'active_branch_id': active_branch_id,
        'selected_branch': selected_branch,
        'today_date': today.strftime('%Y-%m-%d'),
        'target_date': start_date.strftime('%Y-%m-%d'),
        'target_month': target_month,
        'target_year': target_year,
        'period_label': period_label,
        'prev_week_date': prev_week_date,
        'next_week_date': next_week_date,
        'currency_symbol': getattr(tenant, 'currency_symbol', '$'),

        # Daily
        'daily_gross': round(daily_gross, 2),
        'daily_vat': round(daily_vat, 2),
        'daily_expenses_total': round(daily_expenses_total, 2),
        'daily_net_cashflow': round(daily_net_cashflow, 2),
        'daily_sales': daily_sales[:50],
        'daily_sales_count': daily_sales_count,
        'daily_cashiers': sorted(daily_cashier_map.values(), key=lambda x: x['gross'], reverse=True),
        'daily_branches': sorted(daily_branch_map.values(), key=lambda x: x['gross'], reverse=True),
        'daily_expenses': daily_expenses_list,

        # Weekly (Dynamically calculated)
        'weekly_gross': round(weekly_gross, 2),
        'weekly_vat': round(weekly_vat, 2),
        'weekly_expenses_total': round(weekly_expenses_total, 2),
        'weekly_net_profit': round(weekly_net_profit, 2),
        'weekly_sales_count': weekly_sales_count,
        'weekly_days': weekly_days,

        # Monthly (Dynamically calculated)
        'monthly_gross': round(monthly_gross, 2),
        'monthly_vat': round(monthly_vat, 2),
        'monthly_expenses_total': round(monthly_expenses_total, 2),
        'monthly_net_profit': round(monthly_net_profit, 2),
        'monthly_days': monthly_days_list,

        # Annual (Dynamically calculated)
        'annual_year': annual_year,
        'annual_gross': round(annual_gross, 2),
        'annual_vat': round(annual_vat, 2),
        'annual_expenses_total': round(annual_expenses_total, 2),
        'annual_net_profit': round(annual_net_profit, 2),
        'annual_months': annual_months_list,

        # Stock
        'inventory_items': inventory_items[:50],
        'total_units_on_hand': total_units_on_hand,
        'total_cost_val': round(total_cost_val, 2),
        'total_retail_val': round(total_retail_val, 2),
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
    }

    return render(request, 'reports/reports_dashboard.html', context)


@staff_required
def stock_matrix_view(request):
    """
    Cross-Branch Live Stock Matrix.
    Displays product quantities across all store branches side-by-side,
    including items currently moving in the inter-branch transfer buffer.
    """
    tenant = getattr(request, 'tenant', None)
    branches = Branch.objects.all().order_by('branch_code')
    search_query = request.GET.get('search', '').strip().lower()

    # Pre-fetch products, stocks, and in-transit transfers
    products_qs = ProcessedEvent.objects.filter(entity_type='Product').select_related('branch')
    stocks_qs = ProcessedEvent.objects.filter(entity_type='Stock').select_related('branch')
    transfers_qs = InterBranchTransferBuffer.objects.filter(status='IN_TRANSIT').select_related('source_branch', 'destination_branch')

    # Build branch stock map: {product_name: {branch_id: qty}}
    branch_stock_map = {}
    for ev in stocks_qs:
        data = ev.payload_data or {}
        p_name = (data.get('product_name') or '').strip().lower()
        qty = float(data.get('quantity') or 0.0)
        b_id = str(ev.branch.id) if ev.branch else 'HQ'

        if p_name not in branch_stock_map:
            branch_stock_map[p_name] = {}
        branch_stock_map[p_name][b_id] = branch_stock_map[p_name].get(b_id, 0.0) + qty

    # Build in-transit map: {product_name: total_in_transit_qty}
    in_transit_map = {}
    for tr in transfers_qs:
        p_name = tr.product_name.strip().lower()
        in_transit_map[p_name] = in_transit_map.get(p_name, 0.0) + float(tr.quantity)

    # Build distinct product rows
    matrix_rows = []
    seen_products = set()

    for ev in products_qs:
        data = ev.payload_data or {}
        name = (data.get('name') or '').strip()
        p_key = name.lower()
        if not name or p_key in seen_products:
            continue

        barcode = (data.get('barcode') or '').strip()
        category = (data.get('category') or 'General').strip()
        selling_price = float(data.get('selling_price') or 0.0)

        if search_query:
            if search_query not in p_key and search_query not in barcode.lower():
                continue

        seen_products.add(p_key)

        # Quantities per branch
        p_stocks = branch_stock_map.get(p_key, {})
        row_branch_qtys = []
        total_chain_qty = 0.0

        for b in branches:
            b_qty = p_stocks.get(str(b.id), 0.0)
            total_chain_qty += b_qty
            row_branch_qtys.append({
                'branch_id': str(b.id),
                'branch_code': b.branch_code,
                'quantity': b_qty,
            })

        in_transit_qty = in_transit_map.get(p_key, 0.0)

        matrix_rows.append({
            'name': name,
            'barcode': barcode,
            'category': category,
            'selling_price': selling_price,
            'branch_qtys': row_branch_qtys,
            'total_qty': total_chain_qty,
            'in_transit_qty': in_transit_qty,
        })

    # Sort rows by total quantity descending
    matrix_rows.sort(key=lambda x: -x['total_qty'])

    context = {
        'page_title': 'Cross-Branch Live Stock Matrix',
        'tenant': tenant,
        'branches': branches,
        'matrix_rows': matrix_rows[:100],
        'total_products_count': len(matrix_rows),
        'search_query': search_query,
        'currency_symbol': getattr(tenant, 'currency_symbol', '$'),
    }
    return render(request, 'reports/stock_matrix.html', context)


@staff_required
def export_daily_csv(request):
    """Exports Daily Sales and Expense audit to CSV."""
    date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="daily_report_{date_str}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Reference', 'Store Code', 'Total ($)', 'VAT ($)', 'Cashier', 'Fiscalised', 'Time'])

    sales_qs = ProcessedEvent.objects.filter(entity_type='Sale').select_related('branch')
    for ev in sales_qs:
        data = ev.payload_data or {}
        raw_date = str(data.get('date_added') or ev.processed_at.isoformat())
        if raw_date[:10] == date_str:
            writer.writerow([
                data.get('reference', ''),
                ev.branch.branch_code if ev.branch else '',
                data.get('total', 0.0),
                data.get('vat_amount', 0.0),
                data.get('cashier', ''),
                data.get('is_fiscalised', False),
                raw_date[11:16] if 'T' in raw_date else '',
            ])
    return response


@staff_required
def export_stock_matrix_csv(request):
    """Exports cross-branch stock counts to CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="cross_branch_stock_matrix_{timezone.now().date().strftime("%Y-%m-%d")}.csv"'

    branches = Branch.objects.all().order_by('branch_code')
    writer = csv.writer(response)
    header = ['Product Name', 'Barcode', 'Category', 'Selling Price ($)'] + [f"{b.branch_code} Stock" for b in branches] + ['Total Chain Stock', 'In-Transit']
    writer.writerow(header)

    # Simplified export dump
    stocks_qs = ProcessedEvent.objects.filter(entity_type='Stock').select_related('branch')
    products_qs = ProcessedEvent.objects.filter(entity_type='Product')

    branch_stock_map = {}
    for ev in stocks_qs:
        data = ev.payload_data or {}
        p_name = (data.get('product_name') or '').strip().lower()
        qty = float(data.get('quantity') or 0.0)
        b_id = str(ev.branch.id) if ev.branch else 'HQ'
        if p_name not in branch_stock_map:
            branch_stock_map[p_name] = {}
        branch_stock_map[p_name][b_id] = branch_stock_map[p_name].get(b_id, 0.0) + qty

    seen = set()
    for ev in products_qs:
        data = ev.payload_data or {}
        name = (data.get('name') or '').strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        p_stocks = branch_stock_map.get(name.lower(), {})
        row = [
            name,
            data.get('barcode', ''),
            data.get('category', ''),
            data.get('selling_price', 0.0),
        ]
        total_chain = 0.0
        for b in branches:
            b_qty = p_stocks.get(str(b.id), 0.0)
            total_chain += b_qty
            row.append(b_qty)
        row.append(total_chain)
        row.append(0.0)
        writer.writerow(row)

    return response
