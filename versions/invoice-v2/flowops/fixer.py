"""Untrusted team simulation: proposes changes but NEVER decides closure.

Uses integer arithmetic. Does not import or inspect acceptance criteria or the
independent verifier, so its failures need not match the verifier's failures.
"""
from .models import BillState


def stage_invoice_total(bill: BillState) -> dict:
    subtotal_cents = sum(bill.item_cents)
    # Nonnegative cent values: half-up rounding of tax to the nearest cent.
    tax_cents = (subtotal_cents * bill.tax_bps * 2 + 10000) // 20000
    return {'stored_total_cents': subtotal_cents + tax_cents}


def stage_equal_split(bill: BillState) -> dict:
    left_cents = (bill.stored_total_cents + 1) // 2
    return {'split_cents': [left_cents, bill.stored_total_cents - left_cents]}
