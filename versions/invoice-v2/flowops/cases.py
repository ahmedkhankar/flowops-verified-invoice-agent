"""Loads demo cases. Acceptance criteria remain outside planner observations."""
import json
from pathlib import Path
from .models import AcceptanceSpec, CaseSpec, InvoiceState

CASE_FILE = Path(__file__).resolve().parent.parent / 'cases' / 'demo_cases.json'


def load_cases(path: Path | str = CASE_FILE) -> dict[str, CaseSpec]:
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    cases = {}
    for record in raw:
        cid = record['case_id']
        if cid in cases:
            raise ValueError(f'Duplicate case id: {cid}')
        bill = record['initial_bill']
        if 'line_items' in bill:
            InvoiceState(**bill)  # Native schema validation, no expected-answer conversion.
        elif not 0 <= int(bill['tax_bps']) <= 10000 or any(x < 0 for x in bill['item_cents']):
            raise ValueError(f'Invalid bill data for {cid}')
        cases[cid] = CaseSpec(
            case_id=cid, title=record['title'], request=record['request'],
            risk=record['risk'], reason=record.get('reason', ''),
            initial_bill=bill, acceptance=AcceptanceSpec(**record.get('acceptance', {})),
            policy_flags=tuple(record.get('policy_flags', [])),
            simulated_noop_deploy=bool(record.get('simulated_noop_deploy', False)),
        )
    return cases
