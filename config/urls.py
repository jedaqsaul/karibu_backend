"""
config/urls.py — Root URL configuration for the Karibu platform.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from shared.views import HealthCheckView

urlpatterns = [
    path("django-admin/", admin.site.urls),

    # Health check — no auth, used by load balancers
    path("api/health/", HealthCheckView.as_view(), name="health-check"),

    # Apps
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.events.urls")),
    path("api/", include("apps.tickets.urls")),
    path("api/", include("apps.payments.urls")),
    path("api/", include("apps.analytics.urls")),
    path("api/", include("apps.notifications.urls")),
    path("api/", include("apps.logs.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
