"""
shared/utils/ticket_number.py

Generates human-readable, sequential ticket numbers.
Format: KRB-00001, KRB-00002, ...

Uses SELECT FOR UPDATE to prevent race conditions under concurrent purchases.
"""

from django.db import transaction


def generate_ticket_number() -> str:
    """
    Thread-safe ticket number generator.
    Locks the last ticket row for the duration of the transaction
    to guarantee uniqueness under concurrent load.
    """
    from apps.tickets.models import Ticket

    with transaction.atomic():
        last = (
            Ticket.objects
            .select_for_update()
            .order_by("-ticket_number")
            .values_list("ticket_number", flat=True)
            .first()
        )
        if last:
            try:
                n = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                n = 1
        else:
            n = 1
        return f"KRB-{n:05d}"
