#!/usr/bin/env python3
"""
scan_handshake_linkedin.py — Handshake + LinkedIn targeted scanner
Scrapes Handshake using the user's Chrome session cookies (no Excel needed).
Merges results into jobs.json.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT     = Path(__file__).parent
JOBS_OUT = ROOT / 'jobs.json'

# ── Internship filter (word boundary) ─────────────────────────────────────────
_INTERN_RE = re.compile(
    r'\b(intern(?:ship)?|co[\s\-]?op|extern(?:ship)?|fellowship|'
    r'summer\s+analyst|spring\s+analyst|winter\s+analyst|'
    r'summer\s+associate|student\s+(worker|analyst)|practicum|apprentice)\b',
    re.IGNORECASE
)
def is_internship(title): return bool(_INTERN_RE.search(title or ''))

MN_TERMS = [
    'minnesota','minneapolis','st. paul','saint paul','twin cities',
    'eden prairie','bloomington, mn','maple grove','burnsville','woodbury',
    'brooklyn park','eagan','lakeville','apple valley',', mn',' mn,',' mn ',
    'minnetonka','richfield','st paul','maplewood','roseville','golden valley',
    'plymouth, mn','shoreview','wayzata','arden hills','inver grove',
    'shakopee','brooklyn center','fridley','mendota','blaine','rochester, mn',
]
REMOTE_TERMS = [
    'remote','work from home','wfh','distributed','anywhere in the us',
    'us remote','remote us','remote - us','remote (us)','fully remote',
    'virtual','telecommute','remote / hybrid',
]
BLOCK_TERMS = [
    'india','bengaluru','hyderabad','united kingdom','london','germany',
    'berlin','france','paris','singapore','japan','brazil','australia','philippines',
]
def is_mn_or_remote(loc):
    if not loc: return True
    l = loc.lower()
    if any(b in l for b in BLOCK_TERMS): return False
    return any(t in l for t in MN_TERMS) or any(t in l for t in REMOTE_TERMS)

def log(msg): print(msg, flush=True)
def _now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def _job(company, role, location, url, source):
    return {'company':(company or '').strip(),'role':(role or '').strip(),
            'location':(location or '').strip(),'url':(url or '').strip(),
            'applied':False,'source':source,'scanned':_now()}

def make_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.4, status_forcelist=[500, 502, 503])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.headers.update({
        'User-Agent':('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36'),
    })
    return s
SESSION = make_session()

# ── Handshake via Chrome cookies ───────────────────────────────────────────────

HANDSHAKE_SEARCHES = [
    'https://app.joinhandshake.com/postings?page=1&per_page=25&sort_direction=desc&sort_column=default&employment_type_names[]=Internship&location=Minneapolis%2C+Minnesota&latitude=44.977753&longitude=-93.265015&radius=50',
    'https://app.joinhandshake.com/postings?page=1&per_page=25&sort_direction=desc&sort_column=default&employment_type_names[]=Internship&location=Minnesota&labels[]=data',
    'https://app.joinhandshake.com/postings?page=1&per_page=25&sort_direction=desc&sort_column=default&employment_type_names[]=Internship&location=United+States&labels[]=data&labels[]=analytics',
    # The user's saved search
    'https://minneapolis.joinhandshake.com/job-search/11094094?page=1&per_page=25',
]

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

def _get_chrome_cookies():
    """Copy Chrome cookies DB to temp and extract Handshake session cookies."""
    cookies_src = os.path.expanduser(
        '~/Library/Application Support/Google/Chrome/Default/Cookies'
    )
    if not os.path.exists(cookies_src):
        return {}
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        shutil.copy2(cookies_src, tmp.name)
        conn = sqlite3.connect(tmp.name)
        rows = conn.execute(
            "SELECT name, value FROM cookies WHERE host_key LIKE '%joinhandshake%'"
        ).fetchall()
        conn.close()
        # Chrome encrypts values on macOS — value column may be empty
        # We still pass what we get; session may work from headers alone
        return {r[0]: r[1] for r in rows if r[1]}
    except Exception:
        return {}
    finally:
        try: os.unlink(tmp.name)
        except: pass

def _scrape_handshake_chrome(url):
    """Use Chrome headless with copied profile to scrape Handshake."""
    if not os.path.exists(CHROME):
        return ''
    profile_src = os.path.expanduser(
        '~/Library/Application Support/Google/Chrome/Default'
    )
    tmp_root = tempfile.mkdtemp(prefix='hs-chrome-')
    tmp_profile = os.path.join(tmp_root, 'Default')
    try:
        shutil.copytree(profile_src, tmp_profile,
                        ignore=shutil.ignore_patterns('lock','SingletonLock',
                                                      'SingletonCookie','Lockfile'))
        result = subprocess.run([
            CHROME,
            '--headless=new', '--no-sandbox', '--disable-gpu',
            '--dump-dom',
            f'--user-data-dir={tmp_root}',
            '--profile-directory=Default',
            url,
        ], capture_output=True, text=True, timeout=25)
        return result.stdout
    except Exception as e:
        log(f'  [handshake/chrome] {e}')
        return ''
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

def _parse_handshake_html(html):
    """Extract job cards from Handshake HTML."""
    if not html: return []
    out = []
    # Handshake renders job titles in various places; try common patterns
    cards = re.findall(
        r'data-hook=["\']jobs-list-item["\'].*?(?=data-hook=["\']jobs-list-item["\']|$)',
        html, re.DOTALL
    )
    if not cards:
        # Fallback: look for job title + employer name patterns
        title_pat   = re.compile(r'data-hook=["\']jobs-list-item-title["\'][^>]*>([^<]+)', re.I)
        company_pat = re.compile(r'data-hook=["\']jobs-list-item-employer-name["\'][^>]*>([^<]+)', re.I)
        loc_pat     = re.compile(r'data-hook=["\']jobs-list-item-location["\'][^>]*>([^<]+)', re.I)
        id_pat      = re.compile(r'href=["\'][^"\']*?/jobs/(\d+)["\']')
        titles   = [t.strip() for t in title_pat.findall(html)]
        companies = [c.strip() for c in company_pat.findall(html)]
        locs     = [l.strip() for l in loc_pat.findall(html)]
        ids      = id_pat.findall(html)
        for i, title in enumerate(titles):
            if not is_internship(title): continue
            company = companies[i] if i < len(companies) else 'Unknown'
            loc     = locs[i]     if i < len(locs)     else 'Minnesota'
            if not is_mn_or_remote(loc): continue
            job_id  = ids[i] if i < len(ids) else ''
            url     = f'https://app.joinhandshake.com/jobs/{job_id}' if job_id else 'https://app.joinhandshake.com/postings'
            out.append(_job(company, title, loc, url, 'handshake'))
    return out

def _handshake_api(url):
    """Try Handshake API — works if session cookie is valid, silent if not."""
    cookies = _get_chrome_cookies()
    headers = {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://app.joinhandshake.com/postings',
    }
    try:
        r = SESSION.get(url, headers=headers, cookies=cookies, timeout=12)
        if r.status_code in (401, 403, 302): return []
        if r.status_code != 200: return []
        # Try to parse as JSON
        try:
            data = r.json()
            postings = data.get('postings') or data.get('results') or []
            out = []
            for j in postings:
                title   = j.get('title','') or j.get('name','')
                company = (j.get('employer') or {}).get('name','Unknown')
                loc     = j.get('location','') or j.get('city','')
                job_url = j.get('job_posting_url','') or f"https://app.joinhandshake.com/jobs/{j.get('id','')}"
                if not is_internship(title): continue
                if not is_mn_or_remote(loc): continue
                out.append(_job(company, title, loc or 'Minnesota', job_url, 'handshake'))
            return out
        except Exception:
            # Returned HTML — parse it
            return _parse_handshake_html(r.text)
    except Exception as e:
        log(f'  [handshake/api] {e}')
        return []

def scan_handshake():
    log('[handshake] Scanning via API + Chrome session...')
    all_results = []

    for url in HANDSHAKE_SEARCHES:
        # 1. Try API with cookies
        jobs = _handshake_api(url)
        if jobs:
            log(f'  + API: {len(jobs)} internships from {url[:60]}...')
            all_results.extend(jobs)
            continue

        # 2. Fall back to Chrome headless with copied profile
        log(f'  [handshake] API returned nothing — trying Chrome for {url[:60]}...')
        html = _scrape_handshake_chrome(url)
        jobs = _parse_handshake_html(html)
        if jobs:
            log(f'  + Chrome: {len(jobs)} internships')
            all_results.extend(jobs)
        else:
            log(f'  [handshake] No results (login may be required manually)')

        time.sleep(1)

    if not all_results:
        log('')
        log('[handshake] NOTE: Handshake requires you to be logged in.')
        log('[handshake] To get these jobs: log into Handshake in Chrome,')
        log('[handshake] then re-run this script — it uses your Chrome session.')
        log('')

    return all_results

# ── LinkedIn targeted searches ────────────────────────────────────────────────
LINKEDIN_SEARCHES = [
    # MN in-person — MIS / Analytics / Business focus
    {'keywords':'data analyst intern',           'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'business analyst intern',        'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'MIS intern',                     'location':'Minnesota, United States'},
    {'keywords':'information systems intern',     'location':'Minnesota, United States'},
    {'keywords':'business intelligence intern',   'location':'Minnesota, United States'},
    {'keywords':'data analytics internship',      'location':'Minnesota, United States'},
    {'keywords':'operations analyst intern',      'location':'Minnesota, United States'},
    {'keywords':'marketing analytics intern',     'location':'Minnesota, United States'},
    {'keywords':'ERP consulting intern',          'location':'Minnesota, United States'},
    {'keywords':'technology intern',              'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'finance intern',                 'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'accounting intern',              'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'supply chain intern',            'location':'Minnesota, United States'},
    {'keywords':'project management intern',      'location':'Minnesota, United States'},
    {'keywords':'IT intern',                      'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'data science intern',            'location':'Minnesota, United States'},
    # Remote
    {'keywords':'data analyst intern',            'location':'United States','f_WT':'2'},
    {'keywords':'business analyst intern',        'location':'United States','f_WT':'2'},
    {'keywords':'data analytics intern',          'location':'United States','f_WT':'2'},
    {'keywords':'business intelligence intern',   'location':'United States','f_WT':'2'},
    {'keywords':'MIS analytics internship',       'location':'United States','f_WT':'2'},
]

def fetch_linkedin(params):
    try:
        qs = {'keywords':params['keywords'],'location':params.get('location',''),
              'f_E':'1','f_JT':'I','sortBy':'DD','start':'0'}
        if 'f_WT' in params: qs['f_WT'] = params['f_WT']
        headers = {'Accept':'text/html,*/*','Accept-Language':'en-US,en;q=0.9',
                   'Referer':'https://www.linkedin.com/jobs/'}
        url = 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?' + urlencode(qs)
        r = SESSION.get(url, headers=headers, timeout=15)
        if r.status_code != 200: return []
        html = r.text
        id_pat  = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
        t_pat   = re.compile(r'class="base-search-card__title"[^>]*>\s*([^<]+)', re.DOTALL)
        co_pat  = re.compile(r'class="base-search-card__subtitle"[^>]*>(?:\s*<[^>]+>)*\s*([^<\n]+)', re.DOTALL)
        loc_pat = re.compile(r'class="job-search-card__location"[^>]*>\s*([^<\n]+)', re.DOTALL)
        jids = id_pat.findall(html)
        ts   = [t.strip() for t in t_pat.findall(html)]
        cos  = [c.strip() for c in co_pat.findall(html)]
        locs = [l.strip() for l in loc_pat.findall(html)]
        out  = []
        for i, jid in enumerate(jids):
            title = ts[i]   if i < len(ts)   else ''
            co    = cos[i]  if i < len(cos)  else 'Unknown'
            loc   = locs[i] if i < len(locs) else params.get('location','')
            if not is_internship(title): continue
            if not is_mn_or_remote(loc): continue
            out.append(_job(co, title, loc, f'https://www.linkedin.com/jobs/view/{jid}', 'linkedin'))
        return out
    except Exception as e:
        log(f'  [linkedin] {params["keywords"]}: {e}')
        return []

def scan_linkedin():
    log(f'[linkedin] Running {len(LINKEDIN_SEARCHES)} searches...')
    out = []
    for params in LINKEDIN_SEARCHES:
        jobs = fetch_linkedin(params)
        loc_lbl = 'Remote' if params.get('f_WT') == '2' else params.get('location','')
        if jobs:
            log(f'  + "{params["keywords"]}" / {loc_lbl}: {len(jobs)}')
        out.extend(jobs)
        time.sleep(1.1)
    log(f'[linkedin] {len(out)} total')
    return out

# ── Merge with jobs.json ──────────────────────────────────────────────────────
def merge(new_jobs):
    existing = []
    if JOBS_OUT.exists():
        try: existing = json.loads(JOBS_OUT.read_text())
        except: pass
    seen = {j['url'].split('?')[0].rstrip('/'): j for j in existing}
    added = 0
    for j in new_jobs:
        key = j['url'].split('?')[0].rstrip('/')
        if key not in seen:
            seen[key] = j; added += 1
    merged = list(seen.values())
    merged.sort(key=lambda j: ((j.get('company') or '').lower()))
    JOBS_OUT.write_text(json.dumps(merged, indent=2))
    log(f'[merge] +{added} new → {len(merged)} total in jobs.json')
    return merged

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log('')
    log('='*60)
    log('  Handshake + LinkedIn Scanner')
    log('='*60)
    log('')

    all_new = []
    all_new.extend(scan_handshake())
    log('')
    all_new.extend(scan_linkedin())
    log('')

    # Dedup new batch
    seen = set(); deduped = []
    for j in all_new:
        k = j['url'].split('?')[0].rstrip('/')
        if k not in seen: seen.add(k); deduped.append(j)

    log(f'[scan] {len(deduped)} unique new jobs this run')
    merged = merge(deduped)
    log(f'\nDone — {len(merged)} total internships in jobs.json')
    return merged

if __name__ == '__main__':
    main()
