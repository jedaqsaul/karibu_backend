"""
Management command: purge_audit_logs

Deletes audit log entries older than N days (default: 365).
Runs in batches to avoid locking the table.

Usage:
  python manage.py purge_audit_logs
  python manage.py purge_audit_logs --days 180
  python manage.py purge_audit_logs --days 90 --dry-run

Schedule monthly via cron:
  0 2 1 * * python manage.py purge_audit_logs --days 365
"""

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.logs.models import AuditLog


class Command(BaseCommand):
    help = "Purge audit log entries older than N days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Delete entries older than this many days (default: 365).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count entries to delete without actually deleting.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Delete in batches of this size (default: 1000).",
        )

    def handle(self, *args, **options):
        cutoff     = timezone.now() - timedelta(days=options["days"])
        dry_run    = options["dry_run"]
        batch_size = options["batch_size"]

        count = AuditLog.objects.filter(created_at__lt=cutoff).count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: {count} entries would be deleted "
                    f"(older than {options['days']} days, cutoff: {cutoff.date()})."
                )
            )
            return

        self.stdout.write(
            f"Purging {count} entries older than {cutoff.date()} in batches of {batch_size}..."
        )

        deleted_total = 0
        while True:
            ids = list(
                AuditLog.objects
                .filter(created_at__lt=cutoff)
                .values_list("id", flat=True)[:batch_size]
            )
            if not ids:
                break
            deleted, _ = AuditLog.objects.filter(id__in=ids).delete()
            deleted_total += deleted
            self.stdout.write(f"  Deleted batch of {deleted} (total so far: {deleted_total})")

        self.stdout.write(
            self.style.SUCCESS(f"Done. Total deleted: {deleted_total}")
        )
