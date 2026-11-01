"""
events/filters.py

Declarative filters for event list endpoints using django-filter.
Keeps all filtering logic out of views and serializers.
"""

import django_filters
from django.db.models import Q
from .models import Event, EventStatus, Category


class EventFilter(django_filters.FilterSet):
    """
    Filters available on GET /api/events/:
      ?category=<slug>
      ?city=<str>
      ?status=<str>               (admin/organizer only — enforced in view)
      ?is_free=true|false
      ?price_min=100&price_max=500
      ?start_after=2025-01-01
      ?start_before=2025-12-31
      ?search=<str>               (title, description, venue, tags)
    """

    category = django_filters.CharFilter(
        field_name="category__slug",
        lookup_expr="iexact",
        label="Category slug",
    )
    city = django_filters.CharFilter(
        field_name="city",
        lookup_expr="icontains",
        label="City",
    )
    status = django_filters.ChoiceFilter(
        choices=EventStatus.choices,
        label="Status",
    )
    is_free = django_filters.BooleanFilter(
        field_name="is_free",
        label="Free events only",
    )
    price_min = django_filters.NumberFilter(
        field_name="ticket_price",
        lookup_expr="gte",
        label="Minimum price (KES)",
    )
    price_max = django_filters.NumberFilter(
        field_name="ticket_price",
        lookup_expr="lte",
        label="Maximum price (KES)",
    )
    start_after = django_filters.DateTimeFilter(
        field_name="start_datetime",
        lookup_expr="gte",
        label="Starting after (ISO 8601)",
    )
    start_before = django_filters.DateTimeFilter(
        field_name="start_datetime",
        lookup_expr="lte",
        label="Starting before (ISO 8601)",
    )
    search = django_filters.CharFilter(
        method="filter_search",
        label="Full-text search across title, description, venue, tags",
    )

    class Meta:
        model  = Event
        fields = [
            "category", "city", "status",
            "is_free", "price_min", "price_max",
            "start_after", "start_before", "search",
        ]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(venue__icontains=value) |
            Q(tags__icontains=value) |
            Q(city__icontains=value)
        )


class OrganizerEventFilter(django_filters.FilterSet):
    """
    Tighter filter for the organizer's own event dashboard.
    Adds upcoming/past shortcuts.
    """
    from django.utils import timezone as tz

    status = django_filters.ChoiceFilter(choices=EventStatus.choices)
    upcoming = django_filters.BooleanFilter(method="filter_upcoming", label="Upcoming only")

    class Meta:
        model  = Event
        fields = ["status", "upcoming"]

    def filter_upcoming(self, queryset, name, value):
        from django.utils import timezone
        if value:
            return queryset.filter(start_datetime__gt=timezone.now())
        return queryset.filter(start_datetime__lte=timezone.now())
