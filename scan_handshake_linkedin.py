#!/usr/bin/env python3
"""
scan_handshake_linkedin.py — Handshake + LinkedIn + Excel Internship Scanner
Scans:
  1. Your Excel list  (/Users/basheerkhan/Downloads/Undergrad internships.xlsx)
  2. Handshake MN search (requires browser login — launches Chrome if available)
  3. LinkedIn MN + Remote internship search

Merges results into jobs.json (deduped, keeps existing entries).
"""

import json
import os
import re
import sys
import time
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, quote_plus

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent
JOBS_OUT   = ROOT / 'jobs.json'
EXCEL_FILE = Path('/Users/basheerkhan/Downloads/Undergrad internships.xlsx')

# ── Keywords ───────────────────────────────────────────────────────────────────

INTERN_KEYWORDS = [
    'intern', 'internship', 'co-op', 'coop', 'co op', 'extern', 'externship',
    'fellowship', 'summer analyst', 'winter analyst', 'spring analyst',
    'summer associate', 'student worker', 'practicum'
]

MN_KEYWORDS = [
    'minnesota', 'minneapolis', 'st. paul', 'saint paul', 'twin cities',
    'duluth', 'eden prairie', 'bloomington, mn', 'plymouth, mn',
    'maple grove', 'burnsville', 'woodbury', 'brooklyn park', 'eagan',
    'blaine', 'lakeville', 'coon rapids', 'apple valley', ', mn',
    ' mn ', ' mn,', 'minnetonka', 'richfield', 'st paul', 'wayzata',
    'maplewood mn', 'roseville mn', 'stillwater', 'shakopee', 'mankato',
    'st cloud', 'golden valley', 'hopkins mn', 'brooklyn center',
]

REMOTE_KEYWORDS = [
    'remote', 'work from home', 'wfh', 'distributed', 'anywhere in the us',
    'us remote', 'remote us', 'remote - us', 'remote (us)', 'remote, us',
    'fully remote', 'telecommute', 'virtual', 'remote / hybrid',
]

BLOCK_KEYWORDS = [
    'india', 'bengaluru', 'hyderabad', 'united kingdom', 'london',
    'germany', 'berlin', 'france', 'paris', 'spain', 'netherlands',
    'singapore', 'japan', 'brazil', 'australia', 'philippines', 'poland',
]


def is_mn_or_remote(loc: str) -> bool:
    if not loc:
        return True
    l = loc.lower()
    if any(k in l for k in BLOCK_KEYWORDS):
        return False
    return any(k in l for k in MN_KEYWORDS) or any(k in l for k in REMOTE_KEYWORDS)


def is_internship(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in INTERN_KEYWORDS)


def log(msg: str):
    print(msg, flush=True)


# ── HTTP session ───────────────────────────────────────────────────────────────

def make_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36'
        ),
    })
    return s

SESSION = make_session()


# ── 1. Excel scanner ───────────────────────────────────────────────────────────

def scan_excel() -> list:
    """Read the Undergrad Internships Excel and return active internship entries."""
    log('[excel] Reading Undergrad internships.xlsx...')
    try:
        import openpyxl
    except ImportError:
        log('[excel] openpyxl not installed — run: pip3 install openpyxl')
        return []

    if not EXCEL_FILE.exists():
        log(f'[excel] File not found: {EXCEL_FILE}')
        return []

    wb = openpyxl.load_workbook(str(EXCEL_FILE))
    ws = wb.active

    results = []
    skipped_filled = 0
    skipped_expired = 0

    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        if not any(row):
            continue

        # Columns: date, company, title, type, function, location, url, status
        date_val = row[0]
        company  = str(row[1] or '').strip()
        title    = str(row[2] or '').strip()
        job_type = str(row[3] or '').strip().lower()
        function = str(row[4] or '').strip()
        location = str(row[5] or '').strip()
        url      = str(row[6] or '').strip()
        status   = str(row[7] or '').strip().lower()

        # Filter: skip filled / expired
        if status in ('position filled', 'deadline passed'):
            if status == 'position filled':
                skipped_filled += 1
            else:
                skipped_expired += 1
            continue

        # Filter: internship type only (also include full-time from MN if relevant)
        if 'internship' not in job_type and 'intern' not in title.lower():
            continue

        # Filter: MN or Remote
        if not is_mn_or_remote(location):
            continue

        if not company or not title or not url:
            continue

        results.append({
            'company':  company,
            'role':     title,
            'location': location or 'Minnesota',
            'url':      url,
            'applied':  False,
            'source':   'excel',
            'scanned':  datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        })

    log(f'[excel] {len(results)} active internships found '
        f'({skipped_filled} filled, {skipped_expired} expired skipped)')
    return results


# ── 2. Handshake scanner ───────────────────────────────────────────────────────

HANDSHAKE_SEARCH_URL = 'https://minneapolis.joinhandshake.com/job-search/11094094?page={page}&per_page=25'

def scan_handshake_api() -> list:
    """Try Handshake public API endpoints for MN internships."""
    log('[handshake] Trying Handshake public API...')
    results = []

    # Handshake has a JSON endpoint used by their search UI
    api_url = 'https://app.joinhandshake.com/api/v1/postings?employment_type_names[]=Internship&location=Minneapolis%2C+Minnesota&page={page}&per_page=25'

    for page in range(1, 6):  # up to 5 pages
        try:
            headers = {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': 'https://app.joinhandshake.com/jobs',
            }
            r = SESSION.get(api_url.format(page=page), headers=headers, timeout=12)
            if r.status_code == 401:
                log('[handshake] API requires login — falling back to scrape')
                break
            if r.status_code != 200:
                break
            data = r.json()
            postings = data.get('postings', data.get('results', []))
            if not postings:
                break
            for j in postings:
                title   = j.get('title', '') or j.get('name', '')
                company = (j.get('employer', {}) or {}).get('name', 'Unknown')
                loc     = j.get('location', '') or j.get('city', '')
                job_url = j.get('job_posting_url', '') or f"https://app.joinhandshake.com/jobs/{j.get('id','')}"
                if not is_internship(title):
                    continue
                if not is_mn_or_remote(loc):
                    continue
                results.append({
                    'company':  company,
                    'role':     title,
                    'location': loc or 'Minnesota',
                    'url':      job_url,
                    'applied':  False,
                    'source':   'handshake',
                    'scanned':  datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                })
            time.sleep(0.5)
        except Exception as e:
            log(f'[handshake] API page {page}: {e}')
            break

    if results:
        log(f'[handshake] API: {len(results)} internships found')
    return results


def scan_handshake_chrome() -> list:
    """Launch Chrome to scrape Handshake — user must be logged in."""
    log('[handshake] Trying Chrome headless scrape...')
    chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if not os.path.exists(chrome):
        log('[handshake] Chrome not found, skipping')
        return []

    results = []
    for page in range(1, 4):
        url = HANDSHAKE_SEARCH_URL.format(page=page)
        try:
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
                tmp = f.name

            script = f"""
(async () => {{
  const r = await fetch('{url}', {{
    headers: {{'Accept': 'text/html,application/xhtml+xml,*/*', 'X-Requested-With': 'XMLHttpRequest'}}
  }});
  const t = await r.text();
  document.write('<pre id="d">' + encodeURIComponent(t) + '</pre>');
}})();
"""
            # Use Chrome to get the page with user's session cookies
            proc = subprocess.run([
                chrome,
                '--headless=new', '--no-sandbox', '--disable-gpu',
                '--dump-dom',
                '--user-data-dir=' + os.path.expanduser('~/Library/Application Support/Google/Chrome'),
                url
            ], capture_output=True, text=True, timeout=20)

            html = proc.stdout
            # Parse job cards from Handshake HTML
            # Job titles in <h3> or <a> with job link patterns
            title_matches   = re.findall(r'data-hook="jobs-list-item-title"[^>]*>([^<]+)', html)
            company_matches = re.findall(r'data-hook="jobs-list-item-employer-name"[^>]*>([^<]+)', html)
            loc_matches     = re.findall(r'data-hook="jobs-list-item-location"[^>]*>([^<]+)', html)
            id_matches      = re.findall(r'"/jobs/(\d+)"', html)

            for i, title in enumerate(title_matches):
                title   = title.strip()
                company = company_matches[i].strip() if i < len(company_matches) else 'Unknown'
                loc     = loc_matches[i].strip()     if i < len(loc_matches)     else ''
                job_id  = id_matches[i]               if i < len(id_matches)      else ''
                job_url = f'https://app.joinhandshake.com/jobs/{job_id}' if job_id else url

                if not is_internship(title):
                    continue
                if not is_mn_or_remote(loc):
                    continue
                results.append({
                    'company': company, 'role': title, 'location': loc or 'Minnesota',
                    'url': job_url, 'applied': False, 'source': 'handshake',
                    'scanned': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                })
        except Exception as e:
            log(f'[handshake] Chrome page {page}: {e}')
        time.sleep(1)

    if results:
        log(f'[handshake] Chrome scrape: {len(results)} internships')
    else:
        log('[handshake] No results from Chrome (may need to be logged in to Handshake)')
    return results


def scan_handshake() -> list:
    """Try API first, then Chrome, with instructions if both fail."""
    results = scan_handshake_api()
    if not results:
        results = scan_handshake_chrome()
    if not results:
        log('')
        log('[handshake] ⚠  Could not automatically scan Handshake.')
        log('[handshake]    Handshake requires a login. To scan manually:')
        log('[handshake]    1. Open your browser and log into Handshake')
        log('[handshake]    2. Go to: https://minneapolis.joinhandshake.com/job-search/11094094')
        log('[handshake]    3. Export or copy the job list into the Excel file')
        log('[handshake]    Then re-run this script to pick them up via the Excel scan.')
        log('')
    return results


# ── 3. LinkedIn scanner ────────────────────────────────────────────────────────

LINKEDIN_SEARCHES = [
    # MN-specific
    {'keywords': 'data analyst intern',           'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'business analyst intern',        'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'data analytics internship',      'location': 'Minnesota, United States'},
    {'keywords': 'MIS intern',                     'location': 'Minnesota, United States'},
    {'keywords': 'information systems intern',     'location': 'Minnesota, United States'},
    {'keywords': 'business intelligence intern',   'location': 'Minnesota, United States'},
    {'keywords': 'operations analyst intern',      'location': 'Minnesota, United States'},
    {'keywords': 'systems analyst internship',     'location': 'Minnesota, United States'},
    {'keywords': 'supply chain intern',            'location': 'Minnesota, United States'},
    {'keywords': 'finance intern',                 'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'accounting intern',              'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'marketing analytics intern',     'location': 'Minnesota, United States'},
    # Remote-specific
    {'keywords': 'data analyst intern',            'location': 'United States', 'f_WT': '2'},
    {'keywords': 'business analyst intern',        'location': 'United States', 'f_WT': '2'},
    {'keywords': 'data analytics intern',          'location': 'United States', 'f_WT': '2'},
    {'keywords': 'MIS business analytics intern',  'location': 'United States', 'f_WT': '2'},
    {'keywords': 'business intelligence intern',   'location': 'United States', 'f_WT': '2'},
]


def fetch_linkedin(params: dict) -> list:
    try:
        qs = {
            'keywords': params['keywords'],
            'location': params.get('location', ''),
            'f_E': '1',      # Entry level
            'f_JT': 'I',     # Internship
            'sortBy': 'DD',  # Date posted
            'start': '0',
        }
        if 'f_WT' in params:
            qs['f_WT'] = params['f_WT']

        headers = {
            'Accept': 'text/html,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.linkedin.com/jobs/',
        }
        url = 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?' + urlencode(qs)
        r = SESSION.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []

        html = r.text
        id_pat      = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
        title_pat   = re.compile(r'class="base-search-card__title"[^>]*>\s*([^<]+)', re.DOTALL)
        company_pat = re.compile(r'class="base-search-card__subtitle"[^>]*>(?:\s*<[^>]+>)*\s*([^<\n]+)', re.DOTALL)
        loc_pat     = re.compile(r'class="job-search-card__location"[^>]*>\s*([^<\n]+)', re.DOTALL)

        job_ids   = id_pat.findall(html)
        titles    = [t.strip() for t in title_pat.findall(html)]
        companies = [c.strip() for c in company_pat.findall(html)]
        locations = [l.strip() for l in loc_pat.findall(html)]

        results = []
        for i, job_id in enumerate(job_ids):
            title   = titles[i]    if i < len(titles)    else ''
            company = companies[i] if i < len(companies) else 'Unknown'
            loc     = locations[i] if i < len(locations) else params.get('location', '')
            if not is_internship(title):
                continue
            if not is_mn_or_remote(loc):
                continue
            results.append({
                'company':  company,
                'role':     title,
                'location': loc,
                'url':      f'https://www.linkedin.com/jobs/view/{job_id}',
                'applied':  False,
                'source':   'linkedin',
                'scanned':  datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            })
        return results
    except Exception as e:
        log(f'  [linkedin] {params["keywords"]}: {e}')
        return []


def scan_linkedin() -> list:
    log(f'[linkedin] Running {len(LINKEDIN_SEARCHES)} searches...')
    all_results = []
    for params in LINKEDIN_SEARCHES:
        jobs = fetch_linkedin(params)
        if jobs:
            log(f'  + "{params["keywords"]}" in "{params.get("location","")}": {len(jobs)} jobs')
        all_results.extend(jobs)
        time.sleep(1.2)
    log(f'[linkedin] Total: {len(all_results)} internships')
    return all_results


# ── Merge with existing jobs.json ──────────────────────────────────────────────

def load_existing() -> list:
    if JOBS_OUT.exists():
        try:
            return json.loads(JOBS_OUT.read_text())
        except Exception:
            pass
    return []


def merge_and_save(new_jobs: list) -> list:
    existing = load_existing()

    # Build URL index of existing jobs
    existing_urls = {j['url'].split('?')[0].rstrip('/'): j for j in existing}

    added = 0
    for j in new_jobs:
        key = j['url'].split('?')[0].rstrip('/')
        if key not in existing_urls:
            existing_urls[key] = j
            added += 1

    merged = list(existing_urls.values())

    # Sort: internships first, then by company
    merged.sort(key=lambda j: (
        0 if is_internship(j.get('role', '')) else 1,
        (j.get('company') or '').lower()
    ))

    JOBS_OUT.write_text(json.dumps(merged, indent=2))
    log(f'[merge] {added} new jobs added → {len(merged)} total in jobs.json')
    return merged


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log('')
    log('=' * 65)
    log('  Handshake + LinkedIn + Excel Internship Scanner')
    log('  MN & Remote only — small and large companies')
    log('=' * 65)
    log('')

    all_new = []

    # 1. Excel
    excel_jobs = scan_excel()
    all_new.extend(excel_jobs)
    log('')

    # 2. Handshake
    hs_jobs = scan_handshake()
    all_new.extend(hs_jobs)
    log('')

    # 3. LinkedIn
    li_jobs = scan_linkedin()
    all_new.extend(li_jobs)
    log('')

    # Dedup within new batch
    seen = set()
    deduped = []
    for j in all_new:
        key = j['url'].split('?')[0].rstrip('/')
        if key not in seen:
            seen.add(key)
            deduped.append(j)

    log(f'[scan] {len(deduped)} unique new jobs from this scan')

    # Merge with jobs.json
    merged = merge_and_save(deduped)

    log('')
    log(f'  Done — {len(merged)} total internships in jobs.json')
    log(f'  From this run: Excel={len(excel_jobs)}, Handshake={len(hs_jobs)}, LinkedIn={len(li_jobs)}')
    log('')

    # Print sample
    print(f'{"─"*65}')
    for j in deduped[:12]:
        src = j.get('source','')[:10].ljust(10)
        print(f'  [{src}] {(j["company"] or "")[:26]:26s} | {(j["role"] or "")[:36]:36s} | {j["location"]}')
    if len(deduped) > 12:
        print(f'  ... and {len(deduped)-12} more')
    print(f'{"─"*65}')

    return merged


if __name__ == '__main__':
    main()
