"""
Phase 2 migration: full events schema.
Adds Category, rewrites Event model, adds EventImage.
"""

import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create Category
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id",         models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("name",       models.CharField(max_length=100, unique=True)),
                ("slug",       models.SlugField(max_length=100, unique=True)),
                ("icon",       models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "event_categories", "ordering": ["name"]},
        ),

        # 2. Drop the stub Event table and replace with the full model
        migrations.DeleteModel(name="Event"),

        migrations.CreateModel(
            name="Event",
            fields=[
                ("id",               models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("title",            models.CharField(max_length=300)),
                ("slug",             models.SlugField(max_length=320, unique=True)),
                ("description",      models.TextField()),
                ("tags",             models.CharField(blank=True, max_length=500)),
                ("venue",            models.CharField(max_length=300)),
                ("address",          models.CharField(max_length=500)),
                ("city",             models.CharField(db_index=True, max_length=100)),
                ("country",          models.CharField(default="Kenya", max_length=100)),
                ("latitude",         models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude",        models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("start_datetime",   models.DateTimeField(db_index=True)),
                ("end_datetime",     models.DateTimeField()),
                ("is_free",          models.BooleanField(default=False)),
                ("ticket_price",     models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ("total_capacity",   models.PositiveIntegerField()),
                ("tickets_sold",     models.PositiveIntegerField(default=0)),
                ("banner_image",     models.ImageField(blank=True, null=True, upload_to="event_banners/")),
                ("status",           models.CharField(choices=[("draft","Draft"),("pending_approval","Pending Approval"),("published","Published"),("cancelled","Cancelled"),("completed","Completed")], db_index=True, default="draft", max_length=20)),
                ("rejection_reason", models.TextField(blank=True)),
                ("submitted_at",     models.DateTimeField(blank=True, null=True)),
                ("approved_at",      models.DateTimeField(blank=True, null=True)),
                ("created_at",       models.DateTimeField(auto_now_add=True)),
                ("updated_at",       models.DateTimeField(auto_now=True)),
                ("organizer",        models.ForeignKey(limit_choices_to={"role": "organizer"}, on_delete=django.db.models.deletion.CASCADE, related_name="events", to=settings.AUTH_USER_MODEL)),
                ("category",         models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="events", to="events.category")),
                ("approved_by",      models.ForeignKey(blank=True, limit_choices_to={"role": "super_admin"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "events", "ordering": ["-start_datetime"]},
        ),

        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["status", "start_datetime"], name="ev_status_start_idx"),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["city", "status"], name="ev_city_status_idx"),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["organizer", "status"], name="ev_org_status_idx"),
        ),

        # 3. Create EventImage
        migrations.CreateModel(
            name="EventImage",
            fields=[
                ("id",          models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("image",       models.ImageField(upload_to="event_gallery/")),
                ("caption",     models.CharField(blank=True, max_length=200)),
                ("order",       models.PositiveSmallIntegerField(default=0)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("event",       models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="gallery_images", to="events.event")),
            ],
            options={"db_table": "event_images", "ordering": ["order", "uploaded_at"]},
        ),
    ]
