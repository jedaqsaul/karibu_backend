#!/usr/bin/env bash
# test_mpesa_credentials.sh
#
# Tests your MPESA_CONSUMER_KEY / MPESA_CONSUMER_SECRET directly against
# Safaricom's sandbox OAuth endpoint — completely bypassing Django/our
# backend. This tells you for certain whether "Wrong credentials" is a
# problem with the keys themselves, vs. anything in how our code sends
# the request.
#
# Usage (from karibu_backend/, with your .env already filled in):
#   bash test_mpesa_credentials.sh

set -e

ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  echo "No .env file found in the current directory. Run this from karibu_backend/."
  exit 1
fi

# Pull the two values straight out of .env (strips inline comments/quotes).
CONSUMER_KEY=$(grep -E '^MPESA_CONSUMER_KEY=' "$ENV_FILE" | cut -d '=' -f2- | tr -d '"'"'"' \r')
CONSUMER_SECRET=$(grep -E '^MPESA_CONSUMER_SECRET=' "$ENV_FILE" | cut -d '=' -f2- | tr -d '"'"'"' \r')
ENVIRONMENT=$(grep -E '^MPESA_ENVIRONMENT=' "$ENV_FILE" | cut -d '=' -f2- | tr -d '"'"'"' \r')
ENVIRONMENT=${ENVIRONMENT:-sandbox}

if [ -z "$CONSUMER_KEY" ] || [ -z "$CONSUMER_SECRET" ]; then
  echo "MPESA_CONSUMER_KEY or MPESA_CONSUMER_SECRET is empty in .env — set both first."
  exit 1
fi

echo "MPESA_ENVIRONMENT = $ENVIRONMENT"
echo "Consumer key      = ${CONSUMER_KEY:0:6}...${CONSUMER_KEY: -4}  (${#CONSUMER_KEY} chars)"
echo "Consumer secret    = ${CONSUMER_SECRET:0:4}...${CONSUMER_SECRET: -4}  (${#CONSUMER_SECRET} chars)"
echo

if [ "$ENVIRONMENT" = "production" ]; then
  BASE_URL="https://api.safaricom.co.ke"
else
  BASE_URL="https://sandbox.safaricom.co.ke"
fi
echo "Testing against: $BASE_URL"
echo

echo "== Requesting OAuth token directly from Safaricom =="
curl -s -w "\nHTTP %{http_code}\n" -X GET \
  "$BASE_URL/oauth/v1/generate?grant_type=client_credentials" \
  -u "$CONSUMER_KEY:$CONSUMER_SECRET"

echo
echo "If you see an access_token above, the credentials are good and the"
echo "issue is elsewhere. If you see 'Wrong credentials' or a 400/401,"
echo "the key/secret themselves are the problem — see the checklist below."
