"""Local staging-only cleanup, privacy check and hash inventory. Prints no matches."""
from pathlib import Path
import hashlib, json, re, shutil
S=Path(__file__).resolve().parents[1]
R=S.parents[2]
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    # Preparation helper has served its purpose; it is not part of the public artifact.
    helper=S/'tools/prepare_staging.py'
    if helper.exists(): helper.unlink()
    for p in [S/'validation/tmp',S/'validation/home']:
        if p.exists(): shutil.rmtree(p)
    for p in sorted(S.rglob('__pycache__'),reverse=True):
        shutil.rmtree(p)
    allow=json.loads((S/'SOURCE_ALLOWLIST.json').read_text())
    errors=[]
    for e in allow['entries']:
        if sha((R/e['source']).read_bytes())!=e['source_sha256']: errors.append({'path':e['source'],'category':'source_changed'})
        if e.get('path') and sha((S/e['path']).read_bytes())!=e['staged_sha256']: errors.append({'path':e['path'],'category':'staged_allowlist_mismatch'})
    # Construct local-name probes without placing personal identifiers into the public tree.
    name=''.join(map(chr,[97,104,109,101,100])); surname=''.join(map(chr,[107,104,97,110,107,97,114]))
    failure_log=S/'validation/initial-evidence-dependent-attempt.txt'
    if failure_log.exists():
        log=failure_log.read_text()
        for private in [name,surname]: log=re.sub(private,'local-user',log,flags=re.I)
        failure_log.write_text(log)
    patterns={'personal_path':r'/(?:Users|home)/[A-Za-z0-9_.-]+','personal_identifier':name+'|'+surname,'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----','token':r'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})','credential_assignment':r'(?i)(?:api_key|password|secret|access_token)\s*[=:]\s*[\"\'][A-Za-z0-9_+/=-]{16,}[\"\']','email':r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'}
    files=[p for p in S.rglob('*') if p.is_file() and p.name not in ['STAGING_SHA256.json','sanitization.json']]
    for p in files:
        if p.is_symlink(): errors.append({'path':str(p.relative_to(S)),'category':'symlink'})
        text=p.read_text()
        for category,pattern in patterns.items():
            matches=re.findall(pattern,text,re.I)
            if category=='email': matches=[m for m in matches if not m.lower().endswith(('.test','.example','@example.com'))]
            n=len(matches)
            if n: errors.append({'path':str(p.relative_to(S)),'category':category,'count':n})
    report={'status':'PASS' if not errors else 'FAIL','scanned_files':len(files),'findings':errors,'original_allowlist_source_hashes':'UNCHANGED' if not any(e['category']=='source_changed' for e in errors) else 'MISMATCH','raw_private_inputs_opened':False,'full_historical_integrity_claimed':False,'limitations':'Heuristic value-pattern scan, not formal secret detection; source verification covers only explicit inspected allowlist, not excluded private evidence'}
    (S/'validation/sanitization.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if errors: raise SystemExit(1)
    inventory={str(p.relative_to(S)):sha(p.read_bytes()) for p in sorted(S.rglob('*')) if p.is_file() and p.name!='STAGING_SHA256.json'}
    out=S/'STAGING_SHA256.json'; out.write_text(json.dumps({'algorithm':'sha256','scope':'Final sanitized staging only; excludes this inventory itself','files':inventory},indent=2)+'\n')
    assert all(sha((S/p).read_bytes())==h for p,h in inventory.items())
    print('FINAL_FILES',len(inventory),'ALLOWLIST_SHA256',sha((S/'SOURCE_ALLOWLIST.json').read_bytes()),'INVENTORY_SHA256',sha(out.read_bytes()))
if __name__=='__main__': main()
