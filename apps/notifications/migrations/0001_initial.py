import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id",                models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("notification_type", models.CharField(db_index=True, max_length=30)),
                ("title",      models.CharField(max_length=200)),
                ("message",    models.TextField()),
                ("action_url", models.CharField(blank=True, max_length=500)),
                ("is_read",    models.BooleanField(default=False, db_index=True)),
                ("read_at",    models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("recipient",  models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="notifications",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "notifications", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "is_read"],    name="notif_recip_read_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "created_at"], name="notif_recip_created_idx"),
        ),
        migrations.CreateModel(
            name="EmailLog",
            fields=[
                ("id",              models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("recipient_email", models.EmailField(db_index=True)),
                ("subject",         models.CharField(max_length=500)),
                ("email_type",      models.CharField(max_length=50, db_index=True)),
                ("status",          models.CharField(db_index=True, default="sent", max_length=10)),
                ("error_message",   models.TextField(blank=True)),
                ("sent_at",         models.DateTimeField(auto_now_add=True)),
                ("recipient",       models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="email_logs",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "email_logs", "ordering": ["-sent_at"]},
        ),
    ]
