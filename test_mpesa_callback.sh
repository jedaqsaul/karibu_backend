#!/usr/bin/env bash
# test_mpesa_callback.sh
#
# Tests apps.payments end-to-end against your LOCAL server — no ngrok
# involved. This isolates whether a problem is in the Django backend
# itself vs. the ngrok tunnel.
#
# Usage:
#   1. In one terminal: python manage.py runserver 127.0.0.1:8000
#   2. In another terminal, from karibu_backend/ with your venv active:
#        bash test_mpesa_callback.sh
#
# Expects at least one attendee user and one paid, published event to
# already exist (the seeded dev data has both — e.g. grace.wanjiku@example.com).

set -e

BASE_URL="http://127.0.0.1:8000"
EMAIL="grace.wanjiku@example.com"
PASSWORD="Karibu@2026"
CHECKOUT_ID="checkout-manual-test-$(date +%s)"

echo "== 1. Health check (waiting for server to respond) =="
UP=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health/" || true)
  if [ "$CODE" = "200" ]; then
    echo "Server is up (HTTP 200) after ${i}s"
    UP=1
    break
  fi
  sleep 1
done
if [ "$UP" -ne 1 ]; then
  echo "Could not reach $BASE_URL/api/health/ — is 'python manage.py runserver 127.0.0.1:8000' actually running?"
  exit 1
fi

echo
echo "== 2. Login =="
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access'])")
if [ -z "$TOKEN" ]; then
  echo "Login failed. Response was:"
  echo "$LOGIN_RESPONSE"
  exit 1
fi
echo "Got token: ${TOKEN:0:20}..."

echo
echo "== 3. Create a pending MpesaTransaction directly (simulates what a real STK push would create) =="
TXN_ID=$(python manage.py shell -c "
from django.contrib.auth import get_user_model
from apps.events.models import Event
from apps.payments.models import MpesaTransaction
User = get_user_model()
user = User.objects.get(email='$EMAIL')
event = Event.objects.filter(is_free=False, status='published').first()
if not event:
    raise SystemExit('No paid published event found — seed the DB first.')
txn = MpesaTransaction.objects.create(
    user=user, event=event, quantity=1, amount=event.ticket_price,
    phone_number='254712345678', merchant_request_id='merchant-manual-test',
    checkout_request_id='$CHECKOUT_ID',
)
print(txn.id)
" 2>/dev/null | tail -1)
echo "Transaction id: $TXN_ID"
echo "Checkout request id: $CHECKOUT_ID"

echo
echo "== 4. Status BEFORE callback (expect status=initiated, empty ticket_snapshot) =="
curl -s "$BASE_URL/api/payments/mpesa/$TXN_ID/status/" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo
echo "== 5. Fire a realistic Safaricom success callback =="
curl -s -w "\nHTTP %{http_code}\n" -X POST "$BASE_URL/api/payments/mpesa/callback/" \
  -H "Content-Type: application/json" \
  -d "{
    \"Body\": {
      \"stkCallback\": {
        \"MerchantRequestID\": \"merchant-manual-test\",
        \"CheckoutRequestID\": \"$CHECKOUT_ID\",
        \"ResultCode\": 0,
        \"ResultDesc\": \"The service request is processed successfully.\",
        \"CallbackMetadata\": {
          \"Item\": [
            {\"Name\": \"Amount\", \"Value\": 1000.0},
            {\"Name\": \"MpesaReceiptNumber\", \"Value\": \"TESTRCPT1\"},
            {\"Name\": \"TransactionDate\", \"Value\": 20260815120000},
            {\"Name\": \"PhoneNumber\", \"Value\": 254712345678}
          ]
        }
      }
    }
  }"

echo
echo "== 6. Status AFTER callback (expect status=success, ticket_snapshot populated) =="
curl -s "$BASE_URL/api/payments/mpesa/$TXN_ID/status/" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo
echo "Done. If step 6 shows status=success with a ticket_snapshot entry, the backend is working correctly end to end."
