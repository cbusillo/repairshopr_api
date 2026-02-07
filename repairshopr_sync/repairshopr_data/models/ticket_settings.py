from django.db import models


class TicketType(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=255, null=True)

    class Meta:
        db_table = "repairshopr_data_ticket_types"


class TicketTypeField(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=255, null=True)
    field_type = models.CharField(max_length=255, null=True)
    ticket_type_id = models.IntegerField(null=True, db_index=True)
    position = models.IntegerField(null=True)
    required = models.BooleanField(null=True)

    class Meta:
        db_table = "repairshopr_data_ticket_type_fields"


class TicketTypeFieldAnswer(models.Model):
    id = models.IntegerField(primary_key=True)
    ticket_field_id = models.IntegerField(null=True, db_index=True)
    value = models.CharField(max_length=255, null=True)

    class Meta:
        db_table = "repairshopr_data_ticket_type_field_answers"
