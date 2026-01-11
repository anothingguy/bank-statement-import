Connecting a Bank Account
~~~~~~~~~~~~~~~~~~~~~~~~~

1. Navigate to the bank journal's online provider settings
2. Ensure Plaid credentials are configured
3. Click **Connect Bank Account**
4. Plaid Link will open in a modal window
5. Search for and select your bank
6. Enter your bank credentials (Plaid handles this securely)
7. Select which account to sync
8. The connection will be established automatically

Manual Sync
~~~~~~~~~~~

To manually pull transactions:

1. Open the online provider settings
2. Click **Pull Online Bank Statement** in the header
3. Select the date range
4. Click **Pull**

Automatic Sync
~~~~~~~~~~~~~~

Transactions are automatically pulled based on the configured schedule:

* Set **Interval Number** and **Interval Type** (e.g., "1 day")
* The **Next Run** field shows when the next sync will occur
* Set **Statement Creation Mode** to control how statements are grouped
  (daily, weekly, or monthly)

Handling Errors
~~~~~~~~~~~~~~~

If a connection error occurs (e.g., bank requires re-authentication):

1. The connection status will show as **Error**
2. Click **Reconnect** to re-authenticate with Plaid Link
3. The error message will provide details about the issue

Disconnecting
~~~~~~~~~~~~~

To disconnect a bank account:

1. Open the online provider settings
2. Click **Disconnect**
3. This removes the stored access token but preserves imported statements
