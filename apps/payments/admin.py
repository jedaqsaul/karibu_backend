from django.contrib import admin

from .models import MpesaTransaction


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "checkout_request_id", "user", "event", "quantity", "amount",
        "status", "mpesa_receipt_number", "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("checkout_request_id", "merchant_request_id",
                      "mpesa_receipt_number", "phone_number", "user__email")
    readonly_fields = [f.name for f in MpesaTransaction._meta.fields]

    def has_add_permission(self, request):
        # Transactions are only ever created via the STK push flow.
        return False
