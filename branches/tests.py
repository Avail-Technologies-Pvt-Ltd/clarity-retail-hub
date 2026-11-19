from django.test import TestCase, Client
from django.contrib.auth.models import User
from branches.models import Branch, InterBranchTransferBuffer


class BranchModelAndMainBranchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='root',
            email='root@gmail.com',
            password='toor'
        )
        self.client.force_login(self.superuser)

        self.branch_a = Branch.objects.create(
            name="First Street Branch",
            branch_code="HRE-CBD-01",
            is_main_branch=True,
            status="ACTIVE"
        )
        self.branch_b = Branch.objects.create(
            name="Avondale Branch",
            branch_code="HRE-AVN-02",
            is_main_branch=False,
            status="ACTIVE"
        )

    def test_single_main_branch_enforcement(self):
        """Setting branch_b as main must automatically unset branch_a."""
        self.assertTrue(self.branch_a.is_main_branch)
        self.assertFalse(self.branch_b.is_main_branch)

        self.branch_b.is_main_branch = True
        self.branch_b.save()

        self.branch_a.refresh_from_db()
        self.branch_b.refresh_from_db()

        self.assertFalse(self.branch_a.is_main_branch)
        self.assertTrue(self.branch_b.is_main_branch)

        # Count of main branches must strictly equal 1
        self.assertEqual(Branch.objects.filter(is_main_branch=True).count(), 1)

    def test_ajax_set_main_branch_endpoint(self):
        res = self.client.post(f'/branches/{self.branch_b.id}/set-main/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get('type'), 'success')

        self.branch_a.refresh_from_db()
        self.branch_b.refresh_from_db()
        self.assertFalse(self.branch_a.is_main_branch)
        self.assertTrue(self.branch_b.is_main_branch)

    def test_branch_update_endpoint(self):
        res = self.client.post(
            f'/branches/{self.branch_b.id}/update/',
            data={
                'name': 'Avondale Supermarket & Parts',
                'manager_name': 'Sarah Smith',
                'phone': '+263 77 999 8888',
                'address': 'King George Road, Avondale',
                'bank_name': 'Stanbic Bank',
                'bank_account_number': '914000123456',
                'is_headquarters': '1'
            }
        )
        self.assertEqual(res.status_code, 200)
        self.branch_b.refresh_from_db()
        self.assertEqual(self.branch_b.name, 'Avondale Supermarket & Parts')
        self.assertEqual(self.branch_b.manager_name, 'Sarah Smith')
        self.assertEqual(self.branch_b.bank_name, 'Stanbic Bank')
        self.assertTrue(self.branch_b.is_headquarters)

    def test_cannot_suspend_active_main_branch(self):
        """The authoritative main branch cannot be suspended while designated as main."""
        res = self.client.post(f'/branches/{self.branch_a.id}/toggle-status/')
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertEqual(data.get('type'), 'warning')
        self.assertIn('Cannot Suspend Main Branch', data.get('title', ''))

        # Non-main branch CAN be suspended cleanly
        res2 = self.client.post(f'/branches/{self.branch_b.id}/toggle-status/')
        self.assertEqual(res2.status_code, 200)
        self.branch_b.refresh_from_db()
        self.assertEqual(self.branch_b.status, 'SUSPENDED')

    def test_branch_creation_with_lan_key(self):
        branch = Branch.objects.create(
            name="Bulawayo Main Depot",
            branch_code="BYO-CBD-01",
            lan_branch_key="LAN-KEY-XYZ-1234",
            status="ACTIVE"
        )
        self.assertEqual(branch.lan_branch_key, "LAN-KEY-XYZ-1234")
        self.assertEqual(branch.pairing_status, "UNPAIRED")
        self.assertTrue(branch.sync_token.startswith("crh_edge_"))

    def test_interbranch_transfer_buffer_lifecycle(self):
        transfer = InterBranchTransferBuffer.objects.create(
            reference="TR-TEST-001",
            source_branch=self.branch_a,
            destination_branch=self.branch_b,
            product_uuid="prod-uuid-123",
            product_name="Toyota Oil Filter 90915-YZZE1",
            quantity=5.0,
            status="IN_TRANSIT"
        )
        self.assertEqual(transfer.status, "IN_TRANSIT")
        self.assertEqual(transfer.source_branch.branch_code, "HRE-CBD-01")
        self.assertEqual(transfer.destination_branch.branch_code, "HRE-AVN-02")
