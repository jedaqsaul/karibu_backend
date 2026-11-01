from django.contrib import admin
from .models import Ticket, TicketValidation


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display  = ["ticket_number", "event", "attendee", "status", "price_paid", "purchased_at"]
    list_filter   = ["status", "pdf_generated", "email_sent"]
    search_fields = ["ticket_number", "attendee__email", "event__title"]
    raw_id_fields = ["event", "attendee"]
    readonly_fields = [
        "id", "ticket_code", "ticket_number", "qr_payload",
        "purchased_at", "updated_at", "email_sent_at",
    ]

    def qr_payload(self, obj):
        return obj.qr_payload
    qr_payload.short_description = "QR Payload"

    def has_delete_permission(self, request, obj=None):
        return False  # Tickets are immutable records


@admin.register(TicketValidation)
class TicketValidationAdmin(admin.ModelAdmin):
    list_display  = ["ticket", "result", "scanned_by", "scanned_at"]
    list_filter   = ["result", "scanned_at"]
    search_fields = ["scanned_code", "ticket__ticket_number"]
    readonly_fields = ["id", "ticket", "scanned_by", "scanned_code", "result", "scanned_at", "device_info"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
