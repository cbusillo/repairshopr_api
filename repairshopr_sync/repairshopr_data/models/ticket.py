from django.db import models


class TicketProperties(models.Model):
    id = models.AutoField(primary_key=True)
    day = models.CharField(max_length=255, null=True)
    case = models.CharField(max_length=255, null=True)
    other = models.CharField(max_length=255, null=True)
    s_n_num = models.CharField(max_length=255, null=True)
    tag_num = models.CharField(max_length=255, null=True)
    claim_num = models.CharField(max_length=255, null=True)
    location = models.CharField(max_length=255, null=True)
    transport = models.CharField(max_length=255, null=True)
    boces = models.CharField(max_length=255, null=True)
    tag_num_2 = models.CharField(max_length=255, null=True)
    delivery_num = models.CharField(max_length=255, null=True)
    transport_2 = models.CharField(max_length=255, null=True)
    po_num_2 = models.CharField(max_length=255, null=True)
    phone_num = models.CharField(max_length=255, null=True)
    p_g_name = models.CharField(max_length=255, null=True)
    student = models.CharField(max_length=255, null=True)
    s_n = models.CharField(max_length=255, null=True)
    drop_off_location = models.CharField(max_length=255, null=True)
    call_num = models.CharField(max_length=255, null=True)


class Ticket(models.Model):
    id = models.IntegerField(primary_key=True)
    number = models.IntegerField(null=True)
    subject = models.CharField(max_length=255, null=True)
    created_at = models.DateTimeField(null=True)
    customer_id = models.IntegerField(null=True)
    customer_business_then_name = models.CharField(max_length=255, null=True)
    due_date = models.DateTimeField(null=True)
    resolved_at = models.DateTimeField(null=True)
    start_at = models.DateTimeField(null=True)
    end_at = models.DateTimeField(null=True)
    location_id = models.IntegerField(null=True)
    problem_type = models.CharField(max_length=255, null=True)
    status = models.CharField(max_length=255, null=True)
    ticket_type_id = models.IntegerField(null=True)
    properties = models.ForeignKey(TicketProperties, related_name="tickets", on_delete=models.CASCADE, null=True)
    user_id = models.IntegerField(null=True)
    updated_at = models.CharField(max_length=255, null=True)
    pdf_url = models.URLField(max_length=255, null=True)
    priority = models.CharField(max_length=255, null=True)


class TicketComment(models.Model):
    id = models.IntegerField(primary_key=True)
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    subject = models.CharField(max_length=255, null=True)
    body = models.TextField(null=True)
    tech = models.CharField(max_length=255, null=True)
    hidden = models.BooleanField(null=True)
    user_id = models.IntegerField(null=True)

    ticket = models.ForeignKey(Ticket, related_name="comments", on_delete=models.CASCADE, null=True)
