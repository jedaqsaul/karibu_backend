"""
Management command: send_event_reminders

Dispatches reminder notifications to confirmed ticket holders
for events happening in N days (default: 1 and 3).

Schedule via cron or Celery Beat in production:
  0 8 * * * python manage.py send_event_reminders
"""

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.tickets.models import Ticket, TicketStatus
from apps.notifications.tasks import send_event_reminder


class Command(BaseCommand):
    help = "Send event reminder notifications to ticket holders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            nargs="+",
            type=int,
            default=[1, 3],
            help="Days before the event to send reminders (default: 1 and 3)",
        )

    def handle(self, *args, **options):
        now        = timezone.now()
        total_sent = 0

        for day_offset in options["days"]:
            window_start = now + timedelta(days=day_offset)
            window_end   = window_start + timedelta(hours=24)

            tickets = (
                Ticket.objects
                .filter(
                    status=TicketStatus.CONFIRMED,
                    event__start_datetime__gte=window_start,
                    event__start_datetime__lt=window_end,
                )
                .select_related("attendee", "event")
            )

            count = tickets.count()
            for ticket in tickets:
                send_event_reminder(ticket)

            self.stdout.write(f"  {count} reminder(s) for events in {day_offset} day(s).")
            total_sent += count

        self.stdout.write(self.style.SUCCESS(f"Total dispatched: {total_sent}"))
