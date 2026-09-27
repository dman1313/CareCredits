"""Scraper liveness/readiness without paid provider calls."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading


def ready():
    missing = [name for name in ('SCRAPER_SERVICE_TOKEN', 'BACKEND_INTERNAL_URL') if not (os.getenv(name) or '').strip()]
    return {
        'status': 'ready' if not missing else 'not_ready',
        'missing': missing,
        'tavily_configured': bool((os.getenv('TAVILY_API_KEY') or '').strip()),
        'model_configured': bool((os.getenv('MODEL_API_KEY') or '').strip() and (os.getenv('MODEL_ID') or '').strip()),
    }


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip('/') == '/health/live':
            self._send(200, {'status': 'live'})
            return
        if self.path.rstrip('/') == '/health/ready':
            payload = ready()
            self._send(200 if payload['status'] == 'ready' else 503, payload)
            return
        self._send(404, {'status': 'not_found'})


def start(port=None):
    port = int(port or os.getenv('SCRAPER_HEALTH_PORT') or 8002)
    server = ThreadingHTTPServer(('127.0.0.1', port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
