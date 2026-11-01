"""
analytics/services.py

All analytics logic lives here — not in views.
Views are thin: validate input, call service, return response.
Services own the ORM queries and return plain Python dicts/lists.

Three service classes:
  AdminAnalyticsService   — platform-wide metrics for Super Admin dashboard
  OrganizerAnalyticsService — per-organiser metrics for their own events
  PublicAnalyticsService  — lightweight stats exposed publicly (event counts etc.)
"""

from datetime import timedelta
from django.db.models import (
    Count, Sum, Avg, F, Q,
    DecimalField, IntegerField,
)
from django.db.models.functions import (
    TruncDay, TruncMonth, TruncWeek, Coalesce,
)
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.events.models import Event, EventStatus, Category
from apps.tickets.models import Ticket, TicketStatus

User = get_user_model()

_ZERO_DECIMAL = Coalesce(Sum("price_paid"), 0, output_field=DecimalField())
_ZERO_INT     = Coalesce(Count("id"),       0, output_field=IntegerField())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date_range(query_params):
    """
    Pull start_date / end_date from query params.
    Default: last 30 days.
    Returns (start_dt, end_dt) as aware datetimes.
    """
    from datetime import datetime
    now = timezone.now()

    start_str = query_params.get("start_date")
    end_str   = query_params.get("end_date")

    try:
        start = (
            timezone.make_aware(datetime.strptime(start_str, "%Y-%m-%d"))
            if start_str else now - timedelta(days=30)
        )
    except ValueError:
        start = now - timedelta(days=30)

    try:
        end = (
            timezone.make_aware(datetime.strptime(end_str, "%Y-%m-%d"))
            if end_str else now
        )
    except ValueError:
        end = now

    return start, end


def _trunc_fn(period: str):
    mapping = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}
    return mapping.get(period, TruncDay)


# ---------------------------------------------------------------------------
# Admin analytics service
# ---------------------------------------------------------------------------

class AdminAnalyticsService:
    """Platform-wide metrics. All methods are stateless class methods."""

    @classmethod
    def platform_summary(cls) -> dict:
        """
        Top-level KPI cards for the admin dashboard.
        Single pass — no N+1 queries.
        """
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        user_stats = User.objects.aggregate(
            total_users=Count("id"),
            total_organisers=Count("id", filter=Q(role="organizer")),
            approved_organisers=Count("id", filter=Q(role="organizer", is_approved=True)),
            total_attendees=Count("id", filter=Q(role="attendee")),
            new_users_30d=Count("id", filter=Q(date_joined__gte=thirty_days_ago)),
        )

        event_stats = Event.objects.aggregate(
            total_events=Count("id"),
            published_events=Count("id", filter=Q(status=EventStatus.PUBLISHED)),
            pending_events=Count("id", filter=Q(status=EventStatus.PENDING_APPROVAL)),
            draft_events=Count("id", filter=Q(status=EventStatus.DRAFT)),
            cancelled_events=Count("id", filter=Q(status=EventStatus.CANCELLED)),
            upcoming_events=Count("id", filter=Q(
                status=EventStatus.PUBLISHED,
                start_datetime__gt=now,
            )),
        )

        ticket_stats = Ticket.objects.aggregate(
            total_tickets=Count("id"),
            confirmed_tickets=Count("id", filter=Q(status=TicketStatus.CONFIRMED)),
            used_tickets=Count("id", filter=Q(status=TicketStatus.USED)),
            cancelled_tickets=Count("id", filter=Q(status=TicketStatus.CANCELLED)),
            total_revenue=_ZERO_DECIMAL,
            revenue_30d=Coalesce(
                Sum("price_paid", filter=Q(
                    status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                    purchased_at__gte=thirty_days_ago,
                )),
                0,
                output_field=DecimalField(),
            ),
            tickets_sold_30d=Count("id", filter=Q(
                status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                purchased_at__gte=thirty_days_ago,
            )),
        )

        return {**user_stats, **event_stats, **ticket_stats}

    @classmethod
    def revenue_over_time(cls, query_params: dict) -> list:
        """
        Revenue grouped by day/week/month for the revenue chart.
        Returns a list of {period, revenue, ticket_count} dicts.
        """
        start, end = _parse_date_range(query_params)
        period     = query_params.get("period", "day")
        trunc      = _trunc_fn(period)

        rows = (
            Ticket.objects
            .filter(
                status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                purchased_at__gte=start,
                purchased_at__lte=end,
            )
            .annotate(period=trunc("purchased_at"))
            .values("period")
            .annotate(
                revenue=Coalesce(Sum("price_paid"), 0, output_field=DecimalField()),
                ticket_count=Count("id"),
            )
            .order_by("period")
        )

        return [
            {
                "period":       r["period"].isoformat(),
                "revenue":      float(r["revenue"]),
                "ticket_count": r["ticket_count"],
            }
            for r in rows
        ]

    @classmethod
    def tickets_over_time(cls, query_params: dict) -> list:
        """Ticket sales volume grouped by period."""
        start, end = _parse_date_range(query_params)
        period     = query_params.get("period", "day")
        trunc      = _trunc_fn(period)

        rows = (
            Ticket.objects
            .filter(
                purchased_at__gte=start,
                purchased_at__lte=end,
            )
            .annotate(period=trunc("purchased_at"))
            .values("period")
            .annotate(
                total=Count("id"),
                confirmed=Count("id", filter=Q(status=TicketStatus.CONFIRMED)),
                used=Count("id",      filter=Q(status=TicketStatus.USED)),
                cancelled=Count("id", filter=Q(status=TicketStatus.CANCELLED)),
            )
            .order_by("period")
        )

        return [
            {
                "period":    r["period"].isoformat(),
                "total":     r["total"],
                "confirmed": r["confirmed"],
                "used":      r["used"],
                "cancelled": r["cancelled"],
            }
            for r in rows
        ]

    @classmethod
    def revenue_by_category(cls, query_params: dict) -> list:
        """Pie chart: revenue breakdown by event category."""
        start, end = _parse_date_range(query_params)

        rows = (
            Ticket.objects
            .filter(
                status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                purchased_at__gte=start,
                purchased_at__lte=end,
                event__category__isnull=False,
            )
            .values("event__category__name", "event__category__slug")
            .annotate(
                revenue=Coalesce(Sum("price_paid"), 0, output_field=DecimalField()),
                ticket_count=Count("id"),
            )
            .order_by("-revenue")
        )

        return [
            {
                "category":     r["event__category__name"],
                "slug":         r["event__category__slug"],
                "revenue":      float(r["revenue"]),
                "ticket_count": r["ticket_count"],
            }
            for r in rows
        ]

    @classmethod
    def user_registrations_over_time(cls, query_params: dict) -> list:
        """User registration trend grouped by period."""
        start, end = _parse_date_range(query_params)
        period     = query_params.get("period", "day")
        trunc      = _trunc_fn(period)

        rows = (
            User.objects
            .filter(date_joined__gte=start, date_joined__lte=end)
            .annotate(period=trunc("date_joined"))
            .values("period")
            .annotate(
                total=Count("id"),
                attendees=Count("id",   filter=Q(role="attendee")),
                organisers=Count("id",  filter=Q(role="organizer")),
            )
            .order_by("period")
        )

        return [
            {
                "period":     r["period"].isoformat(),
                "total":      r["total"],
                "attendees":  r["attendees"],
                "organisers": r["organisers"],
            }
            for r in rows
        ]

    @classmethod
    def top_events(cls, query_params: dict) -> list:
        """Top N events by revenue or ticket sales."""
        start, end = _parse_date_range(query_params)
        limit      = min(int(query_params.get("limit", 10)), 50)
        order_by   = query_params.get("order_by", "revenue")

        qs = (
            Ticket.objects
            .filter(
                status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                purchased_at__gte=start,
                purchased_at__lte=end,
            )
            .values("event__id", "event__title", "event__slug", "event__city",
                    "event__organizer__first_name")
            .annotate(
                revenue=Coalesce(Sum("price_paid"), 0, output_field=DecimalField()),
                ticket_count=Count("id"),
            )
        )

        sort_field = "-revenue" if order_by == "revenue" else "-ticket_count"
        rows = list(qs.order_by(sort_field)[:limit])

        return [
            {
                "event_id":       str(r["event__id"]),
                "title":          r["event__title"],
                "slug":           r["event__slug"],
                "city":           r["event__city"],
                "organizer_name": r["event__organizer__first_name"],
                "revenue":        float(r["revenue"]),
                "ticket_count":   r["ticket_count"],
            }
            for r in rows
        ]

    @classmethod
    def top_organizers(cls, query_params: dict) -> list:
        """Top N organizers by revenue generated."""
        start, end = _parse_date_range(query_params)
        limit      = min(int(query_params.get("limit", 10)), 50)

        rows = list(
            Ticket.objects
            .filter(
                status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                purchased_at__gte=start,
                purchased_at__lte=end,
            )
            .values("event__organizer__id", "event__organizer__first_name",
                    "event__organizer__email")
            .annotate(
                revenue=Coalesce(Sum("price_paid"), 0, output_field=DecimalField()),
                ticket_count=Count("id"),
                event_count=Count("event__id", distinct=True),
            )
            .order_by("-revenue")[:limit]
        )

        return [
            {
                "organizer_id":    str(r["event__organizer__id"]),
                "organizer_name":  r["event__organizer__first_name"],
                "organizer_email": r["event__organizer__email"],
                "revenue":         float(r["revenue"]),
                "ticket_count":    r["ticket_count"],
                "event_count":     r["event_count"],
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Organizer analytics service
# ---------------------------------------------------------------------------

class OrganizerAnalyticsService:
    """
    Per-organizer metrics. Every method takes organizer (User) as first arg
    and scopes all queries to their events only.
    """

    @classmethod
    def summary(cls, organizer) -> dict:
        """KPI summary for the organizer's dashboard."""
        now             = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        event_stats = Event.objects.filter(organizer=organizer).aggregate(
            total_events=Count("id"),
            published_events=Count("id", filter=Q(status=EventStatus.PUBLISHED)),
            draft_events=Count("id",     filter=Q(status=EventStatus.DRAFT)),
            pending_events=Count("id",   filter=Q(status=EventStatus.PENDING_APPROVAL)),
            cancelled_events=Count("id", filter=Q(status=EventStatus.CANCELLED)),
            upcoming_events=Count("id",  filter=Q(
                status=EventStatus.PUBLISHED,
                start_datetime__gt=now,
            )),
            total_capacity=Coalesce(Sum("total_capacity"), 0, output_field=IntegerField()),
            total_sold=Coalesce(Sum("tickets_sold"),       0, output_field=IntegerField()),
        )

        ticket_stats = Ticket.objects.filter(
            event__organizer=organizer,
        ).aggregate(
            total_revenue=_ZERO_DECIMAL,
            revenue_30d=Coalesce(
                Sum("price_paid", filter=Q(
                    status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                    purchased_at__gte=thirty_days_ago,
                )),
                0,
                output_field=DecimalField(),
            ),
            confirmed_tickets=Count("id", filter=Q(status=TicketStatus.CONFIRMED)),
            used_tickets=Count("id",      filter=Q(status=TicketStatus.USED)),
            cancelled_tickets=Count("id", filter=Q(status=TicketStatus.CANCELLED)),
        )

        return {**event_stats, **ticket_stats}

    @classmethod
    def revenue_over_time(cls, organizer, query_params: dict) -> list:
        """Revenue chart for organizer's own events."""
        start, end = _parse_date_range(query_params)
        period     = query_params.get("period", "day")
        trunc      = _trunc_fn(period)

        rows = (
            Ticket.objects
            .filter(
                event__organizer=organizer,
                status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                purchased_at__gte=start,
                purchased_at__lte=end,
            )
            .annotate(period=trunc("purchased_at"))
            .values("period")
            .annotate(
                revenue=Coalesce(Sum("price_paid"), 0, output_field=DecimalField()),
                ticket_count=Count("id"),
            )
            .order_by("period")
        )

        return [
            {
                "period":       r["period"].isoformat(),
                "revenue":      float(r["revenue"]),
                "ticket_count": r["ticket_count"],
            }
            for r in rows
        ]

    @classmethod
    def event_performance(cls, organizer, query_params: dict) -> list:
        """Per-event breakdown: capacity, sold, revenue, fill rate."""
        status_filter = query_params.get("status")

        qs = Event.objects.filter(organizer=organizer).annotate(
            tickets_confirmed=Count(
                "tickets",
                filter=Q(tickets__status__in=[TicketStatus.CONFIRMED, TicketStatus.USED]),
            ),
            revenue=Coalesce(
                Sum("tickets__price_paid", filter=Q(
                    tickets__status__in=[TicketStatus.CONFIRMED, TicketStatus.USED],
                )),
                0,
                output_field=DecimalField(),
            ),
        )

        if status_filter:
            qs = qs.filter(status=status_filter)

        qs = qs.order_by("-start_datetime")

        return [
            {
                "event_id":          str(e.id),
                "title":             e.title,
                "slug":              e.slug,
                "status":            e.status,
                "city":              e.city,
                "start_datetime":    e.start_datetime.isoformat(),
                "total_capacity":    e.total_capacity,
                "tickets_sold":      e.tickets_sold,
                "tickets_confirmed": e.tickets_confirmed,
                "fill_rate_pct":     round(
                    (e.tickets_sold / e.total_capacity * 100) if e.total_capacity else 0,
                    1,
                ),
                "revenue":           float(e.revenue),
                "is_free":           e.is_free,
                "ticket_price":      float(e.ticket_price),
            }
            for e in qs
        ]

    @classmethod
    def single_event_detail(cls, organizer, event_id: str) -> dict:
        """
        Deep analytics for a single event owned by this organizer.
        Returns sales timeline, attendee list summary, scan stats.
        """
        from apps.events.models import Event
        try:
            event = Event.objects.get(id=event_id, organizer=organizer)
        except Event.DoesNotExist:
            return None

        ticket_stats = Ticket.objects.filter(event=event).aggregate(
            total=Count("id"),
            confirmed=Count("id",  filter=Q(status=TicketStatus.CONFIRMED)),
            used=Count("id",       filter=Q(status=TicketStatus.USED)),
            cancelled=Count("id",  filter=Q(status=TicketStatus.CANCELLED)),
            revenue=_ZERO_DECIMAL,
        )

        # Sales by day for the mini-chart
        sales_timeline = list(
            Ticket.objects
            .filter(event=event, status__in=[TicketStatus.CONFIRMED, TicketStatus.USED])
            .annotate(day=TruncDay("purchased_at"))
            .values("day")
            .annotate(count=Count("id"), revenue=Coalesce(Sum("price_paid"), 0, output_field=DecimalField()))
            .order_by("day")
            .values_list("day", "count", "revenue")
        )

        from apps.tickets.models import TicketValidation
        scan_stats = TicketValidation.objects.filter(ticket__event=event).aggregate(
            total_scans=Count("id"),
            successful_scans=Count("id", filter=Q(result="success")),
            failed_scans=Count("id",     filter=~Q(result="success")),
        )

        return {
            "event": {
                "id":             str(event.id),
                "title":          event.title,
                "status":         event.status,
                "start_datetime": event.start_datetime.isoformat(),
                "total_capacity": event.total_capacity,
                "ticket_price":   float(event.ticket_price),
                "is_free":        event.is_free,
            },
            "ticket_stats": {
                **ticket_stats,
                "revenue": float(ticket_stats["revenue"]),
                "fill_rate_pct": round(
                    (ticket_stats["total"] / event.total_capacity * 100)
                    if event.total_capacity else 0,
                    1,
                ),
            },
            "sales_timeline": [
                {
                    "day":     day.isoformat(),
                    "count":   count,
                    "revenue": float(revenue),
                }
                for day, count, revenue in sales_timeline
            ],
            "scan_stats": scan_stats,
        }
