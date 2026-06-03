#!/usr/bin/env python3
"""
check_liveness.py — Verify each job in jobs.json is still active.
Removes listings where the posting has been closed, filled, or 404'd.
Skips LinkedIn and Indeed (require login / complex to verify).
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JOBS_FILE = Path(__file__).parent / 'jobs.json'

# Text patterns that mean the job is closed
CLOSED_SIGNALS = [
    'no longer accepting applications',
    'this job is no longer available',
    'position has been filled',
    'this role has been filled',
    'this posting has been closed',
    'this position is closed',
    'this position has been closed',
    'job not found',
    'page not found',
    'this job listing is no longer active',
    'application period has closed',
    'this role is no longer accepting',
    'no longer available',
    'posting is closed',
    'position is filled',
    'we are not currently',
    'job has been filled',
    'not currently hiring',
]

# Sources we can reliably check
CHECKABLE_SOURCES = {'greenhouse', 'ashby', 'lever', 'excel'}
# Sources we skip (require auth or bot detection)
SKIP_SOURCES = {'linkedin', 'indeed', 'handshake'}


def make_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,*/*',
    })
    return s


SESSION = make_session()


def is_active(job: dict) -> bool:
    """Return True if job is still active, False if closed/filled."""
    url    = job.get('url', '').strip()
    source = job.get('source', '').lower()

    if not url:
        return False

    # Skip sources we can't reliably check
    if source in SKIP_SOURCES:
        return True
    if 'linkedin.com' in url or 'indeed.com' in url or 'joinhandshake.com' in url:
        return True

    try:
        r = SESSION.get(url, timeout=9, allow_redirects=True)

        # 404 / 410 = definitely gone
        if r.status_code in (404, 410):
            return False

        # Redirect to home/jobs page often means the specific posting is gone
        if r.status_code in (301, 302, 303):
            final = r.url.lower()
            if any(x in final for x in ['/jobs', '/careers', '/home', 'greenhouse.io/', 'ashbyhq.com/', 'lever.co/']):
                if url.lower() not in final:
                    return False

        if r.status_code == 200:
            body = r.text.lower()
            if any(signal in body for signal in CLOSED_SIGNALS):
                return False

        return True  # looks active

    except Exception:
        return True  # network hiccup — keep the job, don't remove


def run():
    if not JOBS_FILE.exists():
        print('[liveness] jobs.json not found — skipping check')
        return

    jobs = json.loads(JOBS_FILE.read_text())
    total   = len(jobs)
    checked = 0
    removed = []
    kept    = []

    print(f'[liveness] Checking {total} jobs...')

    for job in jobs:
        source = job.get('source', '').lower()
        url    = job.get('url', '')

        if source in SKIP_SOURCES or 'linkedin.com' in url or 'indeed.com' in url:
            kept.append(job)
            continue  # don't count as checked

        checked += 1
        active = is_active(job)

        if active:
            kept.append(job)
        else:
            removed.append(job)
            print(f'  ✗ CLOSED  {job.get("company",""):28s} | {job.get("role","")[:40]}')

        time.sleep(0.15)  # polite delay

    if removed:
        print(f'[liveness] Removed {len(removed)} closed listings:')
        for j in removed:
            print(f'           - {j.get("company","")} — {j.get("role","")}')
    else:
        print(f'[liveness] All {checked} checked jobs still active.')

    print(f'[liveness] {len(kept)}/{total} jobs remain ({len(removed)} removed)')

    JOBS_FILE.write_text(json.dumps(kept, indent=2))
    print(f'[liveness] jobs.json updated.')


if __name__ == '__main__':
    run()
