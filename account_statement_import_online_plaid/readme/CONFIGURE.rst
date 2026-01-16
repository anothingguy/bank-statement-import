Plaid Account Setup
~~~~~~~~~~~~~~~~~~~

1. Create a Plaid account at https://dashboard.plaid.com/signup
2. Navigate to the API section to get your credentials:

   * Client ID
   * Secret (for your chosen environment)

3. Choose your environment:

   * **Sandbox**: Free testing with fake data
   * **Development**: Test with real banks (100 live Items)
   * **Production**: Full production access (requires approval)

Module Configuration
~~~~~~~~~~~~~~~~~~~~

1. Go to **Accounting > Configuration > Bank Accounts > Online Providers**
2. Create a new provider or edit an existing journal's online provider
3. Select **Plaid** as the service
4. Enter your Plaid credentials:

   * Client ID
   * Secret
   * Environment

5. Click **Connect Bank Account** to initiate Plaid Link
6. Follow the prompts to authenticate with your bank
7. Select the account to sync
8. Configure the sync schedule (interval and statement creation mode)

Category Mapping (Optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To enable automatic expense categorization:

1. Go to **Accounting > Configuration > Plaid Categories**
2. For each Plaid category, assign an expense account
3. When transactions are imported, they will automatically be assigned
   the corresponding account

Webhook Configuration (Optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For real-time notifications about connection status:

1. In your Plaid Dashboard, configure webhooks to point to:
   ``https://your-odoo-domain/plaid/webhook``
2. This enables notifications for:

   * Connection errors requiring re-authentication
   * New transactions available
   * Transaction removals
