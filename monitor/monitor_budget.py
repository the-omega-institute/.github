"""Trusted, conservative reservations for scheduled monitor model work.

Reservations are spent before dispatch, including failures and uncertain HTTP
outcomes. They are never refunded or reset by a model response.
"""
from contextlib import contextmanager
import datetime as dt
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import urllib.error
import urllib.request

SCHEMA = 'display-monitor-budget.v1'
DAILY_RUNS = 2
INCIDENT_DAYS = 7
MAX_REQUESTS = 12
MAX_REQUEST_BYTES = 128 * 1024
MAX_INPUT_BYTES = 512 * 1024
MAX_OUTPUT_TOKENS = 4096
UPSTREAM = 'https://api.nyxid.ai/api/v1/proxy/s/chrono-llm/responses'


def reserve(observation, previous, run_id, attempt, requested=False, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    result = {'schema': SCHEMA, 'reservations': []}
    allowed, reason = False, 'healthy probes require no model'
    if previous is not None:
        if previous.get('schema') != SCHEMA or not isinstance(previous.get('reservations'), list):
            raise ValueError('Model reservation history is invalid')
        for row in previous['reservations']:
            stamp = dt.datetime.fromisoformat(row['at'])
            if stamp.tzinfo is None or stamp > now + dt.timedelta(minutes=5):
                raise ValueError('Invalid model reservation timestamp')
            if stamp >= now - dt.timedelta(days=31):
                result['reservations'].append(dict(row))
    if len(result['reservations']) > 64:
        raise ValueError('Model reservation history exceeds its bounded inventory')
    if requested:
        fingerprint = observation['fingerprint'] if observation['state'] == 'anomaly' else 'manual-acceptance'
        today = [r for r in result['reservations'] if r['at'][:10] == now.date().isoformat()]
        repeated = [r for r in result['reservations'] if r['incident'] == fingerprint
                    and dt.datetime.fromisoformat(r['at']) >= now - dt.timedelta(days=INCIDENT_DAYS)]
        if str(attempt) != '1':
            reason = 'reruns cannot repeat paid model work'
        elif previous is None:
            reason = 'model history unavailable; wait for a healthy scheduled probe to seed it'
        elif repeated:
            reason = 'this incident already reserved model work in the last seven days'
        elif len(today) >= DAILY_RUNS:
            reason = 'two model sessions already reserved today'
        else:
            result['reservations'].append({'run_id': str(run_id), 'attempt': str(attempt),
                'incident': fingerprint, 'at': now.isoformat()})
            allowed, reason = True, 'bounded model session reserved before dispatch'
    return {**observation, 'model_budget': result, 'model_allowed': allowed, 'model_budget_reason': reason,
            'reservation_run_id': str(run_id), 'reservation_attempt': str(attempt)}


def validate_reservation(observation, run_id, attempt):
    if not (observation.get('model_allowed') is True and str(attempt) == '1'
            and observation.get('reservation_run_id') == str(run_id)
            and observation.get('reservation_attempt') == str(attempt)):
        raise ValueError('No model reservation for this exact original run attempt')


class RequestBudget:
    """All Codex turns, review and acceptance share one file outside the sandbox."""
    def __init__(self, path):
        self.path = Path(path)

    def reserve(self, raw, model):
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError('Model request context exceeds 128 KiB')
        value = json.loads(raw)
        if value.get('model') != model or value.get('previous_response_id') or value.get('conversation'):
            raise ValueError('Only the fixed model and explicit bounded input are permitted')
        if any(t.get('type') not in ('function', 'custom', 'namespace') for t in value.get('tools', [])):
            raise ValueError('Hosted billable tools are outside monitor scope')
        value['max_output_tokens'] = MAX_OUTPUT_TOKENS
        value['store'] = False
        body = json.dumps(value).encode()
        with self.path.open('a+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            saved = stream.read()
            state = json.loads(saved) if saved else {'requests': 0, 'input_bytes': 0}
            if state['requests'] >= MAX_REQUESTS or state['input_bytes'] + len(body) > MAX_INPUT_BYTES:
                raise ValueError('Model session request/context budget exhausted')
            state['requests'] += 1
            state['input_bytes'] += len(body)
            stream.seek(0)
            stream.truncate()
            json.dump(state, stream)
            stream.flush()
        return body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Model gateway redirects are forbidden')


@contextmanager
def gateway(budget, key, model, opener=None):
    """Expose a bounded loopback route; the real key never reaches Codex/tools."""
    local_token = secrets.token_urlsafe(32)
    opener = opener or urllib.request.build_opener(NoRedirect()).open

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            try:
                if self.path != '/responses' or self.headers.get('Authorization') != 'Bearer ' + local_token:
                    raise ValueError('Unregistered model route')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_REQUEST_BYTES or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Unbounded model request')
                body = budget.reserve(self.rfile.read(length), model)
                request = urllib.request.Request(UPSTREAM, data=body, headers={
                    'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                    'Accept': 'text/event-stream,application/json', 'User-Agent': 'omega-display-monitor-budget'})
                # No transport retries: a lost response still consumes its reservation.
                response = opener(request, timeout=90)
            except (ValueError, OSError, KeyError, TypeError):
                self.send_error(403, 'Model request denied or unavailable; no automatic retry')
                return
            with response:
                self.send_response(200)
                self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                self.end_headers()
                try:
                    reader = getattr(response, 'read1', response.read)
                    while data := reader(16384):
                        self.wfile.write(data)
                        self.wfile.flush()
                except (OSError, TimeoutError):
                    pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), local_token
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
