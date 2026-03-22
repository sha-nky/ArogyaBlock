import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request


def _load_env_file():
    env_path = Path(__file__).with_name('.env')
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file()


def _allow_fallback():
    return os.getenv('ALLOW_AI_FALLBACK', '0').strip().lower() in ('1', 'true', 'yes')


def _provider_name():
    return os.getenv('AI_PROVIDER', 'openai').strip().lower()


def _fallback_preliminary(symptoms, intensity):
    return (
        f'Possible condition pattern based on symptoms ({symptoms}) with {intensity} intensity. '
        'This is not a final diagnosis. Doctor should verify with examination, history, and tests.'
    )


def _fallback_simplified(diagnosis, comments):
    return (
        f'Your doctor suspects: {diagnosis}. {comments}. '
        'In simple terms: this matches your reported symptoms, but your doctor will confirm it '
        'using examination and tests.'
    )


def _post_json(url, payload, headers=None, timeout=30):
    req = request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', **(headers or {})},
        method='POST',
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def _call_openai_compatible(system_prompt, user_prompt, api_key, model, base_url, provider_label):
    if not api_key:
        return None, f'{provider_label.upper()} API key is not configured in app/.env', provider_label

    url = base_url.rstrip('/') + '/chat/completions'
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.2,
        'max_tokens': 220,
    }

    try:
        body = _post_json(url, payload, {'Authorization': f'Bearer {api_key}'})
        text = (((body.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip()
        if not text:
            return None, f'{provider_label} returned empty response', provider_label
        return text, None, provider_label
    except (error.HTTPError, error.URLError, json.JSONDecodeError, KeyError, IndexError) as exc:
        return None, f'{provider_label} request failed: {exc}', provider_label


def _call_openai_chat(system_prompt, user_prompt):
    return _call_openai_compatible(
        system_prompt,
        user_prompt,
        api_key=os.getenv('OPENAI_API_KEY', '').strip(),
        model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini').strip(),
        base_url=os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').strip(),
        provider_label='openai',
    )


def _call_groq_chat(system_prompt, user_prompt):
    return _call_openai_compatible(
        system_prompt,
        user_prompt,
        api_key=os.getenv('GROQ_API_KEY', '').strip(),
        model=os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile').strip(),
        base_url=os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1').strip(),
        provider_label='groq',
    )


def _call_anthropic_chat(system_prompt, user_prompt):
    api_key = os.getenv('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        return None, 'ANTHROPIC_API_KEY is not configured in app/.env', 'anthropic'

    payload = {
        'model': os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20240620').strip(),
        'max_tokens': 220,
        'system': system_prompt,
        'messages': [{'role': 'user', 'content': user_prompt}],
    }

    try:
        body = _post_json(
            'https://api.anthropic.com/v1/messages',
            payload,
            {
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
        )
        content = body.get('content', [])
        text_parts = [item.get('text', '') for item in content if item.get('type') == 'text']
        text = '\n'.join([part.strip() for part in text_parts if part.strip()]).strip()
        if not text:
            return None, 'Anthropic returned empty response', 'anthropic'
        return text, None, 'anthropic'
    except (error.HTTPError, error.URLError, json.JSONDecodeError, KeyError) as exc:
        return None, f'Anthropic request failed: {exc}', 'anthropic'


def _call_gemini_chat(system_prompt, user_prompt):
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key:
        return None, 'GEMINI_API_KEY is not configured in app/.env', 'gemini'

    model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash').strip()
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}'
    payload = {
        'contents': [
            {
                'parts': [
                    {
                        'text': (
                            f'System instruction:\n{system_prompt}\n\n'
                            f'User request:\n{user_prompt}'
                        )
                    }
                ]
            }
        ],
        'generationConfig': {
            'temperature': 0.2,
            'maxOutputTokens': 220,
        },
    }

    try:
        body = _post_json(url, payload)
        candidates = body.get('candidates') or []
        parts = (((candidates[0].get('content') or {}).get('parts')) or []) if candidates else []
        text = '\n'.join([(part.get('text') or '').strip() for part in parts if (part.get('text') or '').strip()]).strip()
        if not text:
            return None, 'Gemini returned empty response', 'gemini'
        return text, None, 'gemini'
    except (error.HTTPError, error.URLError, json.JSONDecodeError, KeyError, IndexError) as exc:
        return None, f'Gemini request failed: {exc}', 'gemini'


def _call_llm(system_prompt, user_prompt):
    provider = _provider_name()
    if provider in ('openai', 'openai_compatible'):
        return _call_openai_chat(system_prompt, user_prompt)
    if provider == 'groq':
        return _call_groq_chat(system_prompt, user_prompt)
    if provider in ('anthropic', 'claude'):
        return _call_anthropic_chat(system_prompt, user_prompt)
    if provider in ('gemini', 'google'):
        return _call_gemini_chat(system_prompt, user_prompt)
    return None, f'Unsupported AI_PROVIDER: {provider}', provider


def _response_with_fallback(live_text, error_message, provider, payload_key, fallback_text):
    if live_text:
        return 200, {payload_key: live_text, 'source': provider}
    if _allow_fallback():
        return 200, {payload_key: fallback_text, 'source': 'fallback', 'warning': error_message, 'provider': provider}
    return 502, {'error': error_message, 'source': 'none', 'provider': provider}


class AiGatewayHandler(BaseHTTPRequestHandler):
    def _write_json(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        content_length = int(self.headers.get('Content-Length', '0'))
        raw_body = self.rfile.read(content_length) if content_length else b'{}'
        return json.loads(raw_body.decode('utf-8') or '{}')

    def do_OPTIONS(self):
        self._write_json(204, {})

    def do_GET(self):
        if self.path != '/health':
            self._write_json(404, {'error': 'Not found'})
            return

        self._write_json(
            200,
            {
                'status': 'ok',
                'provider': _provider_name(),
                'fallback_enabled': _allow_fallback(),
            },
        )

    def do_POST(self):
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._write_json(400, {'error': 'Invalid JSON body'})
            return

        if self.path == '/ai/preliminary-diagnosis':
            symptoms = str(payload.get('symptoms', '')).strip()
            intensity = str(payload.get('intensity', 'unknown')).strip() or 'unknown'
            if not symptoms:
                self._write_json(400, {'error': 'symptoms is required', 'provider': _provider_name()})
                return

            system_prompt = (
                'You are a clinical triage assistant. Provide a concise preliminary diagnosis for doctors. '
                'Always mention that this is not final and requires doctor confirmation.'
            )
            user_prompt = f'Symptoms: {symptoms}\nIntensity: {intensity}\nReturn 2-3 sentences.'
            ai_text, error_message, provider = _call_llm(system_prompt, user_prompt)
            status, response = _response_with_fallback(
                ai_text,
                error_message,
                provider,
                'preliminary_diagnosis',
                _fallback_preliminary(symptoms, intensity),
            )
            self._write_json(status, response)
            return

        if self.path == '/ai/simplify-diagnosis':
            diagnosis = str(payload.get('diagnosis', '')).strip()
            comments = str(payload.get('comments', '')).strip()
            symptoms = str(payload.get('symptoms', '')).strip()
            if not diagnosis:
                self._write_json(400, {'error': 'diagnosis is required', 'provider': _provider_name()})
                return

            system_prompt = (
                'You simplify doctor diagnosis into patient-friendly language at grade 6-8 reading level. '
                'Avoid jargon and avoid giving treatment that contradicts doctor.'
            )
            user_prompt = (
                f'Doctor diagnosis: {diagnosis}\nDoctor comments: {comments}\n'
                f'Reported symptoms: {symptoms}\nReturn 3 short bullet-like lines in plain text.'
            )
            ai_text, error_message, provider = _call_llm(system_prompt, user_prompt)
            status, response = _response_with_fallback(
                ai_text,
                error_message,
                provider,
                'simplified_diagnosis',
                _fallback_simplified(diagnosis, comments),
            )
            self._write_json(status, response)
            return

        self._write_json(404, {'error': 'Not found'})

    def log_message(self, format, *args):
        return


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    server = ThreadingHTTPServer(('0.0.0.0', port), AiGatewayHandler)
    print(f'AI gateway listening on http://127.0.0.1:{port}')
    server.serve_forever()
