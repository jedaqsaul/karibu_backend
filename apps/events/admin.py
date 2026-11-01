from django.contrib import admin
from .models import Event, Category, EventImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ["name", "slug", "icon"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display   = ["title", "organizer", "status", "city", "start_datetime", "tickets_sold"]
    list_filter    = ["status", "category", "city", "is_free"]
    search_fields  = ["title", "organizer__email", "venue"]
    raw_id_fields  = ["organizer", "approved_by"]
    readonly_fields = ["slug", "created_at", "updated_at", "submitted_at", "approved_at"]
    ordering       = ["-created_at"]


@admin.register(EventImage)
class EventImageAdmin(admin.ModelAdmin):
    list_display  = ["event", "caption", "order", "uploaded_at"]
    raw_id_fields = ["event"]
