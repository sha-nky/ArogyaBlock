import json
import os
import re
import base64
from io import BytesIO
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError
from zipfile import ZipFile

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


def _is_image_upload(filename, content_type):
    suffix = Path(filename or '').suffix.lower()
    image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff'}
    lowered_type = (content_type or '').lower()
    return suffix in image_extensions or lowered_type.startswith('image/')


def _extract_text_from_upload(filename, content_type, raw_bytes):
    suffix = Path(filename or '').suffix.lower()
    lowered_type = (content_type or '').lower()

    if not raw_bytes:
        return ''

    if _is_image_upload(filename, content_type):
        return _extract_text_from_image_with_ai(raw_bytes, lowered_type or 'image/jpeg')

    if suffix == '.pdf' or lowered_type == 'application/pdf':
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(raw_bytes))
            text_parts = []
            for page in reader.pages:
                page_text = (page.extract_text() or '').strip()
                if page_text:
                    text_parts.append(page_text)
            extracted_text = '\n'.join(text_parts).strip()
            if extracted_text:
                return extracted_text

            # Scanned PDFs often contain no embedded text. Try OCR on embedded page images.
            image_payloads = _extract_images_from_pdf_bytes(raw_bytes)
            ocr_parts = []
            for img_bytes, img_type in image_payloads:
                extracted = _extract_text_from_image_with_ai(img_bytes, img_type)
                if extracted:
                    ocr_parts.append(extracted)
            return '\n\n'.join(ocr_parts).strip()
        except Exception as exc:
            raise ValueError(f'Unable to parse PDF: {exc}')

    if suffix == '.docx':
        try:
            with ZipFile(BytesIO(raw_bytes)) as archive:
                document_xml = archive.read('word/document.xml').decode('utf-8', errors='ignore')
            text = re.sub(r'<[^>]+>', ' ', document_xml)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        except Exception as exc:
            raise ValueError(f'Unable to parse DOCX: {exc}')

    for encoding in ('utf-8', 'utf-16', 'latin-1'):
        try:
            return raw_bytes.decode(encoding).strip()
        except UnicodeDecodeError:
            continue

    return raw_bytes.decode('utf-8', errors='ignore').strip()


def _extract_text_from_image_with_ai(raw_bytes, content_type):
    return _call_vision_llm(
        raw_bytes=raw_bytes,
        content_type=content_type,
        system_prompt=(
            'You extract text from medical images (reports, lab slips, prescriptions). '
            'Return plain text only. If uncertain, mark as [unclear].'
        ),
        user_prompt='Extract all readable medical text from this image.',
        max_tokens=700,
        temperature=0.0,
        empty_error='AI returned empty text for image',
    )


def _analyze_medical_scan_with_ai(raw_bytes, content_type):
    return _call_vision_llm(
        raw_bytes=raw_bytes,
        content_type=content_type,
        system_prompt=(
            'You are a medical imaging assistant for clinicians. '
            'Describe visible findings and quality issues only. '
            'Do not provide definitive diagnosis. Keep it concise.'
        ),
        user_prompt='Analyze this scan/report image and provide 4-6 concise findings.',
        max_tokens=500,
        temperature=0.1,
        empty_error='No clear scan findings could be generated.',
        allow_empty=True,
    )


def _get_vision_provider_config():
    provider = _provider_name()
    if provider in ('openai', 'openai_compatible'):
        api_key = os.getenv('OPENAI_API_KEY', '').strip()
        if not api_key:
            raise ValueError('OPENAI_API_KEY is required for image extraction/scan analysis')
        model = os.getenv('OPENAI_VISION_MODEL', os.getenv('OPENAI_MODEL', 'gpt-4o-mini')).strip()
        base_url = os.getenv('OPENAI_BASE_URL', '').strip() or None
        return api_key, base_url, model, 'openai-compatible'

    if provider == 'groq':
        api_key = os.getenv('GROQ_API_KEY', '').strip()
        if not api_key:
            raise ValueError('GROQ_API_KEY is required for image extraction/scan analysis')
        model = os.getenv('GROQ_VISION_MODEL', os.getenv('GROQ_MODEL', 'llama-3.2-90b-vision-preview')).strip()
        base_url = os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1').strip()
        return api_key, base_url, model, 'groq'

    raise ValueError(
        f'Image extraction/scan analysis not configured for AI_PROVIDER={provider}. '
        'Use openai/openai_compatible or groq.'
    )


def _call_vision_llm(raw_bytes, content_type, system_prompt, user_prompt, max_tokens, temperature, empty_error, allow_empty=False):
    api_key, base_url, model, provider_name = _get_vision_provider_config()
    image_b64 = base64.b64encode(raw_bytes).decode('utf-8')
    data_url = f'data:{content_type};base64,{image_b64}'

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    'role': 'system',
                    'content': system_prompt,
                },
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': user_prompt},
                        {'type': 'image_url', 'image_url': {'url': data_url}},
                    ],
                },
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or '').strip()
        if not text:
            if allow_empty:
                return empty_error
            raise ValueError(empty_error)
        return text
    except Exception as exc:
        raise ValueError(f'Vision request failed ({provider_name}): {exc}')


def _extract_images_from_pdf_bytes(raw_bytes, max_pages=4, max_images=6):
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise ValueError(f'pypdf is required for scanned PDF processing: {exc}')

    image_payloads = []
    reader = PdfReader(BytesIO(raw_bytes))
    for page_index, page in enumerate(reader.pages):
        if page_index >= max_pages or len(image_payloads) >= max_images:
            break
        images = getattr(page, 'images', [])
        for image in images:
            if len(image_payloads) >= max_images:
                break
            name = getattr(image, 'name', '') or ''
            suffix = Path(name).suffix.lower()
            content_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.bmp': 'image/bmp',
                '.tif': 'image/tiff',
                '.tiff': 'image/tiff',
            }.get(suffix, 'image/jpeg')
            image_payloads.append((image.data, content_type))
    return image_payloads


def _analyze_pdf_scan_with_ai(raw_bytes):
    images = _extract_images_from_pdf_bytes(raw_bytes, max_pages=3, max_images=1)
    if not images:
        return ''
    first_image_bytes, first_image_type = images[0]
    return _analyze_medical_scan_with_ai(first_image_bytes, first_image_type)


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
    user_prompt = f'Symptoms: {symptoms}\nIntensity: {intensity}\nReturn 5-10 bullet-like lines in plain text that gives a comprehensive and complete summary for the doctor.'

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
        f'Reported symptoms: {symptoms}\nReturn 5-10 short bullet-like lines in plain text in such a manner that it covers the whole report without leaving anything.'
        f'These points should be helpful to the patients to understand what the issue is, what is suggested by the doctor in terms of medicines, precautions, etc. (if any), and what is/are the next step(s)'
    )

    ai_text, error, provider = _call_llm(system_prompt, user_prompt)
    return _response_with_fallback(
        live_text=ai_text,
        error=error,
        provider=provider,
        fallback_text_key='simplified_diagnosis',
        fallback_text=_fallback_simplified(diagnosis, comments),
    )

@app.route('/ai/extract-text', methods=['POST', 'OPTIONS'])
def extract_text():
    if flask_request.method == 'OPTIONS':
        return _json_response({}, 204)

    uploaded = flask_request.files.get('file')
    if not uploaded:
        return _json_response({'error': 'No file was uploaded'}, 400)

    filename = uploaded.filename or ''
    content_type = uploaded.content_type or ''
    suffix = Path(filename).suffix.lower()
    raw_bytes = uploaded.read()
    if not raw_bytes:
        return _json_response({'error': 'Uploaded file is empty'}, 400)

    try:
        extracted_text = _extract_text_from_upload(filename, content_type, raw_bytes)
        scan_analysis = ''
        if _is_image_upload(filename, content_type):
            scan_analysis = _analyze_medical_scan_with_ai(raw_bytes, content_type or 'image/jpeg')
        elif suffix == '.pdf' or (content_type or '').lower() == 'application/pdf':
            scan_analysis = _analyze_pdf_scan_with_ai(raw_bytes)
    except ValueError as exc:
        return _json_response({'error': str(exc)}, 400)
    except Exception as exc:
        return _json_response({'error': f'Could not extract file text: {exc}'}, 500)

    return _json_response({
        'file_name': filename,
        'extracted_text': extracted_text,
        'scan_analysis': scan_analysis,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=True)
