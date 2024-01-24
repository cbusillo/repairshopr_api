from django.db import models


class CustomerProperties(models.Model):
    id = models.AutoField(primary_key=True)
    type = models.IntegerField(null=True)
    notification_billing = models.CharField(max_length=255, null=True)
    notification_reports = models.CharField(max_length=255, null=True)
    notification_marketing = models.CharField(max_length=255, null=True)
    title = models.CharField(max_length=255, null=True)
    li_school = models.CharField(max_length=255, null=True)

    def __str__(self) -> str:
        return f"{self.id} - {self.type} - {self.notification_billing} - {self.notification_reports} - {self.notification_marketing}"


class Customer(models.Model):
    id = models.IntegerField(primary_key=True)
    firstname = models.CharField(max_length=255, null=True)
    lastname = models.CharField(max_length=255, null=True)
    fullname = models.CharField(max_length=255, null=True)
    business_name = models.CharField(max_length=255, null=True)
    email = models.CharField(max_length=255, null=True)
    phone = models.CharField(max_length=255, null=True)
    mobile = models.CharField(max_length=255, null=True)
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    pdf_url = models.URLField(max_length=500, null=True)
    address = models.CharField(max_length=255, null=True)
    address_2 = models.CharField(max_length=255, null=True)
    city = models.CharField(max_length=255, null=True)
    state = models.CharField(max_length=255, null=True)
    zip = models.CharField(max_length=255, null=True)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    notes = models.TextField(null=True)
    get_sms = models.BooleanField(null=True)
    opt_out = models.BooleanField(null=True)
    disabled = models.BooleanField(null=True)
    no_email = models.BooleanField(null=True)
    location_name = models.CharField(max_length=255, null=True)
    location_id = models.IntegerField(null=True)
    properties = models.ForeignKey(CustomerProperties, related_name="customer", on_delete=models.CASCADE, null=True)
    online_profile_url = models.URLField(max_length=255, null=True)
    tax_rate_id = models.IntegerField(null=True)
    notification_email = models.CharField(max_length=255, null=True)
    invoice_cc_emails = models.CharField(max_length=255, null=True)
    invoice_term_id = models.IntegerField(null=True)
    referred_by = models.CharField(max_length=255, null=True)
    ref_customer_id = models.IntegerField(null=True)
    business_and_full_name = models.CharField(max_length=255, null=True)
    business_then_name = models.CharField(max_length=255, null=True)

    def __str__(self) -> str:
        return f"{self.id} - {self.business_then_name} - {self.phone} - {self.email}"


class CustomerContact(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=255, null=True)
    address1 = models.CharField(max_length=255, null=True)
    address2 = models.CharField(max_length=255, null=True)
    city = models.CharField(max_length=255, null=True)
    state = models.CharField(max_length=255, null=True)
    zip = models.CharField(max_length=255, null=True)
    email = models.CharField(max_length=255, null=True)
    phone = models.CharField(max_length=255, null=True)
    mobile = models.CharField(max_length=255, null=True)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    account_id = models.IntegerField(null=True)
    notes = models.TextField(null=True)
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    vendor_id = models.IntegerField(null=True)
    properties = models.ForeignKey(CustomerProperties, on_delete=models.CASCADE, null=True)
    opt_out = models.BooleanField(null=True)
    extension = models.CharField(max_length=255, null=True)
    processed_phone = models.CharField(max_length=255, null=True)
    processed_mobile = models.CharField(max_length=255, null=True)

    parent_customer = models.ForeignKey(Customer, related_name="contacts", on_delete=models.CASCADE, null=True)

    def __str__(self) -> str:
        return f"{self.id} - {self.name} - {self.phone} - {self.email}"
