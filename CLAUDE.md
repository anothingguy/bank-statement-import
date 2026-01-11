# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in
this repository.

## Overview

This is the **OCA Bank Statement Import** repository - a collection of Odoo 16.0 addons
for bank statement parsing and import. It contains 14 modules:

- **Base modules**: `account_statement_import_base`, `account_statement_import_file`,
  `account_statement_import_file_reconcile_oca`
- **Format parsers**: CAMT.053/054 (`_camt`, `_camt54`), OFX (`_ofx`), QIF (`_qif`),
  spreadsheets (`_sheet_file`)
- **Online providers**: Base (`_online`), GoCardless, OFX, PayPal, Ponto, Qonto

## Development Commands

This repository is part of a Doodba-based Odoo deployment. Use invoke tasks from the
parent project:

```bash
# Install modules
invoke install --modules account_statement_import_base,account_statement_import_file

# Test specific module
invoke test --cur-file <path-to-file-in-module>
invoke test --modules account_statement_import_camt

# Lint (runs pre-commit on all files)
invoke lint
```

## Architecture

### Module Structure

Each addon follows this layout:

```
addon_name/
├── __manifest__.py       # Dependencies, version, data files
├── models/               # Business logic (Model inheritance)
├── wizard/               # Transient models for import wizards
├── views/                # XML view definitions
├── tests/                # Unit tests
│   └── test_files/       # Sample bank files for parser tests
├── readme/               # OCA documentation fragments
└── i18n/                 # Translations (.po files)
```

### Key Patterns

**Parser Architecture** - Format parsers (CAMT, OFX, QIF) implement abstract models or
parser methods that:

1. Accept raw file content
2. Parse into statement dictionaries
3. Return normalized data for import

**Online Provider Pattern** - `account_statement_import_online` provides base class
extended by each bank integration (GoCardless, PayPal, etc.) with:

- API authentication handling
- Scheduled statement fetching
- Provider-specific field mappings

**Extension Hooks** - Core methods designed for customization:

- `_statement_line_import_speeddict()` - Cache lookups for performance
- `_statement_line_import_update_hook()` - Customize reconciliation
- `_statement_line_import_update_unique_import_id()` - Custom import ID logic

### Model Inheritance

Modules extend these core Odoo models:

- `account.journal` - Adds online provider configuration
- `account.bank.statement.line` - Extends import behavior
- `res.partner.bank` - Enhanced account matching

## Coding Standards

### Python (OCA Strict)

```python
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class AccountJournal(models.Model):
    _inherit = "account.journal"
```

- No `print()`, use `_logger`
- Prefer ORM over raw SQL
- Use domain expressions for queries

### XML

- 4-space indentation
- ID format: `view_<model>_form`, `action_<model>`
- Use `xpath` with `position` for view inheritance

### Commit Format

```
[16.0][ADD|FIX|REF|IMP|REM|MIG] <addon>: <summary>
```

## Testing

Tests use `odoo.tests.common.TransactionCase` or `SavepointCase`. Parser tests compare
output against `.pydata` golden files in `test_files/`.

```bash
invoke test --cur-file account_statement_import_camt/tests/test_import_bank_statement.py
```

## Pre-commit Hooks

Key checks enforced:

- `black` + `isort` (88-char lines)
- `flake8` with bugbear
- `pylint-odoo` (mandatory checks block merge)
- `prettier` for XML/JSON/YAML
- OCA manifest and README validation
