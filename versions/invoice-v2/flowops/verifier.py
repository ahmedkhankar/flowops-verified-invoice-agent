"""Independent, read-only acceptance verifier.

Intentionally uses Decimal, not the integer-cent implementation in fixer.py.
Never import the fixer or share its calculations. This is still a *simulation*;
real deployments require separately authored requirements and validation.
"""
from decimal import Decimal, ROUND_HALF_UP
from .models import AcceptanceSpec, BillState, InvoiceState, Verification


def check_state(bill: BillState, acceptance: AcceptanceSpec) -> Verification:
    checks: dict[str, bool] = {}
    native = isinstance(bill, InvoiceState)
    if acceptance.require_invoice_total or native:
        if native:
            subtotal = sum((Decimal(line.unit_price_cents) / Decimal('100') * Decimal(line.quantity)
                            for line in bill.line_items), Decimal('0'))
        else:
            subtotal = sum((Decimal(c) / Decimal('100') for c in bill.item_cents), Decimal('0'))
        percent = Decimal(bill.tax_bps) / Decimal('10000')
        gross = (subtotal * (Decimal('1') + percent)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        actual = Decimal(bill.stored_total_cents) / Decimal('100')
        checks['invoice_total'] = actual == gross
    if bill.split_cents is not None:
        parts = [Decimal(x) / Decimal('100') for x in bill.split_cents]
        total = Decimal(bill.stored_total_cents) / Decimal('100')
        checks['split_sum'] = len(parts) == 2 and sum(parts) == total
        checks['split_balance'] = len(parts) == 2 and abs(parts[0] - parts[1]) <= Decimal('0.01')
        checks['nonnegative_parts'] = len(parts) == 2 and all(x >= 0 for x in parts)
    if acceptance.require_service_ready or native:
        checks['service_ready'] = bill.service_ready
    issues = tuple(name for name, passed in checks.items() if not passed)
    return Verification(passed=all(checks.values()), checks=checks,
                        issues=issues, checked_version=bill.version)
