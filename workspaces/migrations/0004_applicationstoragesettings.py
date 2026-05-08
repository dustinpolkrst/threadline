from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0003_businesshourscalendar_invitation_slapolicy"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApplicationStorageSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("backend", models.CharField(choices=[("local", "Local filesystem"), ("s3", "S3-compatible")], default="local", max_length=20)),
                ("bucket_name", models.CharField(blank=True, max_length=255)),
                ("endpoint_url", models.URLField(blank=True)),
                ("region_name", models.CharField(blank=True, max_length=80)),
                ("access_key_id", models.CharField(blank=True, max_length=255)),
                ("secret_access_key", models.CharField(blank=True, max_length=255)),
                ("custom_domain", models.CharField(blank=True, max_length=255)),
                ("addressing_style", models.CharField(default="auto", max_length=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("workspace", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="storage_settings", to="workspaces.workspace")),
            ],
            options={"verbose_name_plural": "application storage settings"},
        ),
    ]
