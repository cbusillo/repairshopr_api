from django.db import models


class Product(models.Model):
    id = models.IntegerField(primary_key=True)
    price_cost = models.FloatField(null=True)
    price_retail = models.FloatField(null=True)
    condition = models.CharField(max_length=255, null=True)
    description = models.TextField(null=True)
    maintain_stock = models.BooleanField(null=True)
    name = models.CharField(max_length=255, null=True)
    quantity = models.IntegerField(null=True)
    warranty = models.CharField(max_length=255, null=True)
    sort_order = models.CharField(max_length=255, null=True)
    reorder_at = models.CharField(max_length=255, null=True)
    disabled = models.BooleanField(null=True)
    taxable = models.BooleanField(null=True)
    product_category = models.CharField(max_length=255, null=True)
    category_path = models.CharField(max_length=255, null=True)
    upc_code = models.CharField(max_length=255, null=True)
    discount_percent = models.CharField(max_length=255, null=True)
    warranty_template_id = models.CharField(max_length=255, null=True)
    qb_item_id = models.CharField(max_length=255, null=True)
    desired_stock_level = models.CharField(max_length=255, null=True)
    price_wholesale = models.FloatField(null=True)
    notes = models.TextField(null=True)
    tax_rate_id = models.CharField(max_length=255, null=True)
    physical_location = models.CharField(max_length=255, null=True)
    serialized = models.BooleanField(null=True)
    vendor_ids = models.CharField(max_length=255, null=True)
    long_description = models.TextField(null=True)
    location_quantities = models.CharField(max_length=255, null=True)
    photos = models.CharField(max_length=255, null=True)
