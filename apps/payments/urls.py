from django.urls import path

from .views import STKPushInitiateView, MpesaCallbackView, PaymentStatusView

urlpatterns = [
    path("payments/mpesa/stkpush/",        STKPushInitiateView.as_view(), name="mpesa-stkpush"),
    path("payments/mpesa/callback/",       MpesaCallbackView.as_view(),   name="mpesa-callback"),
    path("payments/mpesa/<uuid:id>/status/", PaymentStatusView.as_view(), name="mpesa-status"),
]
