from django.db import models
import uuid
import secrets


class Branch(models.Model):
    """
    Branch registry model for Clarity Retail Hub (Tenant-scoped).
    Represents a physical store location running a Clarity Retail LAN edge node.
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('SUSPENDED', 'Suspended'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch_code = models.CharField(max_length=50, unique=True, help_text="Short branch identifier e.g. HRE-CBD-01")
    name = models.CharField(max_length=150, help_text="Store name e.g. First Street Branch")
    address = models.TextField(blank=True, null=True, help_text="Physical address of the store")
    phone = models.CharField(max_length=50, blank=True, null=True, help_text="Branch contact phone")
    email = models.EmailField(blank=True, null=True, help_text="Branch contact email")
    manager_name = models.CharField(max_length=150, blank=True, null=True, help_text="Branch manager full name")
    is_headquarters = models.BooleanField(default=False, help_text="Designates this branch as the central store/depot")
    is_main_branch = models.BooleanField(
        default=False,
        help_text="Designates the single source-of-truth branch for conflicting UUID records"
    )

    # Sync Edge Credentials & Anti-Theft Pairing
    PAIRING_STATUS_CHOICES = [
        ('UNPAIRED', 'Unpaired / Awaiting First Handshake'),
        ('PAIRED_LOCKED', 'Paired & Hardware Locked'),
        ('REVOKED', 'Key Revoked / Disabled'),
    ]

    lan_branch_key = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Auto-generated key from LAN installation"
    )
    hardware_fingerprint = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="SHA-256 fingerprint of physical terminal"
    )
    pairing_status = models.CharField(
        max_length=20,
        choices=PAIRING_STATUS_CHOICES,
        default='UNPAIRED'
    )
    paired_ip = models.GenericIPAddressField(blank=True, null=True)
    paired_at = models.DateTimeField(blank=True, null=True)

    sync_token = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        help_text="Secret authentication token used by Clarity Retail LAN node"
    )
    last_sync_at = models.DateTimeField(blank=True, null=True, help_text="Timestamp of last successful data sync")
    last_ping_at = models.DateTimeField(blank=True, null=True, help_text="Timestamp of last health heart-beat ping")
    edge_version = models.CharField(max_length=50, blank=True, null=True, help_text="Reported Retail LAN version")

    # Banking / Local Settlement Accounts
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    version = models.IntegerField(default=1, help_text="Monotonic version for edge branch directory synchronization")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ['branch_code']

    def __str__(self):
        main_badge = " (Main)" if self.is_main_branch else ""
        return f"{self.name} [{self.branch_code}]{main_badge}"

    def save(self, *args, **kwargs):
        if not self.sync_token:
            self.sync_token = f"crh_edge_{secrets.token_hex(20)}"
        if self.is_main_branch:
            # Guarantee strictly one main branch per tenant schema
            Branch.objects.exclude(id=self.id).update(is_main_branch=False)
        if self.pk:
            # Increment directory version on updates so edge nodes pull latest state
            self.version = (self.version or 0) + 1
        super().save(*args, **kwargs)

    def refresh_sync_token(self):
        self.sync_token = f"crh_edge_{secrets.token_hex(20)}"
        self.save(update_fields=['sync_token'])
        return self.sync_token


class PendingApproval(models.Model):
    """
    Branch-level transaction and operational action approval queue.
    Authorizes supervisors, branch managers, and company executives to review, approve, or reject edge transactions.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    APPROVAL_TYPES = [
        ('HIGH_VALUE_SALE', 'High-Value Sale Authorization'),
        ('SALE_REFUND', 'Customer Return / Refund Approval'),
        ('STOCK_ADJUSTMENT', 'Inventory Write-off / Stock Adjustment'),
        ('EXPENSE_CLAIM', 'Store Petty Cash / Expense Claim'),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='approvals')
    approval_type = models.CharField(max_length=50, choices=APPROVAL_TYPES, default='HIGH_VALUE_SALE')
    reference = models.CharField(max_length=100, help_text="Transaction reference / receipt number")
    requested_by = models.CharField(max_length=150, default='Store Cashier')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    details = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    reviewed_by = models.CharField(max_length=150, blank=True, null=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pending Approval"
        verbose_name_plural = "Pending Approvals"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_approval_type_display()} #{self.reference} ({self.status}) - {self.branch.branch_code}"


class BranchDirectorySyncState(models.Model):
    """
    Tracks which version of the tenant branch directory has been pulled
    by each physical edge branch.
    """
    subscriber_branch = models.OneToOneField(
        Branch,
        on_delete=models.CASCADE,
        related_name='directory_sync_state'
    )
    last_synced_version = models.IntegerField(default=0)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branch Directory Sync State"
        verbose_name_plural = "Branch Directory Sync States"

    def __str__(self):
        return f"{self.subscriber_branch.branch_code}: Synced v{self.last_synced_version}"


class InterBranchTransferBuffer(models.Model):
    """
    Asynchronous cloud buffer relaying stock transfers between physical branches.
    Branch A dispatches and marks IN_TRANSIT.
    Branch B pulls from buffer and confirms physical acceptance (RECEIVED).
    """
    STATUS_CHOICES = [
        ('IN_TRANSIT', 'Dispatched / In Transit'),
        ('RECEIVED', 'Received & Restocked at Destination'),
        ('PARTIAL_RECEIPT', 'Received with Discrepancy'),
        ('REJECTED', 'Rejected / Returned to Source'),
        ('CANCELLED', 'Recalled / Cancelled at Source'),
    ]

    transfer_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reference = models.CharField(max_length=100, help_text="e.g. TR-2026-001")
    source_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='outgoing_transfers')
    destination_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='incoming_transfers')
    product_uuid = models.CharField(max_length=128, help_text="Global ID of transferred product")
    product_name = models.CharField(max_length=200)

    # Lot & Batch Metadata (Batch-Centric Transfer)
    batch_number = models.CharField(max_length=200, blank=True, null=True, help_text="Physical batch or lot number")
    expiry_date = models.DateField(blank=True, null=True, help_text="Lot expiry date for perishables")
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)

    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Dispatched quantity")
    qty_received = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Confirmed received quantity")
    discrepancy_reason = models.TextField(blank=True, default='', help_text="Explanation if received qty differs from dispatched")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_TRANSIT')
    notes = models.TextField(blank=True, default='')
    dispatched_by = models.CharField(max_length=150, blank=True, default='Store Dispatcher')
    received_by = models.CharField(max_length=150, blank=True, null=True)
    dispatched_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Inter-Branch Transfer Buffer"
        verbose_name_plural = "Inter-Branch Transfer Buffers"
        ordering = ['-dispatched_at']

    def __str__(self):
        return f"[{self.status}] {self.product_name} x {self.quantity} ({self.source_branch.branch_code} -> {self.destination_branch.branch_code})"


