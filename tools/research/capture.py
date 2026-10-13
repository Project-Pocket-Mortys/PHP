"""mitmproxy addon for sanitized JSON HTTP exchanges (SSE streaming is excluded).

Usage: mitmdump -s tools/research/capture.py --set pocket_capture=.research/captures/http.jsonl
Configure the separate test client to trust the proxy; never use a real purchase account.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

SECRET_KEYS = {'session_id', 'secret', 'token', 'authorization', 'cookie', 'set-cookie',
               'password', 'email', 'consent_identifier', 'receipt', 'recovery_code', 'username',
               'device_id', 'advertising_id', 'idfa', 'idfv', 'access_token', 'refresh_token',
               'session_url', 'recovery_code_hash'}

def sanitize(value):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if key.lower() in SECRET_KEYS else sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value

def safe_url(url):
    parts = urlsplit(url)
    query = urlencode([(k, '[REDACTED]' if k.lower() in SECRET_KEYS else v) for k,v in parse_qsl(parts.query)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ''))

def body(message):
    try:
        return sanitize(json.loads(message.get_text()))
    except (ValueError, UnicodeError):
        return {'omitted': 'non-JSON or malformed content', 'size': len(message.raw_content or b'')}

class Capture:
    def load(self, loader):
        loader.add_option('pocket_capture', str, '.research/captures/http.jsonl', 'Sanitized test-client capture output')

    def responseheaders(self, flow):
        if 'text/event-stream' in flow.response.headers.get('content-type', ''):
            flow.response.stream = True

    def response(self, flow):
        from mitmproxy import ctx
        if 'text/event-stream' in flow.response.headers.get('content-type', ''):
            return
        record = {'evidence_kind': 'replacement-server runtime; not original-server evidence',
            'method': flow.request.method, 'url': safe_url(flow.request.pretty_url),
            'request': body(flow.request), 'status': flow.response.status_code,
            'response': body(flow.response)}
        target = Path(ctx.options.pocket_capture)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record) + '\n')

addons = [Capture()]
