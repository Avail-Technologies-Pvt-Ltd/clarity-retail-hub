import json
from django.test import TestCase, Client
from branches.models import Branch, InterBranchTransferBuffer
from sync_gateway.models import ProcessedEvent


class SyncGatewayTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.main_branch = Branch.objects.create(
            name="Main First Street",
            branch_code="HRE-CBD-01",
            is_main_branch=True,
            status="ACTIVE"
        )
        self.second_branch = Branch.objects.create(
            name="Avondale Branch",
            branch_code="HRE-AVN-02",
            is_main_branch=False,
            status="ACTIVE"
        )

    def test_sync_ping_hardware_binding_and_anti_theft(self):
        """First ping binds hardware; subsequent ping with mismatched hardware is rejected (403)."""
        token = self.second_branch.sync_token
        hw_hash_1 = "cpu-intel-i7-motherboard-hash-1111"

        # 1. First ping binds the terminal
        res1 = self.client.post(
            '/sync/ping/',
            data=json.dumps({'version': 'v2.7.2'}),
            content_type='application/json',
            HTTP_X_BRANCH_TOKEN=token,
            HTTP_X_HARDWARE_FINGERPRINT=hw_hash_1
        )
        self.assertEqual(res1.status_code, 200)
        self.second_branch.refresh_from_db()
        self.assertEqual(self.second_branch.pairing_status, 'PAIRED_LOCKED')
        self.assertEqual(self.second_branch.hardware_fingerprint, hw_hash_1)

        # 2. Rogue machine attempts to ping with same token but different hardware fingerprint
        hw_hash_rogue = "cpu-amd-stolen-laptop-hash-9999"
        res2 = self.client.post(
            '/sync/ping/',
            data=json.dumps({'version': 'v2.7.2'}),
            content_type='application/json',
            HTTP_X_BRANCH_TOKEN=token,
            HTTP_X_HARDWARE_FINGERPRINT=hw_hash_rogue
        )
        self.assertEqual(res2.status_code, 403)
        data = res2.json()
        self.assertEqual(data.get('approval'), 'REJECTED')
        self.assertIn('Hardware signature mismatch', data.get('message', ''))

    def test_main_branch_product_conflict_priority(self):
        """
        When Main Branch creates a product, non-main branch syncs cannot
        overwrite core product attributes (name, barcode, category).
        """
        product_gid = "prod-uuid-spark-plug-101"

        # Step 1: Main branch syncs the authoritative product
        main_payload = {
            'events': [
                {
                    'global_id': product_gid,
                    'entity_type': 'Product',
                    'data': {
                        'name': 'NGK Spark Plug BKR6E-11',
                        'barcode': '087295127568',
                        'category': 'Ignition & Electrical',
                        'selling_price': 4.50,
                        'cost_price': 2.20
                    }
                }
            ]
        }
        res1 = self.client.post(
            '/sync/push/',
            data=json.dumps(main_payload),
            content_type='application/json',
            HTTP_X_BRANCH_TOKEN=self.main_branch.sync_token
        )
        self.assertEqual(res1.status_code, 200)

        # Step 2: Second branch attempts to push conflicting name/barcode for same UUID
        second_payload = {
            'events': [
                {
                    'global_id': product_gid,
                    'entity_type': 'Product',
                    'data': {
                        'name': 'Spark Plug Generic (Typo)',
                        'barcode': '999999999999',
                        'category': 'Unknown Spares',
                        'selling_price': 5.00,
                        'cost_price': 2.50
                    }
                }
            ]
        }
        res2 = self.client.post(
            '/sync/push/',
            data=json.dumps(second_payload),
            content_type='application/json',
            HTTP_X_BRANCH_TOKEN=self.second_branch.sync_token
        )
        self.assertEqual(res2.status_code, 200)

        # Verify second branch event was ingested with Main Branch attributes preserved
        second_ev = ProcessedEvent.objects.get(global_id=product_gid, branch=self.second_branch)
        self.assertEqual(second_ev.payload_data['name'], 'NGK Spark Plug BKR6E-11')
        self.assertEqual(second_ev.payload_data['barcode'], '087295127568')
        self.assertEqual(second_ev.payload_data['category'], 'Ignition & Electrical')

    def test_interbranch_transfer_buffer_and_pending_pull(self):
        """Branch A dispatches stock -> Hub buffers -> Branch B pulls pending transfer."""
        dispatch_payload = {
            'events': [
                {
                    'global_id': 'transfer-event-uuid-001',
                    'entity_type': 'InterBranchTransfer',
                    'data': {
                        'action': 'DISPATCH',
                        'reference': 'TR-2026-999',
                        'destination_branch_code': 'HRE-AVN-02',
                        'product_uuid': 'prod-oil-filter',
                        'product_name': 'Toyota Oil Filter',
                        'quantity': 10.0,
                        'notes': 'Urgent stock transfer request'
                    }
                }
            ]
        }

        # Branch A dispatches
        res_push = self.client.post(
            '/sync/push/',
            data=json.dumps(dispatch_payload),
            content_type='application/json',
            HTTP_X_BRANCH_TOKEN=self.main_branch.sync_token
        )
        self.assertEqual(res_push.status_code, 200)

        # Verify record exists in buffer with IN_TRANSIT status
        transfer = InterBranchTransferBuffer.objects.get(reference='TR-2026-999')
        self.assertEqual(transfer.status, 'IN_TRANSIT')
        self.assertEqual(transfer.quantity, 10.0)

        # Branch B pulls pending transfers
        res_pull = self.client.get(
            '/sync/transfers/pending/',
            HTTP_X_BRANCH_TOKEN=self.second_branch.sync_token
        )
        self.assertEqual(res_pull.status_code, 200)
        data = res_pull.json()
        self.assertEqual(data.get('count'), 1)
        self.assertEqual(data['transfers'][0]['reference'], 'TR-2026-999')
        self.assertEqual(data['transfers'][0]['quantity'], 10.0)

    def test_branches_pull_and_directory_sync_state_tracking(self):
        """Edge node pulls branch directory; Hub returns branches and updates BranchDirectorySyncState."""
        from branches.models import BranchDirectorySyncState

        res = self.client.get(
            '/sync/branches/pull/',
            HTTP_X_BRANCH_TOKEN=self.second_branch.sync_token
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        self.assertGreaterEqual(data['count'], 2)
        
        # Verify sync state was recorded on Hub
        sync_state = BranchDirectorySyncState.objects.get(subscriber_branch=self.second_branch)
        self.assertEqual(sync_state.last_synced_version, data['current_version'])

    def test_batch_centric_transfer_full_handshake_with_outgoing_status(self):
        """Full 3-way batch transfer handshake: Dispatch -> Buffer -> Receive ACK -> Outgoing status poll."""
        dispatch_payload = {
            'events': [
                {
                    'global_id': 'batch-transfer-001',
                    'entity_type': 'InterBranchTransfer',
                    'data': {
                        'action': 'DISPATCH',
                        'reference': 'TR-BATCH-888',
                        'destination_branch_code': 'HRE-AVN-02',
                        'product_uuid': 'prod-tomatoes-uuid',
                        'product_name': 'Fresh Roma Tomatoes',
                        'batch_number': 'LOT-TOM-2026-11-A',
                        'expiry_date': '2026-11-20',
                        'cost_price': 1.50,
                        'selling_price': 2.50,
                        'quantity': 25.0,
                        'notes': 'Fresh morning harvest delivery'
                    }
                }
            ]
        }

        # 1. Main branch dispatches batch
        res1 = self.client.post(
            '/sync/push/',
            data=json.dumps(dispatch_payload),
            content_type='application/json',
            HTTP_X_BRANCH_TOKEN=self.main_branch.sync_token
        )
        self.assertEqual(res1.status_code, 200)

        # Verify batch details buffered
        buffer_record = InterBranchTransferBuffer.objects.get(reference='TR-BATCH-888')
        self.assertEqual(buffer_record.batch_number, 'LOT-TOM-2026-11-A')
        self.assertEqual(str(buffer_record.expiry_date), '2026-11-20')
        self.assertEqual(buffer_record.quantity, 25.0)
        self.assertEqual(buffer_record.cost_price, 1.50)

        # 2. Destination pulls pending transfer with batch info
        res2 = self.client.get(
            '/sync/transfers/pending/',
            HTTP_X_BRANCH_TOKEN=self.second_branch.sync_token
        )
        self.assertEqual(res2.status_code, 200)
        pending_list = res2.json().get('transfers', [])
        target_item = next((t for t in pending_list if t['reference'] == 'TR-BATCH-888'), None)
        self.assertIsNotNone(target_item)
        self.assertEqual(target_item['batch_number'], 'LOT-TOM-2026-11-A')

        # 3. Destination confirms receipt
        ack_payload = {
            'events': [
                {
                    'global_id': 'ack-batch-transfer-001',
                    'entity_type': 'InterBranchTransfer',
                    'data': {
                        'action': 'RECEIVE',
                        'reference': 'TR-BATCH-888',
                        'qty_received': 25.0,
                        'received_by': 'Store Receiver Tinashe',
                    }
                }
            ]
        }
        res3 = self.client.post(
            '/sync/push/',
            data=json.dumps(ack_payload),
            content_type='application/json',
            HTTP_X_BRANCH_TOKEN=self.second_branch.sync_token
        )
        self.assertEqual(res3.status_code, 200)

        # 4. Source branch queries outgoing status and gets confirmed receipt
        res4 = self.client.get(
            '/sync/transfers/outgoing-status/',
            HTTP_X_BRANCH_TOKEN=self.main_branch.sync_token
        )
        self.assertEqual(res4.status_code, 200)
        outgoing_list = res4.json().get('transfers', [])
        confirmed_item = next((t for t in outgoing_list if t['reference'] == 'TR-BATCH-888'), None)
        self.assertIsNotNone(confirmed_item)
        self.assertEqual(confirmed_item['status'], 'RECEIVED')
        self.assertEqual(confirmed_item['received_by'], 'Store Receiver Tinashe')
        self.assertEqual(confirmed_item['batch_number'], 'LOT-TOM-2026-11-A')
