from django.db import models


class User(models.Model):
    id = models.IntegerField(primary_key=True)
    email = models.CharField(max_length=255, null=True)
    full_name = models.CharField(max_length=255, null=True)
    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(null=True)
    group = models.CharField(max_length=255, null=True)
    admin = models.BooleanField(null=True)
    color = models.CharField(max_length=255, null=True)
