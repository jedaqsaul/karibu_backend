"""
analytics/models.py

Analytics has no models of its own.
All data is derived from existing models via ORM aggregations:
  - Ticket  → revenue, sales counts, attendee numbers
  - Event   → event counts by status, category breakdown
  - User    → registration trends, role distribution

No denormalised summary tables in Phase 4.
If query performance becomes an issue at scale, Phase 7 hardening
introduces materialised summary tables updated via Celery periodic tasks.
"""
