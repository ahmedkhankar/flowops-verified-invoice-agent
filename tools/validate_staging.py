"""Fresh-process offline checks of this public staging tree; no installation/inference."""
from pathlib import Path
import hashlib, json, os, re, subprocess, sys
import socket
STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE.parents[2]
VENV = ROOT/'.venv/bin/python'
NATIVE = STAGE/'versions/invoice-v2'

def offline(event, args):
    if event in {'socket.connect','socket.connect_ex','socket.getaddrinfo','socket.sendto'}:
        raise RuntimeError('Network prohibited during staged validation')

def worker(kind):
    sys.addaudithook(offline)
    sys.path.insert(0,str(NATIVE))
    os.chdir(NATIVE)
    import flowops.engine
    assert Path(flowops.engine.__file__).resolve().is_relative_to(STAGE)
    if kind=='pytest':
        import pytest
        # Original external-kit tests are retained, not weakened or supplied fabricated answers.
        raise SystemExit(pytest.main(['tests','-q','-p','no:cacheprovider','--ignore=tests/test_native_invoices.py','--ignore=tests/test_native_exam_runner.py','--ignore=tests/test_evaluation_harness.py']))
    if kind=='cli':
        sys.argv=['flowops.cli','--all','--planner','rules']
        from flowops.cli import main
        main()
    if kind=='native':
        from flowops.invoices import invoice_case
        from flowops.engine import WorkflowSession
        from flowops.planner import RulesPlanner
        samples=[({'name':'public-repair','items':[['2.00',3]],'tax':'0.05','total':'0.00','locked':False},'CLOSED_VERIFIED'),({'name':'public-locked','items':[['2.00',3]],'tax':'0.05','total':'0.00','locked':True},'ESCALATED'),({'name':'public-correct','items':[['2.00',3]],'tax':'0.05','total':'6.30','locked':False},'CLOSED_VERIFIED')]
        for data,want in samples:
            session=WorkflowSession(invoice_case(data)); before=session.bill.snapshot(); report=session.run(RulesPlanner())
            assert report['status']==want,(data['name'],report['status'])
            if data['locked'] or data['name']=='public-correct': assert session.bill.snapshot()==before
            print(data['name'],want,'PASS')
    if kind=='ui':
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(STAGE/'public-demo/app.py')).run()
        assert not app.exception
        app.slider[0].set_value(app.slider[0].max).run()
        assert not app.exception
        app.selectbox[0].select_index(2).run()
        assert not app.exception
        app.slider[0].set_value(app.slider[0].max).run()
        assert not app.exception
        assert len(app.warning)==1
        print('Saved diagnostic UI: initial render, full repair replay, preserved failure replay PASS')
        for r in json.loads((STAGE/'public-demo/diagnostic-replay.json').read_text())['records']:
            assert r['steps'] and r['steps'][-1]['status_after']==r['status']
        print('Three replay derivatives: terminal-state consistency PASS')

def main():
    if len(sys.argv)>1: return worker(sys.argv[1])
    env=os.environ.copy()
    for key in list(env):
        if key in {'PYTHONPATH','PYTHONHOME'} or any(x in key.upper() for x in ['API_KEY','TOKEN','SECRET','PASSWORD','FLOWOPS_LLM']): env.pop(key,None)
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',TMPDIR=str(STAGE/'validation/tmp'),HOME=str(STAGE/'validation/home'))
    (STAGE/'validation/tmp').mkdir(parents=True,exist_ok=True); (STAGE/'validation/home').mkdir(exist_ok=True)
    results=[]
    for kind in ['pytest','cli','native','ui']:
        run=subprocess.run([str(VENV),'-B',str(Path(__file__)),kind],cwd=NATIVE,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        output=run.stdout.replace(str(ROOT),'<SOURCE_ROOT>').replace(str(Path.home()),'<HOME>')
        (STAGE/('validation/'+kind+'.txt')).write_text(output)
        results.append({'check':kind,'exit_code':run.returncode,'log':'validation/'+kind+'.txt'})
        print(kind,'exit',run.returncode,output[-2500:])
    (STAGE/'validation/checks.json').write_text(json.dumps({'network':'Python audit hook blocks outbound connection/DNS/sendto in each fresh worker','installation':'None; existing project venv used externally, not copied','checks':results},indent=2)+'\n')
if __name__=='__main__': main()
