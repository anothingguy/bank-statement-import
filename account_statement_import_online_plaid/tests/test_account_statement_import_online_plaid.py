# Copyright 2025 Kencove
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date, datetime
from unittest import mock

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import common

_module_ns = "odoo.addons.account_statement_import_online_plaid"
_provider_class = (
    _module_ns
    + ".models.online_bank_statement_provider_plaid"
    + ".OnlineBankStatementProviderPlaid"
)


class MockPlaidTransaction:
    """Mock Plaid transaction object"""

    def __init__(self, **kwargs):
        self.transaction_id = kwargs.get("transaction_id", "txn-123")
        self.pending = kwargs.get("pending", False)
        self.amount = kwargs.get("amount", 100.0)
        self.date = kwargs.get("date", date(2024, 1, 15))
        self.name = kwargs.get("name", "Test Merchant")
        self.merchant_name = kwargs.get("merchant_name", "Test Merchant")
        self.check_number = kwargs.get("check_number")
        self.personal_finance_category = kwargs.get("personal_finance_category")


class MockPlaidAccount:
    """Mock Plaid account object"""

    def __init__(self, **kwargs):
        self.account_id = kwargs.get("account_id", "acct-123")
        self.name = kwargs.get("name", "Checking Account")
        self.type = kwargs.get("type", "depository")
        self.subtype = kwargs.get("subtype", "checking")
        self.mask = kwargs.get("mask", "1234")
        self.balances = mock.MagicMock()
        self.balances.current = kwargs.get("balance", 5000.0)


class TestAccountBankStatementImportOnlinePlaid(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.currency_usd = cls.env.ref("base.USD")
        cls.currency_usd.write({"active": True})

        cls.now = fields.Datetime.now()

        # Create bank account
        cls.bank_account = cls.env["res.partner.bank"].create(
            {
                "acc_number": "123456789",
                "partner_id": cls.env.company.partner_id.id,
            }
        )

        # Create journal
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Plaid Bank Test",
                "type": "bank",
                "code": "PLDT",
                "currency_id": cls.currency_usd.id,
                "bank_statements_source": "online",
                "online_bank_statement_provider": "plaid",
                "bank_account_id": cls.bank_account.id,
            }
        )

        cls.provider = cls.journal.online_bank_statement_provider_id
        cls.provider.write(
            {
                "plaid_client_id": "test_client_id",
                "plaid_secret": "test_secret",
                "plaid_environment": "sandbox",
                "plaid_access_token": "test_access_token",
                "plaid_item_id": "test_item_id",
                "plaid_account_id": "acct-123",
                "plaid_account_type": "depository",
            }
        )

    def test_service_registration(self):
        """Test that Plaid is registered as an available service"""
        services = self.provider._get_available_services()
        service_codes = [s[0] for s in services]
        self.assertIn("plaid", service_codes)

    def test_connection_status_disconnected(self):
        """Test connection status when not connected"""
        provider = self.provider.copy(
            {
                "plaid_access_token": False,
                "plaid_account_id": False,
            }
        )
        self.assertEqual(provider.plaid_connection_status, "disconnected")

    def test_connection_status_connected(self):
        """Test connection status when connected"""
        self.assertEqual(self.provider.plaid_connection_status, "connected")

    def test_connection_status_error(self):
        """Test connection status when there's an error"""
        self.provider.plaid_error_message = "Test error"
        self.assertEqual(self.provider.plaid_connection_status, "error")

    def test_transaction_sign_inversion(self):
        """Test that Plaid amounts are inverted (positive -> negative for expenses)"""
        transaction = MockPlaidTransaction(
            transaction_id="txn-456",
            amount=100.0,  # Plaid: positive = expense
            name="Coffee Shop",
            merchant_name="Starbucks",
        )

        line = self.provider._plaid_transaction_to_line(transaction)

        # Odoo: negative = expense
        self.assertEqual(line["amount"], -100.0)
        self.assertEqual(line["unique_import_id"], "txn-456")
        self.assertEqual(line["payment_ref"], "Starbucks")

    def test_pending_transaction_unique_id(self):
        """Test that pending transactions get a different unique_import_id"""
        transaction = MockPlaidTransaction(
            transaction_id="txn-789",
            pending=True,
            amount=50.0,
        )

        line = self.provider._plaid_transaction_to_line(transaction)

        self.assertEqual(line["unique_import_id"], "pending-txn-789")

    def test_check_number_preserved(self):
        """Test that check numbers are preserved in payment_ref and ref"""
        transaction = MockPlaidTransaction(
            transaction_id="txn-check",
            amount=500.0,
            name="Check Payment",
            merchant_name=None,
            check_number="1234",
        )

        line = self.provider._plaid_transaction_to_line(transaction)

        self.assertIn("#1234", line["payment_ref"])
        self.assertEqual(line["ref"], "1234")

    def test_category_mapping(self):
        """Test that Plaid categories are mapped to accounts"""
        # Create a category mapping
        account = self.env["account.account"].search(
            [
                ("account_type", "=", "expense"),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )

        if account:
            self.env["plaid.category.mapping"].create(
                {
                    "name": "Test Category",
                    "plaid_category": "FOOD_AND_DRINK",
                    "account_id": account.id,
                }
            )

            transaction = MockPlaidTransaction(
                transaction_id="txn-food",
                amount=25.0,
                name="Restaurant",
                personal_finance_category=mock.MagicMock(
                    primary="FOOD_AND_DRINK",
                    detailed="FOOD_AND_DRINK_RESTAURANTS",
                ),
            )

            line = self.provider._plaid_transaction_to_line(transaction)

            self.assertEqual(line.get("counterpart_account_id"), account.id)

    def test_obtain_statement_data_not_connected(self):
        """Test error when trying to sync without connection"""
        provider = self.provider.copy(
            {
                "plaid_access_token": False,
            }
        )

        with self.assertRaises(UserError):
            provider._plaid_obtain_statement_data(
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )

    def mock_plaid_get_transactions(self):
        """Create mock for _plaid_get_transactions"""
        transactions = [
            MockPlaidTransaction(
                transaction_id="txn-001",
                amount=100.0,
                date=date(2024, 1, 15),
                name="Purchase 1",
                merchant_name="Store A",
            ),
            MockPlaidTransaction(
                transaction_id="txn-002",
                amount=-500.0,  # Credit/deposit
                date=date(2024, 1, 16),
                name="Deposit",
                merchant_name=None,
            ),
        ]
        return mock.patch(
            _provider_class + "._plaid_get_transactions",
            return_value=transactions,
        )

    def mock_plaid_get_balance(self):
        """Create mock for _plaid_get_balance"""
        return mock.patch(
            _provider_class + "._plaid_get_balance",
            return_value=5000.0,
        )

    def test_obtain_statement_data(self):
        """Test obtaining statement data from mocked Plaid API"""
        with self.mock_plaid_get_transactions(), self.mock_plaid_get_balance():
            lines, statement_values = self.provider._plaid_obtain_statement_data(
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )

        self.assertEqual(len(lines), 2)
        self.assertEqual(statement_values.get("balance_end_real"), 5000.0)

        # Check first transaction (expense)
        self.assertEqual(lines[0]["amount"], -100.0)
        self.assertEqual(lines[0]["unique_import_id"], "txn-001")

        # Check second transaction (deposit - sign inverted)
        self.assertEqual(lines[1]["amount"], 500.0)  # -(-500) = 500
        self.assertEqual(lines[1]["unique_import_id"], "txn-002")

    def test_credit_card_balance_inversion(self):
        """Test that credit card balances are inverted"""
        self.provider.plaid_account_type = "credit"

        with mock.patch(_provider_class + "._get_plaid_client") as mock_client:
            mock_api = mock.MagicMock()
            mock_client.return_value = mock_api

            mock_account = MockPlaidAccount(
                account_id="acct-123",
                balance=1500.0,  # Plaid: positive = amount owed
            )
            mock_response = mock.MagicMock()
            mock_response.accounts = [mock_account]
            mock_api.accounts_balance_get.return_value = mock_response

            balance = self.provider._plaid_get_balance()

            # Odoo: negative = credit card debt
            self.assertEqual(balance, -1500.0)

    def test_disconnect(self):
        """Test disconnecting Plaid connection"""
        self.provider.action_plaid_disconnect()

        self.assertFalse(self.provider.plaid_access_token)
        self.assertFalse(self.provider.plaid_item_id)
        self.assertFalse(self.provider.plaid_account_id)
        self.assertEqual(self.provider.plaid_connection_status, "disconnected")

    def test_reset_cursor(self):
        """Test resetting sync cursor"""
        self.provider.plaid_sync_cursor = "test-cursor"
        self.provider.action_plaid_reset_cursor()

        self.assertFalse(self.provider.plaid_sync_cursor)


class TestPlaidCategoryMapping(common.TransactionCase):
    def test_category_mapping_creation(self):
        """Test creating a category mapping"""
        mapping = self.env["plaid.category.mapping"].create(
            {
                "name": "Food and Drink",
                "plaid_category": "FOOD_AND_DRINK",
            }
        )

        self.assertTrue(mapping.exists())
        self.assertTrue(mapping.active)

    def test_category_mapping_unique_constraint(self):
        """Test that duplicate mappings are prevented"""
        self.env["plaid.category.mapping"].create(
            {
                "name": "Travel 1",
                "plaid_category": "TRAVEL",
            }
        )

        with self.assertRaises(Exception):
            self.env["plaid.category.mapping"].create(
                {
                    "name": "Travel 2",
                    "plaid_category": "TRAVEL",
                }
            )
