# Copyright 2025 Kencove
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Online Bank Statements: Plaid",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "website": "https://github.com/OCA/bank-statement-import",
    "author": "Kencove, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "account_statement_import_online",
    ],
    "external_dependencies": {
        "python": ["plaid", "PyJWT"],
    },
    "data": [
        "security/ir.model.access.csv",
        "data/plaid_category_data.xml",
        "views/online_bank_statement_provider.xml",
        "views/plaid_category_mapping.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_statement_import_online_plaid/static/src/js/plaid_link_widget.js",
            "account_statement_import_online_plaid/static/src/xml/plaid_link_templates.xml",
        ],
    },
}
