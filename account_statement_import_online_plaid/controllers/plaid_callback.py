# Copyright 2025 Kencove
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PlaidController(http.Controller):
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
        """
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
