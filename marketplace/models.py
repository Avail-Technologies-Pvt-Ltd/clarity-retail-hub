from django.db import models


class MarketplaceProfile(models.Model):
    """
    Tenant-level B2B Marketplace participation configuration.
    Tenants are private ERP users by default; opt-in enables B2B trade.
    """
    is_opted_in = models.BooleanField(default=False, help_text="Opt into Clarity B2B Marketplace discovery")
    company_tagline = models.CharField(max_length=255, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=50, blank=True, default='')
    allow_wholesaler_discovery = models.BooleanField(default=True, help_text="Allow certified wholesalers to send stock quotes")
    date_opted_in = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Marketplace Profile"
        verbose_name_plural = "Marketplace Profiles"

    def __str__(self):
        return f"Marketplace Profile (Opted-in: {self.is_opted_in})"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class StockRequest(models.Model):
    """
    Retailer Stock Order / Procurement Request.
    Links directly to Clarity Exchange global commodities:
    - Verified Master Product UUID
    - Verified Supplier UUID
    - Optional Verified Transporter UUID
    """
    STATUS_CHOICES = [
        ('OPEN', 'Open for Quotes'),
        ('ORDER_PLACED', 'Order Placed with Supplier'),
        ('IN_TRANSIT', 'In Transit with Transporter'),
        ('DELIVERED', 'Delivered & Received'),
        ('FULFILLED', 'Fulfilled'),
        ('CANCELLED', 'Cancelled'),
    ]

    reference = models.CharField(max_length=50, unique=True)
    item_name = models.CharField(max_length=200)
    
    # Global References from Clarity Exchange
    global_product_id = models.UUIDField(null=True, blank=True, help_text="Verified MasterProduct UUID from Clarity Exchange")
    global_sku = models.CharField(max_length=64, blank=True, default='')
    supplier_id = models.UUIDField(null=True, blank=True, help_text="Verified Supplier NetworkEntity UUID")
    supplier_name = models.CharField(max_length=255, blank=True, default='')
    transporter_id = models.UUIDField(null=True, blank=True, help_text="Verified Transporter NetworkEntity UUID")
    transporter_name = models.CharField(max_length=255, blank=True, default='')

    category = models.CharField(max_length=100, blank=True, default='General Goods')
    quantity_needed = models.IntegerField(default=1)
    target_unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default='USD')
    delivery_deadline = models.DateField(null=True, blank=True)
    preferred_location = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock Order Request"
        verbose_name_plural = "Stock Order Requests"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} - {self.item_name} ({self.quantity_needed} units)"
