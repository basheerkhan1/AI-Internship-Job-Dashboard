#!/usr/bin/env python3
"""
scan_server.py — Local dashboard server with one-click scan trigger
Usage: python3 scan_server.py
Then open: http://localhost:5050
"""

import json
import os
import sys
import io
import threading
from contextlib import redirect_stdout
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent

scan_state = {
    'running': False,
    'last_scan': None,
    'last_count': 0,
    'log': [],
    'error': None,
}

# ── Scanner thread ─────────────────────────────────────────────────────────────

def _run_scan():
    global scan_state
    scan_state['running'] = True
    scan_state['log'] = ['[scan] Starting MN & Remote internship scanner...']
    scan_state['error'] = None

    buf = io.StringIO()

    try:
        # Capture stdout from scan_jobs
        old_stdout = sys.stdout
        sys.stdout = tee = _Tee(old_stdout, buf, scan_state['log'])

        # Import (or reload) scan_jobs
        if 'scan_jobs' in sys.modules:
            import importlib
            mod = importlib.reload(sys.modules['scan_jobs'])
        else:
            sys.path.insert(0, str(ROOT))
            import scan_jobs as mod

        sys.stdout = old_stdout

        jobs = mod.scan()
        scan_state['last_count'] = len(jobs)
        scan_state['last_scan']  = datetime.now(timezone.utc).isoformat()
        scan_state['log'].append(f'[scan] ✓ Complete — {len(jobs)} internships found.')

    except Exception as e:
        sys.stdout = sys.__stdout__
        scan_state['error'] = str(e)
        scan_state['log'].append(f'[scan] ✗ Error: {e}')
    finally:
        scan_state['running'] = False


class _Tee:
    """Write to both real stdout and append to log list."""
    def __init__(self, original, buf, log_list):
        self.original = original
        self.buf = buf
        self.log_list = log_list

    def write(self, data):
        self.original.write(data)
        self.original.flush()
        lines = data.rstrip('\n').split('\n')
        for line in lines:
            if line:
                self.log_list.append(line)

    def flush(self):
        self.original.flush()


# ── HTTP Handler ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/' or path == '/index.html':
            self._serve_file(ROOT / 'index.html', 'text/html; charset=utf-8')
        elif path == '/jobs.json':
            self._serve_file(ROOT / 'jobs.json', 'application/json')
        elif path == '/api/status':
            self._json({
                'running':    scan_state['running'],
                'last_scan':  scan_state['last_scan'],
                'last_count': scan_state['last_count'],
                'log':        scan_state['log'][-30:],
                'error':      scan_state['error'],
            })
        else:
            # Serve any static file from ROOT (PDFs, etc.)
            candidate = ROOT / path.lstrip('/')
            if candidate.exists() and candidate.is_file():
                ext = candidate.suffix.lower()
                ct = {'.pdf': 'application/pdf', '.html': 'text/html',
                      '.json': 'application/json', '.css': 'text/css',
                      '.js': 'application/javascript'}.get(ext, 'application/octet-stream')
                self._serve_file(candidate, ct)
            else:
                self.send_error(404)

    def do_POST(self):
        if self.path == '/api/scan':
            if scan_state['running']:
                self._json({'ok': False, 'message': 'Scan already running'}, 409)
                return
            t = threading.Thread(target=_run_scan, daemon=True)
            t.start()
            self._json({'ok': True, 'message': 'Scan started'})
        else:
            self.send_error(404)

    def _serve_file(self, path, content_type):
        try:
            data = Path(path).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404, f'File not found: {path}')

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    port = int(os.environ.get('PORT', 5050))
    server = HTTPServer(('localhost', port), Handler)
    print(f'')
    print(f'  Basheer Khan — Internship Dashboard (local)')
    print(f'  ─────────────────────────────────────────────')
    print(f'  Open: http://localhost:{port}')
    print(f'  Click "Scan / Refresh" to find new internships')
    print(f'  Press Ctrl+C to stop')
    print(f'')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')


if __name__ == '__main__':
    main()
