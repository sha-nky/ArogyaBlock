import json
import os
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

from flask import Flask, jsonify, make_response, request as flask_request
from openai import OpenAI


app = Flask(__name__)


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


def _json_response(payload, status=200):
    response = make_response(jsonify(payload), status)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    return response


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


def _allow_fallback():
    return os.getenv('ALLOW_AI_FALLBACK', '0').strip().lower() in ('1', 'true', 'yes')


def _provider_name():
    return os.getenv('AI_PROVIDER', 'openai').strip().lower()


def _call_openai_chat(system_prompt, user_prompt, max_tokens=220):
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key:
        return None, 'OPENAI_API_KEY is not configured in app/.env', 'openai'

    model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini').strip()
    base_url = os.getenv('OPENAI_BASE_URL', '').strip() or None

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or '').strip()
        if not text:
            return None, 'OpenAI-compatible provider returned empty response', 'openai'
        return text, None, 'openai'
    except Exception as exc:
        return None, f'OpenAI-compatible request failed: {exc}', 'openai'




def _call_groq_chat(system_prompt, user_prompt, max_tokens=220):
    api_key = os.getenv('GROQ_API_KEY', '').strip()
    if not api_key:
        return None, 'GROQ_API_KEY is not configured in app/.env', 'groq'

    model = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile').strip()
    base_url = os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1').strip()

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or '').strip()
        if not text:
            return None, 'Groq returned empty response', 'groq'
        return text, None, 'groq'
    except Exception as exc:
        return None, f'Groq request failed: {exc}', 'groq'

def _call_anthropic_chat(system_prompt, user_prompt, max_tokens=220):
    api_key = os.getenv('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        return None, 'ANTHROPIC_API_KEY is not configured in app/.env', 'anthropic'

    model = os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20240620').strip()
    payload = {
        'model': model,
        'max_tokens': max_tokens,
        'system': system_prompt,
        'messages': [{'role': 'user', 'content': user_prompt}],
    }

    req = request.Request(
        'https://api.anthropic.com/v1/messages',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        },
        method='POST',
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        content = body.get('content', [])
        text_parts = [item.get('text', '') for item in content if item.get('type') == 'text']
        text = '\n'.join([part.strip() for part in text_parts if part.strip()]).strip()
        if not text:
            return None, 'Anthropic returned empty response', 'anthropic'
        return text, None, 'anthropic'
    except (HTTPError, URLError, json.JSONDecodeError, KeyError) as exc:
        return None, f'Anthropic request failed: {exc}', 'anthropic'




def _call_gemini_chat(system_prompt, user_prompt, max_tokens=220):
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key:
        return None, 'GEMINI_API_KEY is not configured in app/.env', 'gemini'

    model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash').strip()

    try:
        from google import genai
    except Exception as exc:
        return None, f'google-genai package is missing: {exc}', 'gemini'

    prompt = (
        f"System instruction:\n{system_prompt}\n\n"
        f"User request:\n{user_prompt}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={'max_output_tokens': max_tokens, 'temperature': 0.2},
        )
        text = (getattr(response, 'text', None) or '').strip()
        if not text:
            return None, 'Gemini returned empty response', 'gemini'
        return text, None, 'gemini'
    except Exception as exc:
        return None, f'Gemini request failed: {exc}', 'gemini'

def _call_llm(system_prompt, user_prompt, max_tokens=220):
    provider = _provider_name()

    if provider in ('openai', 'openai_compatible'):
        return _call_openai_chat(system_prompt, user_prompt, max_tokens)

    if provider == 'groq':
        return _call_groq_chat(system_prompt, user_prompt, max_tokens)

    if provider in ('anthropic', 'claude'):
        return _call_anthropic_chat(system_prompt, user_prompt, max_tokens)

    if provider in ('gemini', 'google'):
        return _call_gemini_chat(system_prompt, user_prompt, max_tokens)

    return None, f'Unsupported AI_PROVIDER: {provider}', provider


def _response_with_fallback(live_text, error, provider, fallback_text_key, fallback_text):
    if live_text:
        return _json_response({fallback_text_key: live_text, 'source': provider})

    if _allow_fallback():
        return _json_response({fallback_text_key: fallback_text, 'source': 'fallback', 'warning': error, 'provider': provider})

    return _json_response({'error': error, 'source': 'none', 'provider': provider}, 502)


@app.route('/ai/preliminary-diagnosis', methods=['POST', 'OPTIONS'])
def preliminary_diagnosis():
    if flask_request.method == 'OPTIONS':
        return _json_response({}, 204)

    payload = flask_request.get_json(silent=True) or {}
    symptoms = payload.get('symptoms', '')
    intensity = payload.get('intensity', 'unknown')

    system_prompt = (
        'You are a clinical triage assistant. Provide a concise preliminary diagnosis for doctors. '
        'Always mention that this is not final and requires doctor confirmation.'
    )
    user_prompt = f'Symptoms: {symptoms}\nIntensity: {intensity}\nReturn 2-3 sentences.'

    ai_text, error, provider = _call_llm(system_prompt, user_prompt)
    return _response_with_fallback(
        live_text=ai_text,
        error=error,
        provider=provider,
        fallback_text_key='preliminary_diagnosis',
        fallback_text=_fallback_preliminary(symptoms, intensity),
    )


@app.route('/ai/simplify-diagnosis', methods=['POST', 'OPTIONS'])
def simplify_diagnosis():
    if flask_request.method == 'OPTIONS':
        return _json_response({}, 204)

    payload = flask_request.get_json(silent=True) or {}
    diagnosis = payload.get('diagnosis', '')
    comments = payload.get('comments', '')
    symptoms = payload.get('symptoms', '')

    system_prompt = (
        'You simplify doctor diagnosis into patient-friendly language at grade 6-8 reading level. '
        'Avoid jargon and avoid giving treatment that contradicts doctor.'
    )
    user_prompt = (
        f'Doctor diagnosis: {diagnosis}\nDoctor comments: {comments}\n'
        f'Reported symptoms: {symptoms}\nReturn 3 short bullet-like lines in plain text.'
    )

    ai_text, error, provider = _call_llm(system_prompt, user_prompt)
    return _response_with_fallback(
        live_text=ai_text,
        error=error,
        provider=provider,
        fallback_text_key='simplified_diagnosis',
        fallback_text=_fallback_simplified(diagnosis, comments),
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=True)
