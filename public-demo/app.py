"""Offline-only redacted diagnostic replay; never imports a model planner."""
import json
from pathlib import Path
import streamlit as st

DATA = Path(__file__).with_name('diagnostic-replay.json')
st.set_page_config(page_title='FlowOps | Safe diagnostic replay', layout='wide')
st.title('FlowOps — Invoice v2')
st.info('Saved synthetic diagnostic replay only. No model calls, tool execution, or invoice mutation. These are known diagnostic examples, not held-out cases.')
records = json.loads(DATA.read_text())['records']
record = st.selectbox('Recorded example', records, format_func=lambda r: r['case_id'])
position = st.slider('Recorded steps shown', 0, len(record['steps']), 0)
frame = record['steps'][position - 1] if position else None
state = frame['state_after'] if frame else record['initial_state']
a, b, c = st.columns(3)
a.metric('Stored total (cents)', state['stored_total_cents'])
b.metric('Version', state['version'])
c.metric('Merchant lock', 'LOCKED' if state['locked'] else 'UNLOCKED')
st.json(state)
if frame:
    st.subheader('Recorded action: ' + frame.get('chosen_action', 'unknown'))
    st.write(frame.get('chosen_reason', ''))
    st.caption('Model rationale is recorded evidence, not policy truth.')
    st.json({k: frame[k] for k in ['pending_patch_after', 'tool_result', 'verification_after', 'status_after'] if k in frame})
if position == len(record['steps']):
    st.write('Recorded terminal status:', record['status'])
    st.write('Expected diagnostic outcome met:', record['expected_outcome_met'])
    if not record['expected_outcome_met']:
        st.warning('Preserved failure: already-correct invoice unnecessarily sent for approval, not autonomous closure.')
st.divider()
st.markdown('**Reported post-freeze supplier-attested held-out:** 16/20; repairs 12/12; locked escalations 4/4; unchanged closures 0/4; four unnecessary approvals. 77 calls; zero tool failures; one rejection; zero invalid closures/runtime stops.')
st.caption('Separate known diagnostic score: 10/12. Single runs, not certification. Held-out records are deliberately absent. Separate ChatGPT case author knew prior weaknesses. No production/POS or productivity claim.')
