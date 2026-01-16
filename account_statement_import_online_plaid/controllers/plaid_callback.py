# Copyright 2025 Kencove
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import hmac
import json
import logging
import time

from odoo import _, http
from odoo.http import request

_logger = logging.getLogger(__name__)

try:
    import jwt as pyjwt

    PYJWT_AVAILABLE = True
except ImportError:
    PYJWT_AVAILABLE = False
    _logger.warning("PyJWT library not installed. Webhook verification unavailable.")

# Cache for Plaid webhook verification keys
_PLAID_KEY_CACHE = {}


class PlaidController(http.Controller):
    def _verify_plaid_webhook(self, body, headers):
        """Verify Plaid webhook signature.

        Plaid signs all outgoing webhooks with the Plaid-Verification header.
        This method validates the JWT signature and body hash to ensure
        the webhook is authentic and hasn't been tampered with.

        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        if not PYJWT_AVAILABLE:
            _logger.warning(
                "PyJWT not installed - webhook verification skipped. "
                "Install PyJWT for secure webhook handling."
            )
            # Allow processing but log warning - configurable behavior
            return True, None

        signed_jwt = headers.get("Plaid-Verification")
        if not signed_jwt:
            return False, "Missing Plaid-Verification header"

        try:
            # Decode header without verification to get key ID
            unverified_header = pyjwt.get_unverified_header(signed_jwt)

            # Verify algorithm is ES256 as required by Plaid
            if unverified_header.get("alg") != "ES256":
                return False, "Invalid algorithm - expected ES256"

            key_id = unverified_header.get("kid")
            if not key_id:
                return False, "Missing key ID in JWT header"

            # Get verification key (with caching)
            key = self._get_plaid_verification_key(key_id)
            if not key:
                return False, f"Could not retrieve verification key: {key_id}"

            # Check if key is expired
            if key.get("expired_at"):
                return False, "Verification key has expired"

            # Verify JWT signature
            try:
                # Build JWK for PyJWT
                from jwt import algorithms

                jwk_key = algorithms.ECAlgorithm.from_jwk(json.dumps(key))
                claims = pyjwt.decode(
                    signed_jwt,
                    jwk_key,
                    algorithms=["ES256"],
                )
            except pyjwt.InvalidSignatureError:
                return False, "Invalid JWT signature"
            except pyjwt.DecodeError as e:
                return False, f"JWT decode error: {e}"

            # Verify timestamp (not older than 5 minutes)
            issued_at = claims.get("iat", 0)
            if issued_at < time.time() - 5 * 60:
                return False, "Webhook token expired (older than 5 minutes)"

            # Verify body hash
            expected_hash = claims.get("request_body_sha256")
            if not expected_hash:
                return False, "Missing request_body_sha256 in JWT claims"

            # Compute SHA-256 of the body
            actual_hash = hashlib.sha256(body.encode()).hexdigest()

            # Use constant-time comparison to prevent timing attacks
            if not hmac.compare_digest(actual_hash, expected_hash):
                return False, "Body hash mismatch"

            return True, None

        except Exception as e:
            _logger.exception("Webhook verification failed")
            return False, f"Verification error: {e}"

    def _get_plaid_verification_key(self, key_id):
        """Get Plaid webhook verification key, using cache when possible."""
        global _PLAID_KEY_CACHE

        # Check cache first
        if key_id in _PLAID_KEY_CACHE:
            cached_key = _PLAID_KEY_CACHE[key_id]
            if not cached_key.get("expired_at"):
                return cached_key

        # Fetch key from Plaid using any configured provider
        try:
            provider = (
                request.env["online.bank.statement.provider"]
                .sudo()
                .search([("service", "=", "plaid")], limit=1)
            )
            if not provider:
                _logger.error("No Plaid provider configured for key verification")
                return None

            client = provider._get_plaid_client()

            from plaid.model.webhook_verification_key_get_request import (
                WebhookVerificationKeyGetRequest,
            )

            req = WebhookVerificationKeyGetRequest(key_id=key_id)
            response = client.webhook_verification_key_get(req)
            key = response.key.to_dict()

            # Cache the key
            _PLAID_KEY_CACHE[key_id] = key
            return key

        except Exception as e:
            _logger.error("Failed to fetch Plaid verification key %s: %s", key_id, e)
            return None

    @http.route("/plaid/exchange_token", type="json", auth="user")
    def exchange_token(self, public_token, provider_id, account_id, institution):
        """Exchange public token for access token after Plaid Link success"""
        provider = request.env["online.bank.statement.provider"].browse(provider_id)

        if not provider.exists():
            return {"success": False, "error": "Provider not found"}

        try:
            # Exchange public token for access token
            access_token, item_id = provider._plaid_exchange_token(public_token)

            # Store connection details
            provider.write(
                {
                    "plaid_access_token": access_token,
                    "plaid_item_id": item_id,
                    "plaid_account_id": account_id,
                    "plaid_institution_id": institution.get("institution_id")
                    if institution
                    else False,
                    "plaid_institution_name": institution.get("name")
                    if institution
                    else False,
                    "plaid_error_message": False,
                    "plaid_sync_cursor": False,  # Reset cursor for new connection
                }
            )

            # Fetch account details (type, subtype, name, etc.)
            provider._plaid_fetch_account_details()

            _logger.info(
                "Plaid connection established for provider %s (institution: %s)",
                provider.id,
                institution.get("name") if institution else "unknown",
            )

            return {"success": True}

        except Exception as e:
            _logger.exception("Failed to exchange Plaid token")
            provider.plaid_error_message = str(e)
            return {"success": False, "error": str(e)}

    @http.route("/plaid/webhook", type="json", auth="public", csrf=False)
    def plaid_webhook(self, **kwargs):
        """Handle Plaid webhooks for status updates

        Plaid can notify us of:
        - ITEM_LOGIN_REQUIRED: User needs to re-authenticate
        - TRANSACTIONS_REMOVED: Historical transactions were removed
        - INITIAL_UPDATE: Initial transaction pull complete
        - HISTORICAL_UPDATE: Historical transactions available
        - DEFAULT_UPDATE: New transactions available

        Security: Webhook signature is verified using the Plaid-Verification
        header to ensure authenticity and prevent forged requests.
        """
        # Verify webhook signature for security
        raw_body = request.httprequest.get_data(as_text=True)
        headers = {
            "Plaid-Verification": request.httprequest.headers.get(
                "Plaid-Verification", ""
            )
        }

        is_valid, error_msg = self._verify_plaid_webhook(raw_body, headers)
        if not is_valid:
            _logger.warning("Plaid webhook verification failed: %s", error_msg)
            return {"status": "rejected", "reason": "verification_failed"}

        webhook_type = kwargs.get("webhook_type")
        webhook_code = kwargs.get("webhook_code")
        item_id = kwargs.get("item_id")

        _logger.info(
            "Received Plaid webhook: type=%s, code=%s, item_id=%s",
            webhook_type,
            webhook_code,
            item_id,
        )

        if not item_id:
            return {"status": "ignored", "reason": "no item_id"}

        # Find provider by item_id
        provider = (
            request.env["online.bank.statement.provider"]
            .sudo()
            .search([("plaid_item_id", "=", item_id)], limit=1)
        )

        if not provider:
            _logger.warning("No provider found for Plaid item_id: %s", item_id)
            return {"status": "ignored", "reason": "provider not found"}

        if webhook_type == "ITEM" and webhook_code == "ERROR":
            # Item has an error - mark for reconnection
            error = kwargs.get("error", {})
            provider.plaid_error_message = error.get("error_message", "Unknown error")
            _logger.warning(
                "Plaid item error for provider %s: %s",
                provider.id,
                provider.plaid_error_message,
            )

        elif webhook_type == "ITEM" and webhook_code == "PENDING_EXPIRATION":
            # Access token expiring soon - notify user
            provider.message_post(
                body=_("Plaid connection will expire soon. Please reconnect."),
                message_type="notification",
            )

        elif webhook_type == "TRANSACTIONS":
            if webhook_code in (
                "INITIAL_UPDATE",
                "HISTORICAL_UPDATE",
                "DEFAULT_UPDATE",
            ):
                # New transactions available - could trigger automatic pull
                _logger.info(
                    "Transactions update for provider %s: %s",
                    provider.id,
                    webhook_code,
                )
            elif webhook_code == "TRANSACTIONS_REMOVED":
                # Transactions were removed - reset cursor
                removed_ids = kwargs.get("removed_transactions", [])
                _logger.info(
                    "Transactions removed for provider %s: %s",
                    provider.id,
                    removed_ids,
                )

        return {"status": "received"}
