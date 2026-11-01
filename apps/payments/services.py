"""
payments/services.py

Thin client for Safaricom's Daraja API — just the STK Push (Lipa Na
M-Pesa Online) pieces this platform needs:

  1. OAuth token  — GET /oauth/v1/generate, cached (tokens last ~1 hour)
  2. STK Push     — POST /mpesa/stkpush/v1/processrequest
                    Triggers the PIN prompt on the customer's phone.
  3. STK Query    — POST /mpesa/stkpushquery/v1/query
                    Used as a fallback when the async callback hasn't
                    arrived yet (see notes below on why this matters).

Docs: https://developer.safaricom.co.ke/APIs/MpesaExpressSimulate

--------------------------------------------------------------------------
IMPORTANT — local development note
--------------------------------------------------------------------------
Safaricom calls MPESA_CALLBACK_URL directly from their servers. That URL
must be a real, publicly reachable HTTPS endpoint — "http://localhost:8000"
will never receive anything. For local dev, tunnel your local server with
something like ngrok/cloudflared and set MPESA_CALLBACK_URL to that tunnel
URL. Until a real public callback URL is configured, use the STK status
query endpoint (GET /api/payments/mpesa/<id>/status/) to poll Safaricom
directly instead of relying on the callback — see views.PaymentStatusView.
--------------------------------------------------------------------------
"""

import base64
import logging
import re
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction as db_transaction

logger = logging.getLogger("karibu.payments")

CACHE_KEY_TOKEN = "mpesa:access_token"


class DarajaError(Exception):
    """Raised for any failure talking to Safaricom — network, auth, or a
    non-zero ResponseCode. Callers should catch this and turn it into a
    clean 4xx/5xx API response rather than letting it bubble up raw."""


def normalize_phone(raw_phone: str) -> str:
    """
    Normalize a Kenyan phone number to Safaricom's required 2547XXXXXXXX /
    2541XXXXXXXX format, accepting the common input variants:
        0712345678, 712345678, +254712345678, 254712345678
    Raises ValueError if it doesn't look like a valid Safaricom number.
    """
    digits = re.sub(r"\D", "", raw_phone or "")

    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif digits.startswith("254") and len(digits) == 12:
        pass
    elif len(digits) == 9:
        digits = "254" + digits

    if not re.fullmatch(r"254[17]\d{8}", digits):
        raise ValueError(
            "Enter a valid Safaricom number, e.g. 0712345678 or 254712345678."
        )
    return digits


class DarajaClient:
    def __init__(self):
        self.consumer_key    = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.shortcode       = settings.MPESA_SHORTCODE
        self.passkey         = settings.MPESA_PASSKEY
        self.callback_url    = settings.MPESA_CALLBACK_URL
        self.base_url        = settings.MPESA_BASE_URL
        self.timeout          = 30

    # -- OAuth ----------------------------------------------------------

    def get_access_token(self) -> str:
        cached = cache.get(CACHE_KEY_TOKEN)
        if cached:
            return cached

        if not self.consumer_key or not self.consumer_secret:
            raise DarajaError(
                "M-Pesa is not configured — set MPESA_CONSUMER_KEY and "
                "MPESA_CONSUMER_SECRET in the environment."
            )

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        try:
            resp = requests.get(
                url,
                auth=(self.consumer_key, self.consumer_secret),
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Daraja OAuth request failed")
            raise DarajaError(f"Could not reach Safaricom: {exc}") from exc

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise DarajaError(f"Unexpected OAuth response: {data}")

        # Safaricom tokens last 3600s — cache for slightly less so we
        # never use a token in the last few seconds of its life.
        expires_in = int(data.get("expires_in", 3599))
        cache.set(CACHE_KEY_TOKEN, token, timeout=max(expires_in - 60, 60))
        return token

    # -- STK Push ---------------------------------------------------------

    def _password_and_timestamp(self):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        raw = f"{self.shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(raw.encode()).decode()
        return password, timestamp

    def stk_push(self, *, phone_number: str, amount: int, account_reference: str,
                 transaction_desc: str) -> dict:
        """
        Trigger the STK Push PIN prompt on the customer's phone.

        `phone_number` must already be normalized (see normalize_phone).
        `amount` is coerced to a whole-number KES value — Safaricom's
        sandbox rejects decimals.

        Returns Safaricom's raw JSON response on success:
          {MerchantRequestID, CheckoutRequestID, ResponseCode,
           ResponseDescription, CustomerMessage}
        Raises DarajaError on any failure.
        """
        password, timestamp = self._password_and_timestamp()
        token = self.get_access_token()

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(round(amount)),
            "PartyA": phone_number,
            "PartyB": self.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:13],
        }

        try:
            resp = requests.post(
                f"{self.base_url}/mpesa/stkpush/v1/processrequest",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.exception("Daraja STK push request failed")
            raise DarajaError(f"Could not reach Safaricom: {exc}") from exc

        data = resp.json()

        if resp.status_code != 200 or data.get("ResponseCode") not in (0, "0"):
            error_msg = (
                data.get("errorMessage")
                or data.get("ResponseDescription")
                or data.get("CustomerMessage")
                or "STK push was rejected by Safaricom."
            )
            raise DarajaError(error_msg)

        return data

    # -- STK status query (fallback for when the callback hasn't arrived) --

    def query_stk_status(self, checkout_request_id: str) -> dict:
        password, timestamp = self._password_and_timestamp()
        token = self.get_access_token()

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/mpesa/stkpushquery/v1/query",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.exception("Daraja STK status query failed")
            raise DarajaError(f"Could not reach Safaricom: {exc}") from exc

        return resp.json()


# ---------------------------------------------------------------------------
# Payment confirmation — shared by MpesaCallbackView (async, Safaricom-driven)
# and PaymentStatusView's fallback query (sync, used when the callback can't
# reach us, e.g. local dev without a public callback URL). Both paths funnel
# through here so a payment is only ever confirmed and ticketed once,
# however the confirmation arrived.
# ---------------------------------------------------------------------------

def extract_callback_metadata(stk_callback: dict) -> dict:
    """
    Safaricom's CallbackMetadata is a list of {Name, Value} pairs — flatten
    it into a plain dict: {"Amount": ..., "MpesaReceiptNumber": ..., ...}
    """
    items = (stk_callback.get("CallbackMetadata") or {}).get("Item") or []
    return {item.get("Name"): item.get("Value") for item in items if "Name" in item}


def confirm_payment_success(mpesa_transaction, *, result_code=0, result_desc="",
                             mpesa_receipt_number="", transaction_date_raw="",
                             callback_raw=None):
    """
    Mark a transaction SUCCESS and create its tickets — idempotent.
    If the transaction was already confirmed (by callback or by the status
    poll's fallback query racing each other), this only backfills any
    metadata that wasn't set yet and does NOT create duplicate tickets.
    """
    from .models import MpesaTransactionStatus
    from apps.tickets.services import (
        create_confirmed_tickets, generate_and_attach_pdf, send_ticket_email,
    )

    if mpesa_transaction.status == MpesaTransactionStatus.SUCCESS:
        updated_fields = []
        if mpesa_receipt_number and not mpesa_transaction.mpesa_receipt_number:
            mpesa_transaction.mpesa_receipt_number = mpesa_receipt_number
            updated_fields.append("mpesa_receipt_number")
        if transaction_date_raw and not mpesa_transaction.transaction_date_raw:
            mpesa_transaction.transaction_date_raw = transaction_date_raw
            updated_fields.append("transaction_date_raw")
        if callback_raw and not mpesa_transaction.callback_raw:
            mpesa_transaction.callback_raw = callback_raw
            updated_fields.append("callback_raw")
        if updated_fields:
            mpesa_transaction.save(update_fields=updated_fields)
        return mpesa_transaction

    with db_transaction.atomic():
        # Re-fetch and lock to guard against the callback and a concurrent
        # status-poll both trying to confirm the same transaction at once.
        locked = type(mpesa_transaction).objects.select_for_update().get(
            pk=mpesa_transaction.pk
        )
        if locked.status == MpesaTransactionStatus.SUCCESS:
            return locked

        # Per-ticket price is what was actually agreed/paid at initiation
        # time, not whatever event.ticket_price happens to be now.
        per_ticket_price = locked.amount / locked.quantity if locked.quantity else locked.amount

        # NOTE: we don't re-check event.tickets_remaining here. Capacity was
        # already checked when the STK push was initiated, but wasn't held
        # (no reservation system yet) — so in the rare case of two payments
        # completing back-to-back right at sold-out, this can oversell by a
        # seat or two. Given the customer has already paid via M-Pesa, we
        # deliberately still issue the ticket rather than silently keeping
        # their money without a ticket; a stricter reservation-hold system
        # is a reasonable future enhancement if this becomes a real problem.
        created_tickets = create_confirmed_tickets(
            event=locked.event,
            attendee=locked.user,
            quantity=locked.quantity,
            price_paid=per_ticket_price,
        )

        locked.status                = MpesaTransactionStatus.SUCCESS
        locked.result_code           = result_code
        locked.result_desc           = result_desc
        locked.mpesa_receipt_number  = mpesa_receipt_number
        locked.transaction_date_raw  = transaction_date_raw
        locked.callback_raw          = callback_raw
        locked.ticket_snapshot = [
            {"id": str(t.id), "ticket_number": t.ticket_number}
            for t in created_tickets
        ]
        locked.save()

    for ticket in created_tickets:
        generate_and_attach_pdf(ticket)
    send_ticket_email(locked.user, created_tickets, locked.event)

    return locked


def confirm_payment_failure(mpesa_transaction, *, result_code, result_desc, callback_raw=None):
    """Mark a transaction FAILED — idempotent, ignores late signals after success."""
    from .models import MpesaTransactionStatus

    if mpesa_transaction.status == MpesaTransactionStatus.SUCCESS:
        return mpesa_transaction
    if mpesa_transaction.status == MpesaTransactionStatus.FAILED:
        return mpesa_transaction

    mpesa_transaction.status       = MpesaTransactionStatus.FAILED
    mpesa_transaction.result_code  = result_code
    mpesa_transaction.result_desc  = result_desc
    mpesa_transaction.callback_raw = callback_raw
    mpesa_transaction.save()
    return mpesa_transaction
