"""Additional wrapper contracts; synthetic, offline and not evaluation cases."""
import json
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('wrapper_contracts', Path(__file__).resolve().parents[1] / 'run.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def row(**overrides):
    value = dict(want='fix', passed=False, repaired_and_closed=False, closed_untouched=False,
                 model_selected_escalation=False, approval_pause=False, invalid_close=False,
                 runtime_enforced_stop=False, failed_tool_calls=0, rejected_tool_calls=0,
                 business_refusals=0, trace=[], elapsed_seconds=0.5, case_id='offline')
    value.update(overrides)
    return value


def test_all_scoring_counters_and_denominators():
    rows = [row(passed=True, repaired_and_closed=True),
            row(want='close_untouched', passed=True, closed_untouched=True),
            row(want='escalate', passed=True, model_selected_escalation=True),
            row(want='escalate', model_selected_escalation=True),
            row(model_selected_escalation=True), row(approval_pause=True),
            row(invalid_close=True), row(runtime_enforced_stop=True, failed_tool_calls=2,
                rejected_tool_calls=1, business_refusals=1, trace=[{'decision_error': 'offline'}])]
    result = w.summary(rows, rows, 5.0, True)
    counts = result['outcomes']
    assert counts['correct_repair'] == counts['correct_untouched_closure'] == 1
    assert counts['model_selected_escalation'] == 3
    assert counts['correct_model_escalation'] == counts['unnecessary_model_escalation'] == 1
    assert counts['incorrect_escalation_state'] == 1
    assert counts['approval_request'] == 1 and counts['unnecessary_human_intervention'] == 2
    assert counts['invalid_closure'] == counts['runtime_stop'] == 1
    assert counts['tool_failures'] == 2
    assert counts['tool_rejections'] == counts['business_refusals'] == 1
    assert result['case_seconds'] == 4 and result['wall_seconds'] == 5
    assert result['denominators'] == {'fix': 5, 'close_untouched': 1, 'escalate': 2}


def test_empty_partial_has_explicit_zero_counters():
    result = w.summary([], [dict(want='fix')], 0.1, False)
    assert set(result['outcomes']) == set(w.METRICS)
    assert not any(result['outcomes'].values())
    assert result['cases_planned'] == result['unrecorded_cases'] == 1
    assert result['cases_recorded'] == 0 and not result['complete']


@pytest.mark.parametrize('date', ['2020-01-01T00:00:00+00:00', '2999-01-01T00:00:00+00:00',
                                  '2026-10-30T09:00:00', 'not-a-date'])
def test_provenance_timestamp_rejected(date):
    with pytest.raises(ValueError):
        w.provenance('Author', date, 'Independent')


def test_line_order_and_decimal_spelling_do_not_evade_identity():
    a = dict(items=[['1.00', 2], ['2.50', 1]], tax='0.1500', total='5.18', locked=False)
    b = dict(items=[['2.500', 1], ['01.000', 2]], tax='0.15', total='05.180', locked=False)
    assert w.sha(w.canonical(w.transaction(a))) == w.sha(w.canonical(w.transaction(b)))


def test_changed_set_cannot_repeat_a_previously_attempted_transaction(tmp_path, monkeypatch):
    from test_wrapper import setup_run, transport_for, w as runner, evaluation
    args, root = setup_run(tmp_path, monkeypatch)
    monkeypatch.setattr(evaluation, 'TRANSPORT', transport_for(
        ['stage_invoice_fix', 'deploy', 'close', 'close', 'escalate'], []))
    original = runner.run(args)
    retained = (original / 'summary.json').read_bytes()
    records = json.loads(args.cases.read_text())
    records[0]['name'] = 'renamed_old_transaction'
    records[1]['total'] = '9.01'
    args.cases.write_text(json.dumps(records))
    args.sha256 = runner.sha(args.cases.read_bytes())
    with pytest.raises(FileExistsError):
        runner.run(args)
    assert (original / 'summary.json').read_bytes() == retained
