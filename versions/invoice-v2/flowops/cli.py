"""CLI smoke test; no Streamlit or Ollama required for rule-based mode."""
import argparse
import json
from pathlib import Path
from .cases import load_cases
from .engine import WorkflowSession
from .planner import RulesPlanner, OllamaPlanner, HostedPlanner


def main():
    p = argparse.ArgumentParser(description='FlowOps simulated workflow starter')
    p.add_argument('--case', default='split_bill', help='Case id to run')
    p.add_argument('--all', action='store_true', help='Run all demo cases')
    p.add_argument('--planner', choices=['rules', 'ollama', 'hosted'], default='rules')
    p.add_argument('--model', default=None, help='Model id; hosted default is FLOWOPS_LLM_MODEL')
    p.add_argument('--base-url', default=None, help='Hosted HTTPS API base (including /v1 if required)')
    p.add_argument('--fallback-rules', action='store_true', help='Explicit non-AI fallback on hosted transport failure; audited')
    p.add_argument('--cases-file', type=Path, default=None)
    p.add_argument('--approve', action='store_true', help='Simulate explicit human approval before running')
    p.add_argument('--output', type=Path, help='Write audit result JSON')
    args = p.parse_args()
    cases = load_cases(args.cases_file) if args.cases_file else load_cases()
    if args.planner == 'hosted':
        planner = HostedPlanner(model=args.model, base_url=args.base_url, fallback=args.fallback_rules)
    elif args.planner == 'ollama':
        planner = OllamaPlanner(model=args.model or 'qwen3:4b')
    else:
        planner = RulesPlanner()
    ids = cases.keys() if args.all else [args.case]
    reports = []
    for cid in ids:
        session = WorkflowSession(cases[cid])
        if args.approve and session.status == 'PAUSED_APPROVAL':
            session.grant_human_approval('simulated-human-operator')
        report = session.run(planner)
        reports.append(report)
        print(f"{cid:24} status={report['status']:18} "
              f"verified={report['verification']['passed']} "
              f"steps={report['steps']} deploys={report['deploy_attempts']}")
        for e in report['audit_trail']:
            print(f"  {e['index']:02d} {e['action']}: {e['message']}")
    if args.output:
        args.output.write_text(json.dumps(reports if args.all else reports[0], indent=2), encoding='utf-8')
        print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()
