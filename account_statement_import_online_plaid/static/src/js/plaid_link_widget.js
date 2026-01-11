odoo.define("account_statement_import_online_plaid.plaid_link", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");
    var framework = require("web.framework");

    var _t = core._t;

    var PlaidLinkAction = AbstractAction.extend({
        template: "PlaidLinkTemplate",

        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.linkToken = action.context.link_token;
            this.providerId = action.context.provider_id;
            this.plaidHandler = null;
        },

        start: function () {
            var self = this;
            this._super.apply(this, arguments);

            // Show loading state
            this.$el.find(".plaid-loading").show();
            this.$el.find(".plaid-error").hide();

            // Load Plaid Link SDK
            if (window.Plaid) {
                self._initPlaidLink();
            } else {
                var script = document.createElement("script");
                script.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
                script.onload = function () {
                    self._initPlaidLink();
                };
                script.onerror = function () {
                    self._showError(_t("Failed to load Plaid Link. Please try again."));
                };
                document.head.appendChild(script);
            }

            return this._super.apply(this, arguments);
        },

        _initPlaidLink: function () {
            var self = this;

            if (!this.linkToken) {
                this._showError(_t("Invalid link token. Please try again."));
                return;
            }

            try {
                this.plaidHandler = window.Plaid.create({
                    token: this.linkToken,
                    onSuccess: function (publicToken, metadata) {
                        self._onSuccess(publicToken, metadata);
                    },
                    onExit: function (err, metadata) {
                        self._onExit(err, metadata);
                    },
                    onEvent: function (eventName, metadata) {
                        self._onEvent(eventName, metadata);
                    },
                });

                // Hide loading and open Plaid Link
                this.$el.find(".plaid-loading").hide();
                this.plaidHandler.open();
            } catch (e) {
                console.error("Plaid initialization error:", e);
                this._showError(_t("Failed to initialize Plaid Link: ") + e.message);
            }
        },

        _onSuccess: function (publicToken, metadata) {
            var self = this;
            framework.blockUI();

            // Get selected account
            var selectedAccount = metadata.accounts && metadata.accounts[0];
            var accountId = selectedAccount ? selectedAccount.id : null;

            if (!accountId && metadata.account_id) {
                accountId = metadata.account_id;
            }

            this._rpc({
                route: "/plaid/exchange_token",
                params: {
                    public_token: publicToken,
                    provider_id: this.providerId,
                    account_id: accountId,
                    institution: metadata.institution || {},
                },
            })
                .then(function (result) {
                    framework.unblockUI();
                    if (result.success) {
                        self.displayNotification({
                            message: _t("Bank account connected successfully!"),
                            type: "success",
                        });
                        // Reload the form to show updated status
                        self.do_action({
                            type: "ir.actions.act_window_close",
                        });
                    } else {
                        self._showError(
                            _t("Failed to connect account: ") +
                                (result.error || _t("Unknown error"))
                        );
                    }
                })
                .catch(function (error) {
                    framework.unblockUI();
                    console.error("Token exchange error:", error);
                    self._showError(_t("Failed to connect account. Please try again."));
                });
        },

        _onExit: function (err) {
            if (err) {
                console.error("Plaid Link error:", err);
                if (err.error_code !== "USER_EXIT") {
                    this.displayNotification({
                        message: err.display_message || _t("Connection cancelled"),
                        type: "warning",
                    });
                }
            }
            // Close the dialog
            this.do_action({
                type: "ir.actions.act_window_close",
            });
        },

        _onEvent: function (eventName, metadata) {
            // Log events for debugging
            console.log("Plaid event:", eventName, metadata);
        },

        _showError: function (message) {
            this.$el.find(".plaid-loading").hide();
            this.$el.find(".plaid-error").show().find(".error-message").text(message);
        },

        destroy: function () {
            if (this.plaidHandler) {
                this.plaidHandler.exit();
            }
            this._super.apply(this, arguments);
        },
    });

    core.action_registry.add("plaid_link_action", PlaidLinkAction);

    return {
        PlaidLinkAction: PlaidLinkAction,
    };
});
