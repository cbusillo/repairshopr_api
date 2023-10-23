from django.db import models


class Estimate(models.Model):
    id = models.IntegerField(primary_key=True)
    customer_id = models.IntegerField(null=True)
    customer_business_then_name = models.CharField(max_length=255, null=True)
    number = models.CharField(max_length=255, null=True)
    status = models.CharField(max_length=255, null=True)
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    date = models.DateTimeField(null=True)
    subtotal = models.FloatField(null=True)
    total = models.FloatField(null=True)
    tax = models.FloatField(null=True)
    ticket_id = models.IntegerField(null=True)
    pdf_url = models.CharField(max_length=255, null=True)
    location_id = models.IntegerField(null=True)
    invoice_id = models.IntegerField(null=True)
    employee = models.CharField(max_length=255, null=True)

    def __str__(self) -> str:
        return f"{self.id} - {self.customer_business_then_name} - {self.status} - {self.total} - {self.employee}"


# noinspection DuplicatedCode
class EstimateLineItem(models.Model):
    id = models.IntegerField(primary_key=True)
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    item = models.CharField(max_length=255, null=True)
    name = models.CharField(max_length=255, null=True)
    cost = models.FloatField(null=True)
    price = models.FloatField(null=True)
    quantity = models.FloatField(null=True)
    product_id = models.IntegerField(null=True)
    taxable = models.BooleanField(null=True)
    discount_percent = models.FloatField(null=True)
    position = models.IntegerField(null=True)
    invoice_bundle_id = models.IntegerField(null=True)
    discount_dollars = models.FloatField(null=True)
    product_category = models.CharField(max_length=255, null=True)

    parent_estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name="line_items", null=True)
