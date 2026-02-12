from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("repairshopr_data", "0014_alter_ticketcomment_body_collation_portable"),
    ]

    operations = [
        migrations.CreateModel(
            name="SyncStatus",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cycle_id", models.CharField(max_length=64, null=True)),
                ("status", models.CharField(default="idle", max_length=20)),
                ("mode", models.CharField(max_length=20, null=True)),
                ("current_model", models.CharField(max_length=64, null=True)),
                ("current_page", models.IntegerField(null=True)),
                ("records_processed", models.BigIntegerField(default=0)),
                ("cycle_started_at", models.DateTimeField(null=True)),
                ("cycle_finished_at", models.DateTimeField(null=True)),
                ("last_heartbeat", models.DateTimeField(null=True)),
                ("last_error", models.TextField(null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sync Status",
                "verbose_name_plural": "Sync Status",
            },
        )
    ]

