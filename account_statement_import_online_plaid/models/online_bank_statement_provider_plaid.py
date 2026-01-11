# Copyright 2025 Kencove
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.country_code import CountryCode
    from plaid.model.item_public_token_exchange_request import (
        ItemPublicTokenExchangeRequest,
    )
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.products import Products
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.transactions_get_request_options import (
        TransactionsGetRequestOptions,
    )
    from plaid.model.transactions_sync_request import TransactionsSyncRequest

    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False
    _logger.warning("plaid-python library not installed. Plaid provider unavailable.")


class OnlineBankStatementProviderPlaid(models.Model):
    _inherit = "online.bank.statement.provider"

    # Plaid credentials
    plaid_client_id = fields.Char(
        string="Client ID",
        help="Plaid API Client ID from your Plaid dashboard",
    )
    plaid_secret = fields.Char(
        string="Secret",
        help="Plaid API Secret from your Plaid dashboard",
    )
    plaid_environment = fields.Selection(
        selection=[
            ("sandbox", "Sandbox"),
            ("development", "Development"),
            ("production", "Production"),
        ],
        string="Environment",
        default="sandbox",
        help="Plaid environment to use. Use Sandbox for testing.",
    )

    # Connection state
    plaid_access_token = fields.Char(
        string="Access Token",
        help="Plaid access token for this bank connection",
        groups="base.group_system",
    )
    plaid_item_id = fields.Char(
        string="Item ID",
        help="Plaid Item ID representing this bank connection",
    )
    plaid_account_id = fields.Char(
        string="Account ID",
        help="Plaid Account ID for the specific account to sync",
    )
    plaid_institution_id = fields.Char(
        string="Institution ID",
        help="Plaid Institution ID for the connected bank",
    )
    plaid_institution_name = fields.Char(
        string="Institution",
        help="Name of the connected bank institution",
    )
    plaid_account_name = fields.Char(
        string="Account Name",
        help="Name of the connected account at the bank",
    )
    plaid_account_type = fields.Selection(
        selection=[
            ("depository", "Bank Account"),
            ("credit", "Credit Card"),
            ("loan", "Loan"),
            ("investment", "Investment"),
        ],
        string="Account Type",
        help="Type of the connected bank account",
    )
    plaid_account_subtype = fields.Char(
        string="Account Subtype",
        help="Subtype of the connected account (e.g., checking, savings)",
    )
    plaid_account_mask = fields.Char(
        string="Account Mask",
        help="Last 4 digits of the account number",
    )

    # Incremental sync cursor
    plaid_sync_cursor = fields.Char(
        string="Sync Cursor",
        help="Cursor for incremental transaction sync",
    )

    # Connection status
    plaid_connection_status = fields.Selection(
        selection=[
            ("disconnected", "Not Connected"),
            ("connected", "Connected"),
            ("error", "Error - Reconnect Required"),
        ],
        string="Connection Status",
        compute="_compute_plaid_connection_status",
        store=True,
    )
    plaid_error_message = fields.Text(
        string="Error Message",
        help="Last error message from Plaid",
    )

    @api.depends("plaid_access_token", "plaid_account_id", "plaid_error_message")
    def _compute_plaid_connection_status(self):
        for provider in self:
            if provider.service != "plaid":
                provider.plaid_connection_status = False
            elif provider.plaid_error_message:
                provider.plaid_connection_status = "error"
            elif provider.plaid_access_token and provider.plaid_account_id:
                provider.plaid_connection_status = "connected"
            else:
                provider.plaid_connection_status = "disconnected"

    @api.model
    def _get_available_services(self):
        """Register Plaid as an available service"""
        services = super()._get_available_services()
        if PLAID_AVAILABLE:
            services = services + [("plaid", "Plaid")]
        return services

    def _get_plaid_client(self):
        """Get configured Plaid API client"""
        self.ensure_one()
        if not PLAID_AVAILABLE:
            raise UserError(
                _(
                    "The plaid-python library is not installed. "
                    "Please install it with: pip install plaid-python"
                )
            )
        if not self.plaid_client_id or not self.plaid_secret:
            raise UserError(_("Please configure Plaid Client ID and Secret"))

        environment_map = {
            "sandbox": plaid.Environment.Sandbox,
            "development": plaid.Environment.Development,
            "production": plaid.Environment.Production,
        }
        configuration = plaid.Configuration(
            host=environment_map.get(self.plaid_environment, plaid.Environment.Sandbox),
            api_key={
                "clientId": self.plaid_client_id,
                "secret": self.plaid_secret,
            },
        )
        api_client = plaid.ApiClient(configuration)
        return plaid_api.PlaidApi(api_client)

    def action_plaid_link(self):
        """Open Plaid Link to connect a bank account"""
        self.ensure_one()
        client = self._get_plaid_client()

        # Create link token
        request = LinkTokenCreateRequest(
            products=[Products("transactions")],
            client_name=self.env.company.name or "Odoo",
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(
                client_user_id=str(self.env.uid),
            ),
        )

        try:
            response = client.link_token_create(request)
            link_token = response.link_token
        except plaid.ApiException as e:
            raise UserError(_("Failed to create Plaid Link token: %s") % str(e)) from e

        # Return action to open Plaid Link widget
        return {
            "type": "ir.actions.client",
            "tag": "plaid_link_action",
            "target": "new",
            "context": {
                "link_token": link_token,
                "provider_id": self.id,
            },
        }

    def _plaid_exchange_token(self, public_token):
        """Exchange public token for access token"""
        self.ensure_one()
        client = self._get_plaid_client()

        request = ItemPublicTokenExchangeRequest(
            public_token=public_token,
        )

        try:
            response = client.item_public_token_exchange(request)
            return response.access_token, response.item_id
        except plaid.ApiException as e:
            raise UserError(_("Failed to exchange Plaid token: %s") % str(e)) from e

    def _plaid_fetch_account_details(self):
        """Fetch and store account details from Plaid"""
        self.ensure_one()
        if not self.plaid_access_token or not self.plaid_account_id:
            return

        client = self._get_plaid_client()

        try:
            from plaid.model.accounts_get_request import AccountsGetRequest

            request = AccountsGetRequest(
                access_token=self.plaid_access_token,
            )
            response = client.accounts_get(request)

            for account in response.accounts:
                if account.account_id == self.plaid_account_id:
                    self.write(
                        {
                            "plaid_account_name": account.name,
                            "plaid_account_type": account.type.value
                            if hasattr(account.type, "value")
                            else str(account.type),
                            "plaid_account_subtype": account.subtype.value
                            if account.subtype and hasattr(account.subtype, "value")
                            else str(account.subtype)
                            if account.subtype
                            else False,
                            "plaid_account_mask": account.mask,
                            "plaid_error_message": False,
                        }
                    )
                    break
        except plaid.ApiException as e:
            self.plaid_error_message = str(e)
            _logger.error("Failed to fetch Plaid account details: %s", e)

    def _obtain_statement_data(self, date_since, date_until):
        """Main hook - fetch transactions from Plaid"""
        self.ensure_one()
        if self.service != "plaid":
            return super()._obtain_statement_data(date_since, date_until)
        return self._plaid_obtain_statement_data(date_since, date_until)

    def _plaid_obtain_statement_data(self, date_since, date_until):
        """Fetch transactions from Plaid API"""
        self.ensure_one()

        if not self.plaid_access_token:
            raise UserError(
                _(
                    "Bank account not connected. Please use 'Connect Bank Account' first."
                )
            )

        lines = []

        # Use incremental sync if cursor exists and not a manual pull
        if self.plaid_sync_cursor and self.env.context.get("scheduled"):
            transactions, removed = self._plaid_sync_transactions()
            # Handle removed transactions (cancelled pending)
            for removed_txn in removed:
                self._plaid_handle_removed_transaction(removed_txn)
        else:
            transactions = self._plaid_get_transactions(date_since, date_until)

        for txn in transactions:
            line = self._plaid_transaction_to_line(txn)
            if line:
                lines.append(line)

        # Get current balance
        statement_values = {}
        try:
            balance = self._plaid_get_balance()
            if balance is not None:
                statement_values["balance_end_real"] = balance
        except Exception as e:
            _logger.warning("Could not fetch Plaid balance: %s", e)

        return lines, statement_values

    def _plaid_get_transactions(self, date_since, date_until):
        """Fetch transactions for a date range"""
        self.ensure_one()
        client = self._get_plaid_client()

        # Convert datetime to date
        start_date = (
            date_since.date() if isinstance(date_since, datetime) else date_since
        )
        end_date = date_until.date() if isinstance(date_until, datetime) else date_until

        all_transactions = []
        offset = 0
        total_transactions = None

        try:
            while total_transactions is None or offset < total_transactions:
                options = TransactionsGetRequestOptions(
                    account_ids=[self.plaid_account_id]
                    if self.plaid_account_id
                    else None,
                    offset=offset,
                    count=500,
                )
                request = TransactionsGetRequest(
                    access_token=self.plaid_access_token,
                    start_date=start_date,
                    end_date=end_date,
                    options=options,
                )
                response = client.transactions_get(request)

                all_transactions.extend(response.transactions)
                total_transactions = response.total_transactions
                offset += len(response.transactions)

                if len(response.transactions) == 0:
                    break

            self.plaid_error_message = False
            return all_transactions

        except plaid.ApiException as e:
            self.plaid_error_message = str(e)
            error_body = e.body if hasattr(e, "body") else str(e)
            raise UserError(
                _("Failed to fetch transactions from Plaid: %s") % error_body
            ) from e

    def _plaid_sync_transactions(self):
        """Use transactions/sync for incremental updates"""
        self.ensure_one()
        client = self._get_plaid_client()

        added = []
        modified = []
        removed = []
        cursor = self.plaid_sync_cursor or ""
        has_more = True

        try:
            while has_more:
                request = TransactionsSyncRequest(
                    access_token=self.plaid_access_token,
                    cursor=cursor,
                )
                response = client.transactions_sync(request)

                added.extend(response.added)
                modified.extend(response.modified)
                removed.extend(response.removed)

                has_more = response.has_more
                cursor = response.next_cursor

            # Store new cursor
            self.plaid_sync_cursor = cursor
            self.plaid_error_message = False

            # Return added + modified as transactions to import
            return added + modified, removed

        except plaid.ApiException as e:
            self.plaid_error_message = str(e)
            raise UserError(
                _("Failed to sync transactions from Plaid: %s") % str(e)
            ) from e

    def _plaid_handle_removed_transaction(self, removed_txn):
        """Handle removed pending transaction"""
        transaction_id = (
            removed_txn.transaction_id
            if hasattr(removed_txn, "transaction_id")
            else removed_txn.get("transaction_id")
        )
        if not transaction_id:
            return

        # Search for pending version of this transaction
        line = self.env["account.bank.statement.line"].search(
            [
                ("unique_import_id", "like", f"pending-{transaction_id}"),
                ("journal_id", "=", self.journal_id.id),
            ],
            limit=1,
        )

        if line and not line.is_reconciled:
            _logger.info("Removing cancelled pending transaction: %s", transaction_id)
            line.unlink()

    def _plaid_transaction_to_line(self, transaction):
        """Convert Plaid transaction to statement line dict"""
        # Get transaction attributes
        transaction_id = (
            transaction.transaction_id
            if hasattr(transaction, "transaction_id")
            else transaction.get("transaction_id")
        )
        pending = (
            transaction.pending
            if hasattr(transaction, "pending")
            else transaction.get("pending", False)
        )
        amount = (
            transaction.amount
            if hasattr(transaction, "amount")
            else transaction.get("amount", 0)
        )
        date_val = (
            transaction.date
            if hasattr(transaction, "date")
            else transaction.get("date")
        )
        name = (
            transaction.name
            if hasattr(transaction, "name")
            else transaction.get("name", "")
        )
        merchant_name = (
            transaction.merchant_name
            if hasattr(transaction, "merchant_name")
            else transaction.get("merchant_name")
        )
        check_number = (
            transaction.check_number
            if hasattr(transaction, "check_number")
            else transaction.get("check_number")
        )
        category = (
            transaction.personal_finance_category
            if hasattr(transaction, "personal_finance_category")
            else transaction.get("personal_finance_category")
        )

        # Handle pending transactions with a different unique_import_id
        if pending:
            unique_id = f"pending-{transaction_id}"
        else:
            unique_id = transaction_id

        # Sign inversion: Plaid positive = expense/debit
        # Odoo: negative = expense, positive = income
        amount = -float(amount)

        # Build payment reference
        payment_ref = merchant_name or name or "/"

        # Add check number if present
        if check_number:
            payment_ref = f"{payment_ref} #{check_number}"

        line = {
            "date": date_val,
            "payment_ref": payment_ref[:140] if payment_ref else "/",
            "amount": amount,
            "unique_import_id": unique_id,
            "partner_name": merchant_name,
            "narration": name if name != merchant_name else False,
        }

        # Add check number to ref field
        if check_number:
            line["ref"] = str(check_number)

        # Store raw transaction data
        line["raw_data"] = str(transaction)

        # Handle category mapping
        if category:
            primary_cat = (
                category.primary
                if hasattr(category, "primary")
                else category.get("primary")
            )
            detailed_cat = (
                category.detailed
                if hasattr(category, "detailed")
                else category.get("detailed")
            )

            if primary_cat:
                # Look up category mapping
                mapping = self.env["plaid.category.mapping"].search(
                    [
                        ("plaid_category", "=", primary_cat),
                        "|",
                        ("company_id", "=", self.company_id.id),
                        ("company_id", "=", False),
                    ],
                    limit=1,
                )
                if mapping and mapping.account_id:
                    line["counterpart_account_id"] = mapping.account_id.id

                # Store category in narration if not already set
                if not line.get("narration"):
                    line["narration"] = f"Category: {primary_cat}"
                    if detailed_cat:
                        line["narration"] += f" / {detailed_cat}"

        return line

    def _plaid_get_balance(self):
        """Get current account balance from Plaid"""
        self.ensure_one()
        client = self._get_plaid_client()

        try:
            from plaid.model.accounts_balance_get_request import (
                AccountsBalanceGetRequest,
            )

            request = AccountsBalanceGetRequest(
                access_token=self.plaid_access_token,
            )
            response = client.accounts_balance_get(request)

            for account in response.accounts:
                if account.account_id == self.plaid_account_id:
                    # Use current balance (includes pending)
                    balance = account.balances.current
                    if balance is not None:
                        # For credit cards, Plaid shows positive balance as owed
                        # Odoo expects negative balance for credit card debt
                        if self.plaid_account_type == "credit":
                            return -float(balance)
                        return float(balance)
            return None

        except plaid.ApiException as e:
            _logger.warning("Failed to get Plaid balance: %s", e)
            return None

    def action_plaid_disconnect(self):
        """Disconnect the Plaid connection"""
        self.ensure_one()
        self.write(
            {
                "plaid_access_token": False,
                "plaid_item_id": False,
                "plaid_account_id": False,
                "plaid_institution_id": False,
                "plaid_institution_name": False,
                "plaid_account_name": False,
                "plaid_account_type": False,
                "plaid_account_subtype": False,
                "plaid_account_mask": False,
                "plaid_sync_cursor": False,
                "plaid_error_message": False,
            }
        )
        return True

    def action_plaid_refresh(self):
        """Refresh account details from Plaid"""
        self.ensure_one()
        self._plaid_fetch_account_details()
        return True

    def action_plaid_reset_cursor(self):
        """Reset sync cursor to force full resync"""
        self.ensure_one()
        self.plaid_sync_cursor = False
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": _(
                    "Sync cursor reset. Next sync will fetch all transactions."
                ),
                "type": "success",
            },
        }
