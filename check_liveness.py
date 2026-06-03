#!/usr/bin/env python3
"""
check_liveness.py — Verify each job in jobs.json is still posted.
Removes listings that are closed, filled, or 404'd.

How it detects closed jobs:
  - Greenhouse: redirects to ?error=true or to a different domain
  - Lever/Ashby: posting UUID disappears from the final URL
  - Any source: cross-domain redirect (job-boards.greenhouse.io → company.com/careers)
  - Any source: HTTP 404/410 response
  - Any source: body contains known "closed" phrases
  - Skips LinkedIn, Indeed, Handshake (require login to verify)
"""

import json
import re
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JOBS_FILE = Path(__file__).parent / 'jobs.json'

CLOSED_SIGNALS = [
    'no longer accepting applications',
    'this job is no longer available',
    'position has been filled',
    'this role has been filled',
    'this posting has been closed',
    'this position is closed',
    'this position has been closed',
    'job not found',
    'this job listing is no longer active',
    'application period has closed',
    'no longer available',
    'posting is closed',
    'job has been filled',
]

SKIP_DOMAINS = ['linkedin.com', 'indeed.com', 'joinhandshake.com']
SKIP_SOURCES = {'linkedin', 'indeed', 'handshake'}


def make_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.4, status_forcelist=[500, 502, 503])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
    })
    return s


SESSION = make_session()


def _host(url: str) -> str:
    """Extract bare hostname (no www) from a URL."""
    m = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return m.group(1).lower() if m else ''


def is_active(job: dict) -> bool:
    """Return True if the job posting is still live, False if closed."""
    url    = (job.get('url') or '').strip()
    source = (job.get('source') or '').lower()

    if not url:
        return False

    # Skip sources that require authentication
    if source in SKIP_SOURCES or any(d in url for d in SKIP_DOMAINS):
        return True

    try:
        r = SESSION.get(url, timeout=10, allow_redirects=True)
        final = r.url

        # ── Hard status codes ────────────────────────────────────────
        if r.status_code in (404, 410):
            return False

        # ── Greenhouse ───────────────────────────────────────────────
        # Closed Greenhouse jobs redirect to ?error=true, or the branded
        # company careers page (different domain), or drop the job ID.
        if 'greenhouse.io' in url:
            if 'error=true' in final:
                return False
            orig_h  = _host(url)
            final_h = _host(final)
            if orig_h and final_h and orig_h != final_h:
                return False          # redirected to company's own domain
            job_id = re.search(r'/jobs/(\d+)', url)
            if job_id and f'/jobs/{job_id.group(1)}' not in final:
                return False          # job ID disappeared

        # ── Lever ────────────────────────────────────────────────────
        # Closed Lever postings return 404 or redirect to the company page.
        elif 'jobs.lever.co' in url:
            uuid = re.search(
                r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
                url, re.I
            )
            if uuid and uuid.group(1).lower() not in final.lower():
                return False

        # ── Ashby ────────────────────────────────────────────────────
        elif 'ashbyhq.com' in url:
            uuid = re.search(
                r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
                url, re.I
            )
            if uuid and uuid.group(1).lower() not in final.lower():
                return False

        # ── Generic cross-domain redirect ────────────────────────────
        # If the final URL is on a completely different domain, the specific
        # job posting is gone and we landed on a fallback page.
        else:
            orig_h  = _host(url)
            final_h = _host(final)
            if orig_h and final_h and orig_h != final_h:
                return False

        # ── Body text check ──────────────────────────────────────────
        if r.status_code == 200:
            body = r.text.lower()
            if any(s in body for s in CLOSED_SIGNALS):
                return False

        return True  # looks active

    except Exception:
        return True  # network hiccup — don't remove the job


def run():
    if not JOBS_FILE.exists():
        print('[liveness] jobs.json not found — nothing to check')
        return

    jobs     = json.loads(JOBS_FILE.read_text())
    total    = len(jobs)
    checked  = 0
    removed  = []
    kept     = []

    print(f'[liveness] Checking {total} jobs...')

    for job in jobs:
        source = (job.get('source') or '').lower()
        url    = job.get('url') or ''

        # Jobs we skip (can't verify without login)
        if source in SKIP_SOURCES or any(d in url for d in SKIP_DOMAINS):
            kept.append(job)
            continue

        checked += 1
        if is_active(job):
            kept.append(job)
        else:
            removed.append(job)
            print(f'  ✗ closed  {job.get("company",""):28s} | {(job.get("role") or "")[:45]}')

        time.sleep(0.2)

    if removed:
        print(f'[liveness] Removed {len(removed)} closed listing(s).')
    else:
        print(f'[liveness] All {checked} verified jobs are still active.')

    print(f'[liveness] {len(kept)}/{total} remain after check.')
    JOBS_FILE.write_text(json.dumps(kept, indent=2))
    print(f'[liveness] jobs.json saved.')


if __name__ == '__main__':
    run()
