This module provides integration with `Plaid <https://plaid.com>`_ for automatic
bank statement synchronization.

Plaid is a financial technology company that enables applications to connect
with users' bank accounts. It supports thousands of financial institutions
primarily in the United States, including:

* Major banks (Chase, Bank of America, Wells Fargo, etc.)
* Regional banks (Huntington, PNC, First Commonwealth, etc.)
* Credit unions
* Credit card accounts

Features:

* **Plaid Link Integration**: Seamless bank authentication using Plaid's
  secure Link interface embedded in Odoo
* **Automatic Synchronization**: Schedule regular transaction syncs
  (hourly, daily, weekly)
* **Incremental Sync**: Uses Plaid's transactions/sync API for efficient
  updates
* **Pending Transactions**: Optionally import pending transactions that
  update when posted
* **Category Mapping**: Auto-categorize transactions based on Plaid's
  personal finance categories
* **Credit Card Support**: Proper handling of credit card transactions
  with correct sign conventions
* **Check Number Preservation**: Maintains check numbers for check
  transactions
