"""FlowOps Streamlit dashboard. Run: streamlit run app.py"""
import json
import os
import streamlit as st
from flowops.cases import load_cases
from flowops.engine import WorkflowSession
from flowops.planner import OllamaPlanner, RulesPlanner, HostedPlanner

st.set_page_config(page_title='FlowOps | Verified Autonomy', page_icon='🔄', layout='wide')

st.title('FlowOps AI')
st.caption('Autonomous merchant integration resolution · Safe simulation · HUMAIN Challenge 3')
st.info('Demo environment only. Synthetic bills and team actions; this application does not access real merchant data or payment systems.')

cases = load_cases()
with st.sidebar:
    st.header('Experiment setup')
    case_id = st.selectbox('Scenario', list(cases), format_func=lambda cid: cases[cid].title)
    planner_kind = st.radio('Planning mode', ['Rules baseline', 'Hosted LLM API', 'Ollama local AI'], help='The rules baseline is not an AI agent.')
    model_name = ''
    base_url = None
    fallback_rules = False
    if planner_kind == 'Hosted LLM API':
        model_name = st.text_input('Hosted model', value=os.getenv('FLOWOPS_LLM_MODEL', ''))
        base_url = st.text_input('Hosted API base URL', value=os.getenv('FLOWOPS_LLM_BASE_URL', 'https://api.openai.com/v1'))
        st.caption('API key is read from FLOWOPS_LLM_API_KEY; never included in audit downloads.')
        fallback_rules = st.checkbox('Allow explicit rules fallback on API transport failure', value=False)
    elif planner_kind == 'Ollama local AI':
        model_name = st.text_input('Ollama model', value='qwen3:4b')
    if st.button('Start / reset scenario', use_container_width=True, type='primary'):
        st.session_state['flow_session'] = WorkflowSession(cases[case_id])
        st.session_state['scenario_id'] = case_id
    st.divider()
    st.markdown('**Security controls**')
    st.caption('The model cannot supply a team identity, approval, or arbitrary tool arguments. Deployment is enforced by a trusted runtime.')

if 'flow_session' not in st.session_state or st.session_state.get('scenario_id') != case_id:
    st.session_state['flow_session'] = WorkflowSession(cases[case_id])
    st.session_state['scenario_id'] = case_id
session = st.session_state['flow_session']
try:
    if planner_kind == 'Hosted LLM API':
        planner = HostedPlanner(model=model_name, base_url=base_url, fallback=fallback_rules)
    elif planner_kind == 'Ollama local AI':
        planner = OllamaPlanner(model=model_name)
    else:
        planner = RulesPlanner()
except ValueError as exc:
    st.warning(str(exc))
    st.stop()

try:
    observed = session.observe()
except Exception:
    st.error('Independent verification unavailable; ticket escalated, never closed.')
    observed = {'world': session.bill.snapshot(), 'status': session.status,
                'verification': session.verification.as_dict()}

st.subheader(cases[case_id].title)
st.write(cases[case_id].request)
left, middle, right, extra = st.columns(4)
left.metric('Ticket status', session.status)
middle.metric('Independent verification', 'PASS' if session.verification.passed else 'FAIL')
right.metric('Agent steps', session.step_count)
extra.metric('Deploy attempts', session.deploy_attempts)

col_actions, col_world = st.columns([1, 1.1])
with col_actions:
    st.markdown('### Agent controls')
    if session.status == 'PAUSED_APPROVAL':
        st.warning('Human approval required. No modifying action can run until approved.')
        reviewer = st.text_input('Reviewer (simulation only)', value='Human reviewer')
        if st.button('Record human approval', type='primary'):
            try:
                session.grant_human_approval(reviewer)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    else:
        one, many = st.columns(2)
        if one.button('One agent step', disabled=session.status != 'ACTIVE', use_container_width=True):
            try:
                session.step(planner)
                st.rerun()
            except Exception as exc:
                st.error(f'Execution stopped: {exc}')
        if many.button('Run to outcome', disabled=session.status != 'ACTIVE', type='primary', use_container_width=True):
            try:
                session.run(planner, max_steps=12)
                st.rerun()
            except Exception as exc:
                st.error(f'Execution stopped: {exc}')
    st.markdown('### Acceptance checks')
    for name, passed in session.verification.checks.items():
        st.write(('✅' if passed else '❌') + ' ' + name.replace('_', ' ').title())
    if session.status == 'CLOSED_VERIFIED':
        st.success('Ticket closed with independent verification and any required approval.')
    if session.status == 'ESCALATED':
        st.error('Ticket escalated: no safe verified closure.')

with col_world:
    st.markdown('### Observed world (what the agent may read)')
    # The acceptance spec is purposefully never included here.
    st.json(observed, expanded=False)
    st.markdown('### Current bill')
    bill = session.bill
    a, b, c = st.columns(3)
    a.metric('Stored total', f'{bill.stored_total_cents / 100:.2f} SAR')
    b.metric('Split A', f'{bill.split_cents[0] / 100:.2f} SAR')
    c.metric('Split B', f'{bill.split_cents[1] / 100:.2f} SAR')

st.markdown('### Auditable action history')
st.dataframe(session.history, use_container_width=True, hide_index=True)
st.download_button('Download JSON audit report',
    data=json.dumps(session.report(), indent=2, ensure_ascii=False),
    file_name=f'flowops_{case_id}_audit.json', mime='application/json')
st.caption(f'Selected planner: {planner.name}. Requested and provider-reported models are recorded separately; neither is independently verified. Explicit rules fallbacks are labelled per decision. Demo cases are builder-authored, not independent evaluation data. Earlier Qwen3 simulation metrics do not describe another model.')
