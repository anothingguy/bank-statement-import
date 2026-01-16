# Copyright 2025 Kencove
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PlaidCategoryMapping(models.Model):
    _name = "plaid.category.mapping"
    _description = "Plaid Category to Account Mapping"
    _order = "plaid_category"

    name = fields.Char(
        required=True,
        help="Display name for this category mapping",
    )
    plaid_category = fields.Char(
        string="Plaid Category Code",
        required=True,
        index=True,
        help="Plaid primary category code (e.g., FOOD_AND_DRINK, TRAVEL)",
    )
    plaid_category_detailed = fields.Char(
        string="Plaid Detailed Category",
        help="Optional: Plaid detailed category for more specific mapping",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Expense Account",
        domain="[('account_type', 'in', ['expense', 'expense_depreciation', 'expense_direct_cost'])]",
        help="Account to use for automatic categorization of transactions",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
        help="Leave empty to apply to all companies",
    )
    active = fields.Boolean(
        default=True,
    )
    notes = fields.Text(
        help="Additional notes about this category mapping",
    )

    _sql_constraints = [
        (
            "unique_category_company",
            "UNIQUE(plaid_category, plaid_category_detailed, company_id)",
            "A mapping for this Plaid category already exists for this company.",
        ),
    ]
