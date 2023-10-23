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
