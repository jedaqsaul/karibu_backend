"""
payments/views.py

Three endpoints:
  STKPushInitiateView  — POST, authenticated attendee starts a payment
  MpesaCallbackView    — POST, public webhook Safaricom calls with the result
  PaymentStatusView    — GET, authenticated attendee polls payment status
                         (also proactively queries Safaricom directly if the
                         callback hasn't arrived yet — see its docstring)
"""

import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.logs.utils import log_action

from .models import MpesaTransaction, MpesaTransactionStatus
from .serializers import STKPushInitiateSerializer, MpesaTransactionSerializer
from .services import (
    DarajaClient, DarajaError,
    extract_callback_metadata, confirm_payment_success, confirm_payment_failure,
)

logger = logging.getLogger("karibu.payments")


class STKPushInitiateView(APIView):
    """
    POST /api/payments/mpesa/stkpush/
    Body: {"event_id": "...", "quantity": 1, "phone_number": "0712345678"}

    Triggers the M-Pesa PIN prompt on the customer's phone and creates a
    tracking MpesaTransaction. No ticket exists yet — that only happens
    once payment is confirmed (see MpesaCallbackView / PaymentStatusView).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = STKPushInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event    = serializer.validated_data["event"]
        quantity = serializer.validated_data["quantity"]
        phone    = serializer.validated_data["phone_number"]
        amount   = event.ticket_price * quantity

        client = DarajaClient()
        try:
            daraja_response = client.stk_push(
                phone_number=phone,
                amount=amount,
                account_reference=event.slug or event.title,
                transaction_desc=f"Karibu-{event.title}",
            )
        except DarajaError as exc:
            logger.warning("STK push initiation failed for event %s: %s", event.id, exc)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        mpesa_transaction = MpesaTransaction.objects.create(
            user=request.user,
            event=event,
            quantity=quantity,
            amount=amount,
            phone_number=phone,
            merchant_request_id=daraja_response.get("MerchantRequestID", ""),
            checkout_request_id=daraja_response["CheckoutRequestID"],
        )

        log_action(
            request.user, "MPESA_STK_PUSH_INITIATED",
            f"STK push sent for {quantity}x '{event.title}' — KES {amount} to {phone}",
        )

        return Response(
            {
                "message": daraja_response.get(
                    "CustomerMessage",
                    "Check your phone and enter your M-Pesa PIN to complete payment.",
                ),
                "transaction_id": mpesa_transaction.id,
                "checkout_request_id": mpesa_transaction.checkout_request_id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class MpesaCallbackView(APIView):
    """
    POST /api/payments/mpesa/callback/

    Public webhook — Safaricom calls this directly, with no auth header,
    once the customer has entered their PIN (or cancelled / timed out).
    Must always return HTTP 200 with an ack body, or Safaricom will retry
    the callback repeatedly.

    Expected payload shape:
      {
        "Body": {
          "stkCallback": {
            "MerchantRequestID": "...",
            "CheckoutRequestID": "...",
            "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.",
            "CallbackMetadata": {
              "Item": [
                {"Name": "Amount", "Value": 1.0},
                {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                {"Name": "TransactionDate", "Value": 20260802182530},
                {"Name": "PhoneNumber", "Value": 254712345678}
              ]
            }
          }
        }
      }
    (CallbackMetadata is absent entirely when ResultCode != 0.)
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Always acknowledge, even on malformed payloads — never give
        # Safaricom a reason to retry a request we can't make sense of.
        ack = Response({"ResultCode": 0, "ResultDesc": "Accepted"}, status=status.HTTP_200_OK)

        try:
            stk_callback = request.data["Body"]["stkCallback"]
            checkout_request_id = stk_callback["CheckoutRequestID"]
            result_code = stk_callback["ResultCode"]
            result_desc = stk_callback.get("ResultDesc", "")
        except (KeyError, TypeError):
            logger.error("Malformed M-Pesa callback payload: %s", request.data)
            return ack

        try:
            mpesa_transaction = MpesaTransaction.objects.get(
                checkout_request_id=checkout_request_id
            )
        except MpesaTransaction.DoesNotExist:
            logger.error(
                "M-Pesa callback for unknown CheckoutRequestID: %s", checkout_request_id
            )
            return ack

        if result_code == 0:
            meta = extract_callback_metadata(stk_callback)
            try:
                confirm_payment_success(
                    mpesa_transaction,
                    result_code=result_code,
                    result_desc=result_desc,
                    mpesa_receipt_number=str(meta.get("MpesaReceiptNumber", "")),
                    transaction_date_raw=str(meta.get("TransactionDate", "")),
                    callback_raw=request.data,
                )
                log_action(
                    mpesa_transaction.user, "MPESA_PAYMENT_SUCCESS",
                    f"Payment confirmed for '{mpesa_transaction.event.title}' — "
                    f"receipt {meta.get('MpesaReceiptNumber', '')}",
                )
            except Exception:
                # Payment succeeded on Safaricom's end but something on our
                # side (ticket creation, PDF, email) blew up — this needs a
                # human, but we must still 200 the callback so Safaricom
                # doesn't retry a payment that already went through.
                logger.exception(
                    "Failed to finalize successful M-Pesa payment %s",
                    mpesa_transaction.id,
                )
        else:
            confirm_payment_failure(
                mpesa_transaction,
                result_code=result_code,
                result_desc=result_desc,
                callback_raw=request.data,
            )
            log_action(
                mpesa_transaction.user, "MPESA_PAYMENT_FAILED",
                f"Payment failed for '{mpesa_transaction.event.title}' — {result_desc}",
            )

        return ack


class PaymentStatusView(APIView):
    """
    GET /api/payments/mpesa/<id>/status/

    Polled by the frontend every few seconds after initiating STK push.

    If the transaction is still INITIATED, proactively queries Safaricom's
    STK status endpoint as a fallback — this matters most in local
    development, where Safaricom's callback can't reach a non-public
    localhost URL at all, so without this the transaction would be stuck
    "pending" forever even after the customer successfully pays.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        mpesa_transaction = get_object_or_404(
            MpesaTransaction, id=id, user=request.user
        )

        if mpesa_transaction.status == MpesaTransactionStatus.INITIATED:
            self._poll_daraja(mpesa_transaction)
            mpesa_transaction.refresh_from_db()

        return Response(MpesaTransactionSerializer(mpesa_transaction).data)

    def _poll_daraja(self, mpesa_transaction):
        client = DarajaClient()
        try:
            result = client.query_stk_status(mpesa_transaction.checkout_request_id)
        except DarajaError as exc:
            # Not fatal — the async callback might still land normally.
            logger.info(
                "STK status query failed for %s (will retry on next poll): %s",
                mpesa_transaction.checkout_request_id, exc,
            )
            return

        result_code = result.get("ResultCode")
        if result_code is None:
            # Still pending on Safaricom's side — no result yet.
            return

        result_code = int(result_code)
        result_desc = result.get("ResultDesc", "")

        if result_code == 0:
            # The query endpoint doesn't return CallbackMetadata (no amount/
            # receipt number) — confirm anyway; the real callback, if it
            # ever arrives, will backfill the receipt number afterwards.
            confirm_payment_success(
                mpesa_transaction, result_code=result_code, result_desc=result_desc,
            )
        else:
            confirm_payment_failure(
                mpesa_transaction, result_code=result_code, result_desc=result_desc,
            )
