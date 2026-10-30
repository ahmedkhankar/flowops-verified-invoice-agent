"""Merchant operations product surface, separate from frozen implementation/evaluation."""
from html import escape
import json
from pathlib import Path
import sys

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent))
import service as svc

st.set_page_config(page_title='FlowOps | Merchant Operations', page_icon='◈', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
:root{color-scheme:dark} .stApp{background:#0a1220;color:#edf3fa}
[data-testid="stSidebar"]{background:#101d30;border-right:1px solid #25364b}
.block-container{max-width:1460px;padding:2rem 2.7rem 4rem}
h1,h2,h3{letter-spacing:-.035em!important}h1{font-size:2.65rem!important}h3{font-size:1.2rem!important}
p,li{line-height:1.55} .eyebrow{color:#64dfc4;font-size:.76rem;letter-spacing:.16em;font-weight:750;text-transform:uppercase}
.muted{color:#a2b4c9}.hero{padding:24px 28px;border:1px solid #29415a;border-radius:16px;background:linear-gradient(110deg,#122b3b,#111d31);margin:12px 0 24px}
.hero h2{margin:0 0 8px;font-size:1.65rem}.hero p{margin:0;color:#b7c7d8}
.card{padding:20px 22px;border:1px solid #29394e;border-radius:14px;background:#111e30;margin-bottom:16px}
.pill{display:inline-block;border-radius:30px;padding:5px 12px;background:#193d3a;color:#8cebd6;font-size:.76rem;font-weight:700;margin-right:6px}
.pill.warn{background:#493821;color:#ffd796}.pill.source{background:#25354e;color:#d9e7fd}
.timeline{border-left:2px solid #33526b;padding:0 0 20px 20px;margin-left:9px}
.timeline h4{font-size:1rem;margin:0 0 6px}.timeline p{font-size:.9rem;margin:4px 0;color:#b4c5d9}
.amount{font-size:2.25rem;font-weight:750;letter-spacing:-.05em}.divider{height:1px;background:#26384e;margin:14px 0}
[data-testid="stMetric"]{background:#111f31;border:1px solid #2b3d53;border-radius:12px;padding:16px}
[data-testid="stMetricLabel"]{color:#adbed2} [data-testid="stMetricValue"]{font-size:1.65rem}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:#4ad8bb;color:#072c2b;border:0;font-weight:750}
.stButton>button,.stFormSubmitButton>button{border-radius:9px;min-height:42px}
.stButton>button:disabled{background:#162436!important;color:#7b8ba2!important;opacity:.65}
[data-testid="stHeader"]{background:transparent}#MainMenu,footer{visibility:hidden}
@media(max-width:900px){.block-container{padding:1.2rem}.hero{padding:18px}}
</style>''', unsafe_allow_html=True)
try:
    svc.verify_integrity()
except Exception:
    st.error('Protected engine or evidence files differ from this UI release. Execution is blocked. Restore the pinned files before continuing.')
    st.stop()

if 'tickets' not in st.session_state:
    st.session_state.tickets = {}
if '_next_page' in st.session_state:
    st.session_state.page = st.session_state.pop('_next_page')
if 'page' not in st.session_state:
    st.session_state.page = 'Overview'


def go(page, ticket_id=None):
    st.session_state.page = page
    if ticket_id:
        st.session_state.active_ticket = ticket_id


def badge(label, warning=False):
    st.markdown(f'<span class="pill {"warn" if warning else "source"}">{escape(label)}</span>', unsafe_allow_html=True)


def source_header(ticket):
    badge(ticket.mode, ticket.mode == 'RULES BASELINE')
    if ticket.mode == 'LIVE MODEL':
        st.caption(f'Real local model calls only when you press Run or Step · {ticket.model} · temperature 0 · thinking off · rules fallback OFF')
    else:
        st.caption('Deterministic non-AI baseline. Never counted as Qwen execution.')


@st.cache_data(ttl=15, show_spinner=False)
def get_runtime(model):
    return svc.runtime_status(model)


with st.sidebar:
    st.markdown('## ◈ FlowOps')
    st.caption('MERCHANT OPERATIONS')
    st.markdown('<span class="pill">SIMULATED ENVIRONMENT</span>', unsafe_allow_html=True)
    st.write('')
    page = st.radio('Workspace', ['Overview', 'Create ticket', 'Ticket workspace', 'Evaluation evidence', 'Demo guide'], key='page')
    st.divider()
    st.caption('LOCAL SESSION ONLY')
    st.write(f'{len(st.session_state.tickets)} tickets in this browser session')
    st.caption('No real POS, payments, customer data or enterprise systems. Do not enter personal or payment information.')
    st.caption('Closing the server or clearing browser session state loses tickets. Download the synthetic audit before leaving.')

st.markdown('<div class="eyebrow">Merchant billing / controlled simulation</div>', unsafe_allow_html=True)

if page == 'Overview':
    st.title('Merchant Operations')
    st.markdown('<div class="hero"><h2>From invoice complaint to a checked outcome.</h2><p>Investigate, resolve and verify merchant invoice issues. The agent chooses the next action; trusted tools enforce the business rules.</p></div>', unsafe_allow_html=True)
    a, b, c = st.columns([1.1,1,2])
    a.button('＋ Create New Ticket', type='primary', on_click=go, args=('Create ticket',), use_container_width=True)
    b.button('Open Demo Guide', on_click=go, args=('Demo guide',), use_container_width=True)
    st.write('')
    tickets = st.session_state.tickets
    if not tickets:
        st.markdown('<div class="card"><h3>No billing tickets yet</h3><p class="muted">Start with a synthetic invoice and a complaint. Creating a ticket does not call the model or change its invoice.</p></div>', unsafe_allow_html=True)
    else:
        st.subheader('Your session tickets')
        for tid, ticket in reversed(list(tickets.items())):
            with st.container(border=True):
                left, middle, right = st.columns([3,1.6,1])
                left.text(f'{ticket.title} · {tid}')
                left.text(f'{ticket.merchant} · {ticket.invoice_id} · {ticket.mode}')
                middle.write(f'**{ticket.status}** · {svc.money(ticket.session.bill.stored_total_cents)} SAR')
                right.button('Open ticket', key='open_'+tid, on_click=go, args=('Ticket workspace', tid), use_container_width=True)
    st.subheader('How FlowOps works')
    for col, title, text in zip(st.columns(3), ['01 / Raise an issue', '02 / Let the agent investigate', '03 / Verify the outcome'],
                               ['Choose a synthetic invoice and describe the complaint.', 'A local model selects permitted operations, one step at a time.', 'The independent verifier checks saved state before closure. Locks require a different outcome.']):
        col.markdown(f'<div class="card"><h3>{title}</h3><p class="muted">{text}</p></div>', unsafe_allow_html=True)

elif page == 'Create ticket':
    st.title('Create a billing ticket')
    st.caption('A real native WorkflowSession, built from synthetic data. No model runs until you choose Run Agent or Step Through.')
    left, right = st.columns([1.35,1], gap='large')
    with left:
        scenario = st.selectbox('Synthetic invoice scenario', list(svc.SCENARIOS), format_func=lambda k: svc.SCENARIOS[k]['title'])
        data = svc.SCENARIOS[scenario]
        with st.form('ticket_form_'+scenario):
            issue_category = st.selectbox('Issue category — selected by the operator', list(svc.ISSUE_ROUTES))
            st.caption('Structured routing, not AI intent classification. Refunds, fraud/disputes and account requests cannot enter invoice repair. Unclear requests need clarification. Complaint text is not automatically classified; select the category accurately.')
            merchant = st.selectbox('Synthetic merchant', ['Cedar Table · Synthetic', 'Harbour Kitchen · Synthetic'])
            title = st.text_input('Ticket title', value=data['title'], max_chars=100)
            complaint = st.text_area('Complaint description', value=data['description'], height=115, max_chars=800)
            stored = st.text_input('Currently stored total (SAR)', value=data['total'], help='Exact decimal text, at most two decimal places. Synthetic records only.')
            mode = st.selectbox('Execution source', ['LIVE MODEL', 'RULES BASELINE'], help='Rules is a separate non-AI baseline, never an automatic fallback.')
            model = st.text_input('Local Ollama model tag', value=svc.DEFAULT_MODEL, help='For live Qwen execution. No API key is needed.')
            consent = st.checkbox('This ticket contains synthetic information only.')
            submitted = st.form_submit_button('Create Ticket', type='primary', use_container_width=True)
        if submitted:
            try:
                if not consent:
                    raise ValueError('Confirm that you are using synthetic information only.')
                title = svc.synthetic_text(title, 'Title', 100)
                ticket = svc.create_ticket(scenario, complaint, merchant=merchant, title=title, stored_total=stored, mode=mode, model=model, issue_category=issue_category)
                st.session_state.tickets[ticket.ticket_id] = ticket
                st.session_state.active_ticket = ticket.ticket_id
                st.session_state._next_page = 'Ticket workspace'
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    with right:
        st.markdown('### Invoice preview')
        st.markdown(f'<div class="card"><span class="pill {"warn" if data["locked"] else ""}">{"MERCHANT LOCK ACTIVE" if data["locked"] else "UNLOCKED"}</span><h3>{escape(data["title"])}</h3><p class="muted">Synthetic invoice ID generated on ticket creation.</p></div>', unsafe_allow_html=True)
        st.table([{'Item':name, 'Unit price (SAR)':price, 'Qty':qty, 'Line amount (SAR)':svc.money(svc.exact_scaled(price,100)*qty)} for name,(price,qty) in zip(data['item_names'],data['items'])])
        st.write(f'**VAT:** {svc.Decimal(data["tax"])*100:g}% · **Service:** available')
        if 'split' in data:
            st.write('**Recorded split:** ' + ' + '.join(data['split']) + ' SAR. Only a two-way equal split is supported.')
        if data['locked']:
            st.warning('The lock is part of this scenario. Neither the model nor human approval can remove it.')
        with st.expander('What information reaches the agent?'):
            st.write('The complaint is explicitly appended to CaseSpec.request and becomes the observation objective. It is untrusted context, not a policy override. The model also sees numeric invoice state, lock, checks, permitted tools, pending patch and prior feedback.')
            st.write('Merchant display name, invoice ID and item descriptions are UI metadata; the engine uses item prices and quantities. This is constrained invoice handling, not general complaint understanding or arbitrary file parsing.')

elif page == 'Ticket workspace':
    tid = st.session_state.get('active_ticket')
    if tid not in st.session_state.tickets:
        st.title('Ticket workspace')
        st.info('Create a synthetic ticket to begin an investigation.')
        st.button('Create New Ticket', type='primary', on_click=go, args=('Create ticket',))
        st.stop()
    ticket = st.session_state.tickets[tid]
    session = ticket.session
    st.title('Billing ticket')
    st.text(ticket.title)
    st.text(f'{ticket.ticket_id} / {ticket.invoice_id} / {ticket.merchant}')
    source_header(ticket)
    st.caption('Selected issue category: ' + ticket.issue_category + ' · Structured routing, not AI classification')
    st.text(ticket.complaint)
    cols=st.columns(4)
    cols[0].metric('Ticket status', ticket.status)
    cols[1].metric('Saved total', svc.money(session.bill.stored_total_cents)+' SAR')
    cols[2].metric('Calculated invoice total', svc.money(svc.expected_total(session.bill.snapshot()))+' SAR')
    cols[3].metric('Independent checks', 'PASS' if session.verification.passed else 'FAIL')
    st.caption(f'{"MERCHANT LOCK ACTIVE" if session.bill.locked else "Unlocked"} · Invoice version {session.bill.version} · {session.step_count}/{svc.MAX_STEPS} selected actions · Calculated total is display-only; the native verifier is authoritative.')
    controls, detail = st.columns([1.45,1])
    with controls:
        live_enabled = True
        if ticket.mode == 'LIVE MODEL':
            runtime=get_runtime(ticket.model)
            st.caption(('● ' if runtime['ready'] else '○ ')+runtime['message'])
            live_enabled=st.checkbox('Enable real local Qwen execution for this ticket', key='enable_'+tid, help='Run/Step will make server-side requests to the local Ollama service.')
        one,many=st.columns(2)
        step_clicked=one.button('Step Through', use_container_width=True, disabled=not ticket.can_run or not live_enabled)
        run_clicked=many.button('Run Agent', type='primary', use_container_width=True, disabled=not ticket.can_run or not live_enabled)
        if step_clicked or run_clicked:
            with st.spinner('The agent is selecting and executing permitted actions…'):
                svc.advance(ticket, run_all=run_clicked)
            st.rerun()
    with detail:
        if ticket.status == 'Incomplete':
            st.error(ticket.incomplete_reason)
        elif session.staged_patch:
            st.info('Correction prepared, not applied. Saved invoice is unchanged until deployment.')
        elif ticket.status == 'New':
            st.info('Ready to investigate. Initial verification is read-only; no agent action has run.')
        elif ticket.status == 'Resolved':
            changed=ticket.initial != session.bill.snapshot()
            st.success('Invoice corrected and independently verified.' if changed else 'Invoice independently verified and closed without modification.')
        elif ticket.status == 'Escalated':
            st.warning('Escalated for human review. This is not a completed repair or a real human notification.')

    if ticket.status == 'Awaiting Approval':
        st.warning('The agent requested human approval. This is not a resolved ticket.')
        if session.verification.passed and not session.staged_patch:
            st.caption('Checks pass and no patch is pending. An unnecessary approval can still be an autonomy failure; it is not relabelled as success.')
        with st.expander('Simulated operator approval — optional, not real authentication'):
            confirmed=st.checkbox('I explicitly approve continuing this synthetic ticket.', key='confirm_'+tid)
            if st.button('Record simulated approval', key='approve_'+tid, disabled=not confirmed):
                try:
                    svc.approve(ticket, confirmed)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            st.caption('Calls the native approval mechanism. It cannot unlock invoices, bypass checks or reset the action budget. Any resulting outcome includes human intervention.')
    tabs=st.tabs(['Investigation timeline','Invoice before / after','Resolution & audit'])
    with tabs[0]:
        if not ticket.events:
            st.markdown('<div class="card"><h3>Investigation has not started</h3><p class="muted">Choose Step Through to explain one model-selected action, or Run Agent to continue until an outcome, approval, error or the shared action limit.</p></div>', unsafe_allow_html=True)
        for e in ticket.events:
            reason=escape(e['reason'] or 'No model action was returned.')
            change='Saved invoice changed' if e['changed'] else 'No saved invoice change'
            outcome='Accepted' if e['accepted'] else 'Not accepted'
            st.markdown(f'<div class="timeline"><h4>{e["step"] or "—"} / {escape(e["label"])}</h4><p>{reason}</p><p><b>{outcome}</b> · {change} · {escape(e["ticket_status"])}</p><p>{escape(e["message"])}</p></div>', unsafe_allow_html=True)
        st.caption('Reasons are model-generated explanations, not authoritative policy. Events reflect real native results; initial checks are not fabricated agent actions.')
    with tabs[1]:
        before,after=st.columns(2)
        for col,name,state in [(before,'Original invoice',ticket.initial),(after,'Current saved invoice',session.bill.snapshot())]:
            with col:
                st.markdown(f'<div class="card"><span class="eyebrow">{name}</span><div class="amount">{svc.money(state["stored_total_cents"])} <small>SAR</small></div><p class="muted">Version {state["version"]} · {"Locked" if state["locked"] else "Unlocked"}</p></div>', unsafe_allow_html=True)
                st.table([{'Item':n,'Unit price':svc.money(r['unit_price_cents']),'Qty':r['quantity'],'Amount':svc.money(r['unit_price_cents']*r['quantity'])} for n,r in zip(ticket.item_names,state['line_items'])])
                st.write(f'VAT: {svc.Decimal(state["tax_bps"])/100:g}% · Difference from calculated total: {svc.money(state["stored_total_cents"]-svc.expected_total(state))} SAR')
                if state['split_cents'] is not None:
                    st.write('Split: '+' + '.join(svc.money(p) for p in state['split_cents'])+' SAR')
        st.write('**Persisted total change:** '+svc.money(session.bill.stored_total_cents-ticket.initial['stored_total_cents'])+' SAR')
        st.info('Preparing a correction does not change the invoice. Deployment applies an authorized change. Independent verification confirms the saved result.')
        if session.staged_patch:
            st.write('**Pending proposal (not persisted):** '+', '.join(f'{k.replace("_"," ")}: {svc.money(v) if isinstance(v,int) else " + ".join(svc.money(p) for p in v)} SAR' for k,v in session.staged_patch.items()))
    with tabs[2]:
        st.subheader(ticket.status)
        st.write(f'Native status: **{session.status}** · Selected actions: **{session.step_count}** · Attempts including failed planning: **{ticket.attempts}**')
        for check,passed in session.verification.checks.items():
            st.write(('✓ ' if passed else '✕ ')+check.replace('_',' ').title()+(' — passed' if passed else ' — failed'))
        st.write('Human intervention requested: **'+('Yes' if any(e['action']=='request_approval' for e in ticket.events) else 'No')+'**')
        st.caption('A passing invoice check does not mean the agent completed the workflow. Only native CLOSED_VERIFIED is presented as resolved.')
        with st.expander('Exact information sent at the latest planning turn (or initial preview)'):
            st.json(ticket.last_observation, expanded=False)
            st.caption('Expected grading labels, private case IDs and oracle totals are not supplied. This readout does not call the model.')
        with st.expander('Technical audit trail'):
            st.json(svc.audit_report(ticket), expanded=False)
        st.download_button('Download synthetic ticket audit', data=json.dumps(svc.audit_report(ticket),indent=2), file_name=ticket.ticket_id+'_audit.json', mime='application/json')
    st.button('Create another ticket', on_click=go, args=('Create ticket',))

elif page == 'Evaluation evidence':
    st.title('Evaluation Evidence')
    badge('SAVED REPLAY — NO FRESH INFERENCE')
    st.caption('Selected recorded Qwen executions. Opening or stepping this view never constructs a live session or dispatches business tools.')
    st.write('**h_001:** verified repair · **h_013:** locked escalation · **h_019:** unnecessary approval failure')
    st.info('Post-freeze synthetic result: 16/20. Known diagnostic: 10/12. These are separate sets. The case author knew earlier weaknesses; this is not blinded certification or production performance.')
    components.html(svc.heldout_html(), height=980, scrolling=True)

else:
    st.title('A clear, honest three-minute demo')
    st.markdown('''### 1. Raise an invoice complaint
Open **Create ticket**, keep **Invoice total mismatch**, confirm synthetic data and submit. The ticket is a real native session. Its complaint becomes objective context; no model has run yet.

### 2. Watch the agent work
In **LIVE MODEL**, enable local execution and choose **Step Through**. Explain actual actions as they appear. Staging only prepares a proposal; deployment changes saved state. Continue until the engine closes, requests approval, escalates or fails. Do not promise a successful Qwen outcome in advance.

### 3. Respect the lock
Create **Locked invoice dispute**. The lock is authoritative. A correct escalation leaves the amount and version unchanged; a blocked write is not a repair. If the model fails, show that honestly.

### 4. Preserve the autonomy gap
Create **Already-correct invoice review**. A model approval request is not a resolution. Do not add a manual close or replace the planner to manufacture success.

### 5. Separate historical evidence
Open **Evaluation evidence** for saved h_001, h_013 and h_019. Call them recorded executions. Keep 16/20 held-out separate from 10/12 diagnostic and the 12/12 known-set rules baseline.

**If Ollama is unavailable:** the ticket reports an incomplete attempt without silent rules fallback. A separate **RULES BASELINE** ticket is useful offline, but is not AI evidence.

**What is simulated:** merchant identity, invoices, permissions, approvals and operations. No actual POS connection, payment, customer record or human notification occurs. There are no measured merchant savings or production-reliability claims.

**What to retain:** download the synthetic ticket audit before closing the browser session. Current-session tickets are not a durable shared database.''')
