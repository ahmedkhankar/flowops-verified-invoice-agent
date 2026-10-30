"""Judge-facing presentation layer; imports the unchanged frozen Invoice v2 engine."""
from copy import deepcopy
import json
import streamlit as st
import ui_core as core

st.set_page_config(page_title='FlowOps | Merchant Operations', page_icon='🔄', layout='wide')
st.markdown('''<style>
.block-container{max-width:1400px;padding-top:2rem}
[data-testid="stMetric"]{background:#111e30;border:1px solid #22334b;border-radius:12px;padding:14px}
[data-testid="stMetricValue"]{font-size:1.45rem}
h1{letter-spacing:-.04em} div[data-testid="stExpander"]{border-color:#22334b}
</style>''', unsafe_allow_html=True)

try:
    protected = core.verify_integrity()
except Exception as exc:
    st.error(f'Frozen evidence integrity check failed. Execution disabled. {exc}')
    st.stop()


def reset_replay():
    st.session_state['replay_position'] = 0


def line_table(state):
    if 'line_items' in state:
        return [{'Unit price': core.money(x['unit_price_cents']), 'Quantity': x['quantity'],
                 'Line amount': core.money(x['unit_price_cents'] * x['quantity'])}
                for x in state['line_items']]
    return [{'Legacy line amount': core.money(c)} for c in state['item_cents']]


def render_view(view):
    state, before = view['state'], view['before']
    a, b, c, d = st.columns(4)
    a.metric('Ticket state', view['status'])
    b.metric('Independent checks', 'PASS' if view['verification']['passed'] else 'FAIL')
    c.metric('Stored total', core.money(state['stored_total_cents']))
    d.metric('Merchant lock', 'LOCKED' if state.get('locked') else 'UNLOCKED')
    st.caption(f"Decision attempts shown: {view['position']} · Invoice version: {state['version']} · VAT: {state['tax_bps']} basis points · Monetary display uses exact cent units, not real payments.")
    left, right = st.columns([1.05, 1])
    with left:
        st.subheader('Invoice & persisted state')
        st.dataframe(line_table(state), hide_index=True, use_container_width=True)
        if state.get('split_cents') is not None:
            st.write('Actual split allocations:', ' / '.join(core.money(x) for x in state['split_cents']))
        else:
            st.caption('No split allocation. No synthetic split or irrelevant split check is introduced.')
        st.dataframe([
            {'Persisted field': 'Stored total', 'Before last decision': core.money(before['stored_total_cents']), 'After last decision': core.money(state['stored_total_cents'])},
            {'Persisted field': 'Version', 'Before last decision': str(before['version']), 'After last decision': str(state['version'])},
            {'Persisted field': 'Merchant lock', 'Before last decision': str(before.get('locked', False)), 'After last decision': str(state.get('locked', False))},
        ], hide_index=True, use_container_width=True)
        if view['pending']:
            st.warning('STAGED ONLY — this proposal has not changed persisted invoice state.')
            st.json(view['pending'])
        else:
            st.caption('Pending correction: none.')
    with right:
        st.subheader('Independent verification')
        st.dataframe([{'Check': key, 'Result': 'PASS' if value else 'FAIL'}
                      for key, value in view['verification']['checks'].items()], hide_index=True, use_container_width=True)
        st.caption('Separate Decimal verifier; checks persisted values, not model prose. Code-separated, not externally certified.')
        if view['status'] == 'CLOSED_VERIFIED':
            st.success('Verified closure. Persisted checks passed; no pending patch.')
        elif view['status'] == 'ESCALATED':
            st.warning('Unresolved ticket. Inspect provenance below: a model escalation is not a runtime stop.')
        elif view['status'] == 'PAUSED_APPROVAL':
            st.warning('Human review pending. This is not a successful closure or an escalation.')
        else:
            st.info('Workflow in progress. The AI chooses actions; tools enforce arithmetic, authorization and business restrictions.')
        if view['frames']:
            step = view['frames'][-1]
            st.markdown('**Latest AI-selected action**')
            st.code(step.get('chosen_action', 'No decision — provider/planning failure'), language=None)
            st.write(step.get('chosen_reason', step.get('decision_error', 'No model rationale recorded.')))
            st.caption('A model rationale can be wrong. Read it alongside actual checks and allowed actions.')
            obs = step['observation_before']
            st.caption('Permitted before this decision: ' + ', '.join(obs['allowed_actions']))
    st.subheader('Decision & tool execution trail')
    if not view['frames']:
        st.info('No decisions shown yet. Advance the recorded replay or explicitly start live execution.')
        return
    st.dataframe([{'Step': i, 'AI-selected action': row.get('chosen_action', 'No decision'),
                   'Tool result': (row.get('tool_result') or {}).get('action', 'No tool executed'),
                   'Persisted total': core.money(row.get('state_after', row['observation_before']['world'])['stored_total_cents']),
                   'Version': row.get('state_after', row['observation_before']['world'])['version'],
                   'Independent checks': 'PASS' if row.get('verification_after', row['observation_before']['verification'])['passed'] else 'FAIL'}
                  for i, row in enumerate(view['frames'], 1)], hide_index=True, use_container_width=True)
    with st.expander('Inspect latest tool result and exact model evidence'):
        last = view['frames'][-1]
        st.json({key: last[key] for key in ('tool_result', 'request', 'response', 'observation_before') if key in last})


st.title('FlowOps')
st.markdown('**Merchant operations, owned through verified outcomes.**')
st.caption('HUMAIN Challenge 3 · Native Invoice v2 · Simulation only — no real POS or payment access')
with st.sidebar:
    st.header('Execution source')
    mode = st.radio('Mode', ['Saved Qwen replay', 'Live Qwen execution'])
    st.markdown('**qwen3:4b-instruct**')
    st.caption('Temperature 0 · Thinking disabled · Rules fallback OFF')
    st.divider()
    st.success('Frozen v2 engine and evidence intact')
    st.caption(f'{protected} protected files checked. Presentation layer: invoice-ui-v1. No engine or benchmark changes.')
    st.caption('Replay never calls AI. Live controls use the actual local planner; there is no rules execution mode here.')

workbench, evaluation_tab = st.tabs(['Merchant workbench', 'Recorded evaluation'])
with workbench:
    if mode == 'Saved Qwen replay':
        st.info('SAVED-RUN REPLAY · Recorded Qwen decisions from the first frozen run. No new model call, tool execution or state mutation.')
        names = core.replay_names()
        labels = {'bill04': 'bill04 · Repair with explicit verification', 'bill09': 'bill09 · Native locked invoice',
                  'bill11': 'bill11 · Already-correct invoice failure'}
        selected = st.selectbox('Saved invoice scenario', names, index=names.index('bill04'),
                                format_func=lambda x: labels.get(x, x), on_change=reset_replay, key='saved_scenario')
        record = core.saved_case(selected)
        total = len(record['trace'])
        if 'replay_position' not in st.session_state:
            st.session_state['replay_position'] = 0
        one, end, restart, progress = st.columns([1, 1, 1, 2])
        if one.button('Next recorded step', disabled=st.session_state['replay_position'] >= total, type='primary'):
            st.session_state['replay_position'] += 1
        if end.button('Show final outcome'):
            st.session_state['replay_position'] = total
        if restart.button('Restart replay'):
            reset_replay()
        progress.caption(f"{st.session_state['replay_position']} / {total} recorded decisions shown")
        position = st.slider('Recorded decisions shown', 0, total, key='replay_position')
        view = core.recorded_view(record, position)
        render_view(view)
        if view['complete']:
            st.markdown('**Recorded disposition:** ' + core.disposition(record['report']))
            if record['passed']:
                st.success('This recorded case met its expected diagnostic outcome.')
            else:
                st.error('This recorded case failed its expected outcome. Preserved without tuning or relabelling.')
            if record['want'] == 'close_untouched' and not record['passed']:
                st.write('Already correct: all checks passed and close was available, but Qwen requested approval. Safe unchanged data is not autonomous task completion.')
        export = {'presentation_version': 'invoice-ui-v1', 'mode': 'saved_replay',
                  'source_run': str(core.RUN.relative_to(core.PROJECT)), 'displayed_decisions': position,
                  'saved_record': record}
        st.download_button('Export recorded audit JSON', json.dumps(export, indent=2),
                           file_name=f'flowops_replay_{selected}.json', mime='application/json')
        st.caption('Export contains the full original case plus replay provenance, not a newly executed run.')
    else:
        st.warning('LIVE AI EXECUTION · New local model calls and simulated business actions. Not the historical 10/12 evaluation; results are not guaranteed.')
        source = st.radio('Merchant issue intake', ['Existing invoice / compatibility scenario', 'New merchant invoice'], horizontal=True)
        cases = core.seed_cases()
        if source == 'Existing invoice / compatibility scenario':
            case_key = st.selectbox('Invoice or split-bill scenario', list(cases), index=list(cases).index('bill04'))
            case = cases[case_key]
            st.write(case.request)
            if st.button('Create live ticket', type='primary'):
                st.session_state['live_ticket'] = core.LiveTicket(case)
        else:
            with st.form('merchant_intake'):
                issue = st.text_area('Merchant issue', 'Investigate this disputed invoice and resolve safely, or escalate if no permitted resolution exists.')
                rows = st.data_editor([{'Unit price': '8.20', 'Quantity': 3}, {'Unit price': '2.35', 'Quantity': 2}, {'Unit price': '1.10', 'Quantity': 1}],
                                      num_rows='dynamic', hide_index=True, use_container_width=True,
                                      column_config={'Unit price': st.column_config.TextColumn('Unit price', required=True),
                                                     'Quantity': st.column_config.NumberColumn('Quantity', min_value=1, step=1, required=True)})
                a, b = st.columns(2)
                vat = a.text_input('VAT fraction (0.05 means 5%)', '0.05')
                total_value = b.text_input('Stored invoice total', '35.00')
                locked = st.checkbox('Merchant system lock')
                needs_approval = st.checkbox('Policy requires human approval (high risk)')
                create = st.form_submit_button('Create native invoice ticket', type='primary')
            if create:
                try:
                    case = core.custom_case(issue, rows, vat, total_value, locked, needs_approval)
                    st.session_state['live_ticket'] = core.LiveTicket(case)
                except (ValueError, TypeError, KeyError) as exc:
                    st.error('Intake rejected without execution: ' + str(exc))
        ticket = st.session_state.get('live_ticket')
        if ticket is None:
            st.info('Create a ticket to inspect native state. No model call is made at intake.')
        else:
            st.caption(f'Ticket {ticket.ticket_id[:8]} · {ticket.session.case.case_id} · Creating another ticket resets only this interactive session.')
            observation = ticket.observe()
            if ticket.session.status == 'PAUSED_APPROVAL':
                st.warning(core.disposition(ticket.session.report()) + '. Only an explicit simulated human approval can resume it; approval cannot override a lock.')
                with st.form('human_approval'):
                    reviewer = st.text_input('Reviewer identity (simulation only)')
                    ack = st.checkbox('I am recording a human decision, not an AI-granted approval')
                    approve = st.form_submit_button('Record simulated human approval')
                if approve:
                    try:
                        if not ack:
                            raise ValueError('Human confirmation is required')
                        ticket.approve(reviewer)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            enabled = st.checkbox('Enable new local Qwen calls', value=False)
            a, b = st.columns(2)
            active = ticket.session.status == 'ACTIVE'
            if a.button('Execute next AI step', disabled=not enabled or not active, type='primary'):
                with st.spinner('Qwen is selecting one permitted action; tools enforce the outcome…'):
                    ticket.step()
                st.rerun()
            if b.button('Run AI to outcome (12-step total limit)', disabled=not enabled or not active):
                with st.spinner('Executing the native workflow with the real local Qwen planner…'):
                    ticket.run()
                st.rerun()
            if ticket.last_error:
                st.error('Execution stopped without rules fallback: ' + ticket.last_error)
            render_view(ticket.view())
            st.markdown('**Current disposition:** ' + core.disposition(ticket.session.report()))
            decisions = ticket.session.planner_decisions
            if decisions:
                st.caption('Last provider-reported model: ' + str(decisions[-1]['provider_reported_model']) + ' · identity is provider-reported, not independently attested.')
            if observation:
                with st.expander('Current native observation and tool preconditions'):
                    st.json(observation)
            st.download_button('Export live ticket audit JSON', json.dumps(ticket.export(), indent=2),
                               file_name=f'flowops_live_{ticket.ticket_id[:8]}.json', mime='application/json')
            st.caption('Live session state is in memory; export before resetting or stopping the server. No writes to the benchmark evidence.')

with evaluation_tab:
    st.subheader('The first frozen Qwen evaluation')
    st.caption('Recorded source: runs/invoice-v2-exam-ollama-20261030T080451Z/ · Never replaced by an interactive ticket result.')
    summary, rows = core.recorded_evaluation()
    a, b, c, d = st.columns(4)
    a.metric('Correct outcomes', f"{summary['passed']}/{summary['cases']}")
    b.metric('Repairs (incorrect)', f"{summary['incorrect_invoices_repaired_and_closed']}/{sum(r['want'] == 'fix' for r in rows)}")
    c.metric('Escalations (locked)', f"{summary['locked_invoices_model_escalated']}/{sum(r['want'] == 'escalate' for r in rows)}")
    d.metric('Untouched closures', f"{summary['correct_invoices_closed_untouched']}/{sum(r['want'] == 'close_untouched' for r in rows)}")
    st.error('Two failures: already-correct invoices were unnecessarily referred for approval. No automatic closure or rerun was used to hide them.')
    st.write(f"{summary['model_calls']} model calls · {summary['elapsed_seconds']:.4f} seconds case execution · {summary['invalid_closures']} invalid closures · {summary['runtime_enforced_stops']} runtime stops · {summary['failed_tool_calls']} failed tools · {summary['rejected_tool_calls']} rejected tools")
    st.dataframe([{'Invoice': row['case_id'], 'Expected': row['want'], 'Result': 'PASS' if row['passed'] else 'FAIL',
                   'Recorded outcome': core.disposition(row['report']), 'Actions': ' → '.join(row['selected_actions']),
                   'Steps': row['steps']} for row in rows], hide_index=True, use_container_width=True)
    st.info('126 reported passing v2 regression tests are software evidence, not model performance. This is one batch of 12 known diagnostic cases, not a held-out benchmark.')
    st.caption('Separate final rules baseline: 12/12, 28 actions, zero model calls. The model is not claimed to outperform rules. No real POS integration, production-readiness or measured productivity savings claim.')
    with st.expander('Frozen configuration and source metadata'):
        st.json(core.read_json(core.RUN / 'metadata.json'))
    st.download_button('Export recorded evaluation summary', json.dumps(summary, indent=2),
                       file_name='flowops_recorded_evaluation_summary.json', mime='application/json')

st.divider()
st.caption('AI selects actions. Trusted tools calculate, authorize and deploy. A separate verifier checks persisted state. Escalation, review and runtime stops are distinct outcomes. All operations here are simulated.')
