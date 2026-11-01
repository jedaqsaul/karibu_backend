import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0002_full_events"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Ticket",
            fields=[
                ("id",             models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("ticket_code",    models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)),
                ("ticket_number",  models.CharField(max_length=20, unique=True, db_index=True)),
                ("price_paid",     models.DecimalField(max_digits=10, decimal_places=2)),
                ("currency",       models.CharField(default="KES", max_length=3)),
                ("status",         models.CharField(
                    choices=[("pending","Pending Payment"),("confirmed","Confirmed"),("cancelled","Cancelled"),("refunded","Refunded"),("used","Used")],
                    db_index=True, default="pending", max_length=20,
                )),
                ("pdf_generated",  models.BooleanField(default=False)),
                ("pdf_url",        models.URLField(blank=True)),
                ("download_count", models.PositiveIntegerField(default=0)),
                ("email_sent",     models.BooleanField(default=False)),
                ("email_sent_at",  models.DateTimeField(blank=True, null=True)),
                ("purchased_at",   models.DateTimeField(auto_now_add=True)),
                ("updated_at",     models.DateTimeField(auto_now=True)),
                ("event",    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tickets",     to="events.event")),
                ("attendee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tickets",     to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "tickets", "ordering": ["-purchased_at"]},
        ),
        migrations.AddIndex(model_name="ticket", index=models.Index(fields=["event",    "status"], name="ticket_event_status_idx")),
        migrations.AddIndex(model_name="ticket", index=models.Index(fields=["attendee", "status"], name="ticket_att_status_idx")),
        migrations.CreateModel(
            name="TicketValidation",
            fields=[
                ("id",           models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("scanned_code", models.CharField(max_length=100)),
                ("result",       models.CharField(
                    choices=[("success","Valid"),("already_used","Already Used"),("invalid_code","Invalid Code"),("cancelled","Cancelled"),("event_mismatch","Wrong Event")],
                    max_length=20,
                )),
                ("scanned_at",  models.DateTimeField(auto_now_add=True, db_index=True)),
                ("device_info", models.CharField(blank=True, max_length=300)),
                ("ticket",     models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="validations",  to="tickets.ticket")),
                ("scanned_by", models.ForeignKey(null=True,             on_delete=django.db.models.deletion.SET_NULL, related_name="ticket_scans", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "ticket_validations", "ordering": ["-scanned_at"]},
        ),
    ]
