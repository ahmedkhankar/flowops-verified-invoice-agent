"""Rules baseline, optional Ollama and configurable hosted LLM planning.

Rules are never presented as AI results. A hosted transport fallback must be
explicitly enabled and is attributed per decision, never to the requested model.
"""
import json
import os
from urllib import request, error
from urllib.parse import urlparse
from .models import Decision
from .engine import ALLOWED_AGENT_ACTIONS
from .tools import MODEL_INSTRUCTIONS


class RulesPlanner:
    name = 'Rules baseline (not AI)'

    def decide(self, observation: dict) -> Decision:
        verification = observation['verification']
        issues = set(verification['issues'])
        if observation['world'].get('locked') and not verification['passed']:
            return Decision('escalate', 'Merchant system lock prevents the required correction')
        if observation['deploy_attempts'] >= 2 and not verification['passed']:
            return Decision('escalate', 'Repeated repair attempts have not satisfied acceptance checks')
        if 'service_ready' in issues:
            return Decision('escalate', 'No approved outage recovery tool is available')
        if observation['pending_patch_fields']:
            return Decision('deploy', 'Apply staged correction through trusted deployment service')
        if verification['passed']:
            return Decision('close', 'Current persisted state passes independent verification')
        if 'invoice_total' in issues:
            return Decision('stage_invoice_fix', 'Invoice total does not match item values plus tax')
        if issues.intersection({'split_sum', 'split_balance', 'nonnegative_parts'}):
            return Decision('stage_split_fix', 'Current split amounts violate acceptance checks')
        return Decision('escalate', 'No safe correction for this failure')


class OllamaPlanner:
    """JSON-only tool selection via local Ollama /api/chat.

    A failed model request is an error rather than a silent fallback. This
    prevents misleading benchmarks that count rules decisions as LLM outputs.
    """
    name = 'Ollama local LLM'

    def __init__(self, model='qwen3:4b', url='http://127.0.0.1:11434', timeout=60):
        self.model, self.url, self.timeout = model, url.rstrip('/'), timeout
        self.last_source = 'ollama:' + model
        self.provider_reported_model = None

    def decide(self, observation: dict) -> Decision:
        self.provider_reported_model = None
        prompt = '/no_think\n' + MODEL_INSTRUCTIONS
        body = {
            'model': self.model, 'stream': False, 'think': False,
            'format': 'json', 'options': {'temperature': 0},
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': json.dumps(observation, ensure_ascii=False)},
            ],
        }
        req = request.Request(
            f'{self.url}/api/chat',
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST',
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                result = json.load(response)
            raw = result['message']['content'].strip()
            candidate = json.loads(raw)
            if not isinstance(candidate, dict):
                raise ValueError('Expected a JSON object')
            action = candidate.get('action')
            if not isinstance(action, str) or action not in ALLOWED_AGENT_ACTIONS:
                raise ValueError(f'Unauthorized or unknown model action: {action!r}')
            # Reject *all* unexpected keys and nested tool arguments, including team/actor.
            if not set(candidate) <= {'action', 'reason'}:
                raise ValueError(f'Model attempted unsupported fields: {set(candidate) - {"action", "reason"}}')
            reason = candidate.get('reason', '')
            if not isinstance(reason, str):
                raise ValueError('Reason must be a string')
            reported = result.get('model')
            self.provider_reported_model = reported[:200] if isinstance(reported, str) else None
            return Decision(action, reason[:400])
        except (error.URLError, TimeoutError) as exc:
            raise RuntimeError(f'Ollama unavailable at {self.url}: {exc}') from exc
        except (KeyError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f'Model output rejected; no tool executed: {exc}') from exc


class HostedPlanner:
    """OpenAI-compatible chat completions. No SDK, Ollama or network needed for tests.

    Only synthetic observations are sent. The caller explicitly chooses endpoint,
    model and whether transport failures may use the non-AI rules baseline.
    """
    name = 'Hosted LLM'

    def __init__(self, model=None, base_url=None, api_key=None, timeout=60, fallback=False):
        self.model = model or os.getenv('FLOWOPS_LLM_MODEL', '')
        self.base_url = (base_url or os.getenv('FLOWOPS_LLM_BASE_URL', 'https://api.openai.com/v1')).rstrip('/')
        self.api_key = api_key if api_key is not None else os.getenv('FLOWOPS_LLM_API_KEY', '')
        if not self.model.strip():
            raise ValueError('A hosted model is required: set FLOWOPS_LLM_MODEL or --model')
        parsed = urlparse(self.base_url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Hosted base URL must be HTTPS without credentials, query or fragment')
        self.timeout = timeout
        self.fallback = fallback
        self.last_source = None
        self.fallback_reason = None
        self.provider_reported_model = None

    def decide(self, observation: dict) -> Decision:
        self.last_source = None
        self.fallback_reason = None
        self.provider_reported_model = None
        prompt = MODEL_INSTRUCTIONS
        payload = {'model': self.model, 'temperature': 0,
                   'response_format': {'type': 'json_object'},
                   'messages': [{'role': 'system', 'content': prompt},
                                {'role': 'user', 'content': json.dumps(observation)}]}
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        req = request.Request(self.base_url + '/chat/completions',
                              data=json.dumps(payload).encode(), headers=headers, method='POST')
        try:
            # The transport rejects redirects to avoid forwarding bearer credentials.
            with _hosted_urlopen(req, timeout=self.timeout) as response:
                result = json.load(response)
        except (error.URLError, TimeoutError, OSError) as exc:
            # Never include response bodies, credentials or provider URLs in reports.
            detail = f'Hosted API unavailable ({type(exc).__name__})'
            if not self.fallback:
                raise RuntimeError(detail) from exc
            self.last_source = 'rules_fallback (not AI)'
            self.fallback_reason = detail
            return RulesPlanner().decide(observation)
        except (ValueError, TypeError) as exc:
            raise RuntimeError('Model output rejected; invalid response JSON') from exc
        try:
            raw = result['choices'][0]['message']['content']
            candidate = json.loads(raw)
            if not isinstance(candidate, dict):
                raise ValueError('Expected a JSON object')
            if not set(candidate) <= {'action', 'reason'}:
                raise ValueError('Unsupported fields')
            action = candidate.get('action')
            if not isinstance(action, str) or action not in ALLOWED_AGENT_ACTIONS:
                raise ValueError('Unauthorized or unknown action')
            reason = candidate.get('reason', '')
            if not isinstance(reason, str):
                raise ValueError('Reason must be a string')
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise RuntimeError('Model output rejected; no tool executed') from exc
        reported_model = result.get('model')
        self.provider_reported_model = reported_model[:200] if isinstance(reported_model, str) else None
        self.last_source = 'hosted_api'  # source, not a claim of independently verified model identity
        return Decision(action, reason[:400])


def _hosted_urlopen(req, timeout):
    """Separate transport seam for deterministic offline tests; no global opener."""
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return request.build_opener(NoRedirect()).open(req, timeout=timeout)
