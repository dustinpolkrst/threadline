from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0003_crmimportjob_crmimportrow_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="crmimportrow",
            name="warnings",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="crmimportrow",
            name="duplicate_object_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="crmimportrow",
            name="resolution",
            field=models.CharField(
                choices=[("create", "Create"), ("update", "Update existing"), ("skip", "Skip")],
                default="create",
                max_length=20,
            ),
        ),
    ]
