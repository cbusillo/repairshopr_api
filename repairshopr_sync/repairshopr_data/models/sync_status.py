from django.db import models


class SyncStatus(models.Model):
    cycle_id = models.CharField(max_length=64, null=True)
    status = models.CharField(max_length=20, default="idle")
    mode = models.CharField(max_length=20, null=True)
    current_model = models.CharField(max_length=64, null=True)
    current_page = models.IntegerField(null=True)
    records_processed = models.BigIntegerField(default=0)
    cycle_started_at = models.DateTimeField(null=True)
    cycle_finished_at = models.DateTimeField(null=True)
    last_heartbeat = models.DateTimeField(null=True)
    last_error = models.TextField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sync Status"
        verbose_name_plural = "Sync Status"

