from django.test import TestCase, Client
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from branches.models import Branch, InterBranchTransferBuffer
from sync_gateway.models import ProcessedEvent
from reports.models import DailyBranchSummary
from django.contrib.auth.models import User


class ReportsDashboardAndMatrixTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.com',
            password='password123'
        )
        self.client.force_login(self.user)

        self.branch_a = Branch.objects.create(
            name="Harare Central",
            branch_code="HRE-01",
            is_main_branch=True,
            status="ACTIVE"
        )
        self.branch_b = Branch.objects.create(
            name="Bulawayo Hub",
            branch_code="BYO-02",
            is_main_branch=False,
            status="ACTIVE"
        )

        today_iso = timezone.now().isoformat()

        # Ingest Sales: $100 on Branch A, $50 on Branch B
        ProcessedEvent.objects.create(
            global_id="sale-001",
            entity_type="Sale",
            branch=self.branch_a,
            payload_data={'total': 100.0, 'vat_amount': 15.0, 'cashier': 'Tinashe', 'date_added': today_iso}
        )
        ProcessedEvent.objects.create(
            global_id="sale-002",
            entity_type="Sale",
            branch=self.branch_b,
            payload_data={'total': 50.0, 'vat_amount': 7.5, 'cashier': 'Sipho', 'date_added': today_iso}
        )

        # Ingest Expense: $30 on Branch A
        ProcessedEvent.objects.create(
            global_id="expense-001",
            entity_type="Expense",
            branch=self.branch_a,
            payload_data={'amount': 30.0, 'name': 'Generator Fuel', 'date_added': today_iso}
        )

        # Ingest Stock: 20 units on Branch A, 15 units on Branch B
        ProcessedEvent.objects.create(
            global_id="prod-brake-pads",
            entity_type="Product",
            branch=self.branch_a,
            payload_data={'name': 'Brake Pads D21', 'category': 'Braking', 'barcode': '112233', 'selling_price': 25.0}
        )
        ProcessedEvent.objects.create(
            global_id="stock-brake-pads-a",
            entity_type="Stock",
            branch=self.branch_a,
            payload_data={'product_name': 'Brake Pads D21', 'quantity': 20.0}
        )
        ProcessedEvent.objects.create(
            global_id="stock-brake-pads-b",
            entity_type="Stock",
            branch=self.branch_b,
            payload_data={'product_name': 'Brake Pads D21', 'quantity': 15.0}
        )

        # In-transit transfer: 5 units in transit from A to B
        InterBranchTransferBuffer.objects.create(
            reference="TR-001",
            source_branch=self.branch_a,
            destination_branch=self.branch_b,
            product_uuid="prod-brake-pads",
            product_name="Brake Pads D21",
            quantity=5.0,
            status="IN_TRANSIT"
        )

    def test_daily_report_cashflow_reconciliation(self):
        """Verifies Gross Sales ($150) - Expenses ($30) = Net Cash Flow ($120)."""
        res = self.client.get('/reports/?tab=daily')
        self.assertEqual(res.status_code, 200)
        ctx = res.context
        self.assertEqual(ctx['daily_gross'], 150.0)
        self.assertEqual(ctx['daily_expenses_total'], 30.0)
        self.assertEqual(ctx['daily_net_cashflow'], 120.0)
        self.assertEqual(ctx['daily_sales_count'], 2)

    def test_monthly_report_view(self):
        res = self.client.get('/reports/?tab=monthly')
        self.assertEqual(res.status_code, 200)
        ctx = res.context
        self.assertEqual(ctx['monthly_gross'], 150.0)
        self.assertEqual(ctx['monthly_expenses_total'], 30.0)
        self.assertEqual(ctx['monthly_net_profit'], 120.0)

    def test_annual_report_view(self):
        res = self.client.get('/reports/?tab=annual')
        self.assertEqual(res.status_code, 200)
        ctx = res.context
        self.assertEqual(ctx['annual_gross'], 150.0)
        self.assertEqual(ctx['annual_expenses_total'], 30.0)
        self.assertEqual(ctx['annual_net_profit'], 120.0)

    def test_cross_branch_stock_matrix_view(self):
        """Verifies matrix displays stock per branch (20 and 15) and in-transit (5)."""
        res = self.client.get('/reports/stock-matrix/')
        self.assertEqual(res.status_code, 200)
        ctx = res.context
        self.assertEqual(len(ctx['matrix_rows']), 1)
        row = ctx['matrix_rows'][0]
        self.assertEqual(row['name'], 'Brake Pads D21')
        self.assertEqual(row['total_qty'], 35.0)
        self.assertEqual(row['in_transit_qty'], 5.0)

    def test_csv_exports(self):
        res_daily = self.client.get('/reports/export/daily/')
        self.assertEqual(res_daily.status_code, 200)
        self.assertEqual(res_daily['Content-Type'], 'text/csv')

        res_matrix = self.client.get('/reports/export/stock-matrix/')
        self.assertEqual(res_matrix.status_code, 200)
        self.assertEqual(res_matrix['Content-Type'], 'text/csv')

    def test_daily_branch_summary_aggregation(self):
        """Verifies DailyBranchSummary ingestion is aggregated into the Daily report."""
        today = timezone.now().date()
        DailyBranchSummary.objects.create(
            branch=self.branch_a,
            summary_date=today,
            sales_count=5,
            gross_sales=Decimal('300.00'),
            vat_amount=Decimal('45.00'),
            net_sales=Decimal('255.00'),
            expenses_total=Decimal('50.00'),
            net_cashflow=Decimal('250.00'),
            fiscalised_count=5,
            cashier_breakdown=[{'cashier': 'Tinashe', 'count': 5, 'gross': 300.00}]
        )
        DailyBranchSummary.objects.create(
            branch=self.branch_b,
            summary_date=today,
            sales_count=3,
            gross_sales=Decimal('200.00'),
            vat_amount=Decimal('30.00'),
            net_sales=Decimal('170.00'),
            expenses_total=Decimal('20.00'),
            net_cashflow=Decimal('180.00'),
            fiscalised_count=3,
            cashier_breakdown=[{'cashier': 'Sipho', 'count': 3, 'gross': 200.00}]
        )

        res = self.client.get('/reports/?tab=daily')
        self.assertEqual(res.status_code, 200)
        ctx = res.context
        self.assertEqual(ctx['daily_gross'], 500.0)
        self.assertEqual(ctx['daily_vat'], 75.0)
        self.assertEqual(ctx['daily_expenses_total'], 70.0)
        self.assertEqual(ctx['daily_net_cashflow'], 430.0)
        self.assertEqual(ctx['daily_sales_count'], 8)

    def test_weekly_report_calculation_from_daily_summaries(self):
        """Verifies Weekly report dynamically calculates 7-day totals from DailyBranchSummary."""
        today = timezone.now().date()
        monday = today - timedelta(days=today.weekday())

        # Create summaries for Monday and Tuesday
        DailyBranchSummary.objects.create(
            branch=self.branch_a,
            summary_date=monday,
            sales_count=10,
            gross_sales=Decimal('500.00'),
            vat_amount=Decimal('75.00'),
            net_sales=Decimal('425.00'),
            expenses_total=Decimal('100.00'),
            net_cashflow=Decimal('400.00')
        )
        DailyBranchSummary.objects.create(
            branch=self.branch_a,
            summary_date=monday + timedelta(days=1),
            sales_count=8,
            gross_sales=Decimal('400.00'),
            vat_amount=Decimal('60.00'),
            net_sales=Decimal('340.00'),
            expenses_total=Decimal('50.00'),
            net_cashflow=Decimal('350.00')
        )

        res = self.client.get(f'/reports/?tab=weekly&date={monday.strftime("%Y-%m-%d")}')
        self.assertEqual(res.status_code, 200)
        ctx = res.context
        self.assertEqual(ctx['weekly_gross'], 900.0)
        self.assertEqual(ctx['weekly_vat'], 135.0)
        self.assertEqual(ctx['weekly_expenses_total'], 150.0)
        self.assertEqual(ctx['weekly_net_profit'], 750.0)
        self.assertEqual(ctx['weekly_sales_count'], 18)
        self.assertEqual(len(ctx['weekly_days']), 7)

    def test_monthly_and_annual_calculation_from_daily_summaries(self):
        """Verifies Monthly & Annual reports calculate dynamically from DailyBranchSummary."""
        today = timezone.now().date()
        DailyBranchSummary.objects.create(
            branch=self.branch_a,
            summary_date=today,
            sales_count=20,
            gross_sales=Decimal('1000.00'),
            vat_amount=Decimal('150.00'),
            net_sales=Decimal('850.00'),
            expenses_total=Decimal('200.00'),
            net_cashflow=Decimal('800.00')
        )

        res_monthly = self.client.get(f'/reports/?tab=monthly&year={today.year}&month={today.month}')
        self.assertEqual(res_monthly.status_code, 200)
        self.assertEqual(res_monthly.context['monthly_gross'], 1000.0)
        self.assertEqual(res_monthly.context['monthly_expenses_total'], 200.0)
        self.assertEqual(res_monthly.context['monthly_net_profit'], 800.0)

        res_annual = self.client.get(f'/reports/?tab=annual&year={today.year}')
        self.assertEqual(res_annual.status_code, 200)
        self.assertEqual(res_annual.context['annual_gross'], 1000.0)
        self.assertEqual(res_annual.context['annual_expenses_total'], 200.0)
        self.assertEqual(res_annual.context['annual_net_profit'], 800.0)
        self.assertEqual(len(res_annual.context['annual_months']), 12)
