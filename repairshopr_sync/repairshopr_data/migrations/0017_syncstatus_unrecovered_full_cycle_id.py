from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("repairshopr_data", "0016_invoice_amount_paid_invoice_balance_due_and_more")]

    operations = [
        migrations.AddField(
            model_name="syncstatus",
            name="unrecovered_full_cycle_id",
            field=models.CharField(max_length=64, null=True),
        ),
    ]
