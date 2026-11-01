"""
Phase 6 migration: upgrade AuditLog with user_email snapshot,
user_role, category, and composite indexes.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="user_email",
            field=models.EmailField(blank=True, db_index=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="user_role",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="category",
            field=models.CharField(
                choices=[
                    ("auth","Authentication"),("account","Account"),
                    ("event","Event"),("ticket","Ticket"),
                    ("admin","Admin Action"),("system","System"),
                ],
                db_index=True,
                default="system",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["action",   "created_at"], name="audit_action_created_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["category", "created_at"], name="audit_cat_created_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["user",     "created_at"], name="audit_user_created_idx"),
        ),
    ]
