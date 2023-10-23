from django.db import models


class Payment(models.Model):
    id = models.IntegerField(primary_key=True)
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    success = models.BooleanField(null=True)
    payment_amount = models.FloatField(null=True)
    invoice_ids = models.CharField(max_length=255, null=True)
    ref_num = models.CharField(max_length=255, null=True)
    applied_at = models.DateTimeField(null=True)
    payment_method = models.CharField(max_length=255, null=True)
    transaction_response = models.CharField(max_length=255, null=True)
    signature_date = models.DateTimeField(null=True)
    customer_id = models.IntegerField(null=True)
