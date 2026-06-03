#!/usr/bin/env python3
"""
scan_jobs.py — MN + Remote Internship Scanner for MIS / Business Analytics
Sources: Greenhouse API, Ashby API, Lever API, Workday API, LinkedIn guest API
Focus: Internships matching Basheer's major (MIS, Business Analytics, Data Analytics)
       in Minnesota (Twin Cities area) and Remote US
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JOBS_OUTPUT = "jobs.json"

# ── Internship filter (word-boundary regex — no false matches on "internal/external/international") ──

_INTERN_RE = re.compile(
    r'\b(intern(?:ship)?|co[\s\-]?op|extern(?:ship)?|fellowship|'
    r'summer\s+analyst|spring\s+analyst|winter\s+analyst|'
    r'summer\s+associate|student\s+(worker|analyst)|practicum|apprentice)\b',
    re.IGNORECASE
)

def is_internship(title: str) -> bool:
    return bool(_INTERN_RE.search(title or ''))

# ── Location filter ──────────────────────────────────────────────────────────

MN_TERMS = [
    'minnesota', 'minneapolis', 'st. paul', 'saint paul', 'twin cities',
    'eden prairie', 'bloomington, mn', 'maple grove', 'burnsville',
    'woodbury', 'brooklyn park', 'eagan', 'lakeville', 'apple valley',
    ', mn', ' mn,', ' mn ', 'minnetonka', 'richfield', 'st paul',
    'maplewood', 'roseville', 'golden valley', 'plymouth, mn',
    'shoreview', 'wayzata', 'arden hills', 'inver grove', 'shakopee',
    'brooklyn center', 'fridley', 'mendota', 'blaine', 'medina, mn',
    'bayport, mn', 'duluth, mn',
]
REMOTE_TERMS = [
    'remote', 'work from home', 'wfh', 'distributed', 'anywhere in the us',
    'us remote', 'remote us', 'remote - us', 'remote (us)',
    'remote, us', 'remote united states', 'fully remote', 'telecommute',
    'virtual', 'remote / hybrid', 'hybrid remote', 'remote first',
]
BLOCK_TERMS = [
    'india', 'bengaluru', 'hyderabad', 'pune', 'mumbai',
    'united kingdom', 'london', 'germany', 'berlin', 'munich',
    'france', 'paris', 'spain', 'netherlands', 'amsterdam',
    'singapore', 'japan', 'tokyo', 'brazil', 'australia', 'sydney',
    'philippines', 'poland', 'warsaw', 'canada only',
]

def is_mn_or_remote(loc: str) -> bool:
    if not loc:
        return True
    l = loc.lower()
    if any(b in l for b in BLOCK_TERMS):
        return False
    return any(t in l for t in MN_TERMS) or any(t in l for t in REMOTE_TERMS)

def log(msg: str):
    print(msg, flush=True)

# ── HTTP session ─────────────────────────────────────────────────────────────

def make_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.4, status_forcelist=[500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, */*',
    })
    return s

SESSION = make_session()

def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _job(company, role, location, url, source):
    return {
        'company':  company.strip(),
        'role':     role.strip(),
        'location': location.strip() if location else '',
        'url':      url.strip(),
        'applied':  False,
        'source':   source,
        'scanned':  _now(),
    }

# ── Greenhouse ───────────────────────────────────────────────────────────────

GREENHOUSE_SLUGS = [
    # ── MN-headquartered / strong MN presence ──
    'generalmills',       # General Mills, Golden Valley MN
    'landolakes',         # Land O'Lakes, Arden Hills MN
    'jamf',               # Jamf, Minneapolis MN
    'arcticwolfnetworks', # Arctic Wolf, Eden Prairie MN
    'spscommerce',        # SPS Commerce, Minneapolis MN
    'digitalriver',       # Digital River, Minnetonka MN
    'healthcatalyst',     # Health Catalyst, Minneapolis MN
    'cariboucoffee',      # Caribou Coffee, Brooklyn Center MN
    'securian',           # Securian Financial, St. Paul MN
    'cargill',            # Cargill, Wayzata MN
    'andersencorporation',# Andersen Windows, Bayport MN
    'chsinc',             # CHS Inc., Inver Grove Heights MN
    'allianzlife',        # Allianz Life, Minneapolis MN
    'donaldson',          # Donaldson Company, Minneapolis MN
    'graco',              # Graco, Minneapolis MN
    # ── National analytics / data / MIS companies (remote-friendly) ──
    'amplitude',          # Product analytics
    'mixpanel',           # Product analytics
    'heap',               # Product analytics
    'fullstory',          # Digital experience analytics
    'alteryx',            # Analytics platform
    'databricks',         # Data lakehouse
    'dbtlabs',            # dbt Labs, data transformation
    'fivetran',           # ELT / data pipelines
    'confluent',          # Kafka / data streaming
    'elastic',            # Search & analytics
    'datadog',            # Observability + analytics
    'hashicorp',          # Infrastructure / data tooling
    'starburst',          # Query engine / analytics
    'dremio',             # Data lakehouse
    'thoughtspot',        # Analytics
    'sigma',              # Cloud analytics
    'matillion',          # Data integration
    'montecarlodata',     # Data observability
    'atlan',              # Data catalog
    # ── Business / ops / finance analytics (remote-friendly) ──
    'stripe',             # Fintech
    'brex',               # Corporate finance
    'rippling',           # HR/Payroll/Analytics
    'gusto',              # HR/Payroll analytics
    'lattice',            # HR analytics
    'carta',              # Cap table / finance analytics
    'mercury',            # Business banking
    'pilot',              # Finance ops
    'ramp',               # Spend analytics
    'workos',             # Auth / SaaS
    'hubspot',            # CRM / marketing analytics
    'klaviyo',            # Email analytics
    'gong',               # Revenue analytics
    'outreach',           # Sales analytics
    'salesloft',          # Sales analytics
    'clari',              # Revenue analytics
    'hightouch',          # Reverse ETL / analytics
    'rackner',            # Consulting, remote
    'doublegood',         # Analytics internship poster
    'cohere',             # AI / data
    'anthropic',          # AI research
    'scaleai',            # Data labeling / AI
    # ── MN companies that sometimes post on Greenhouse ──
    'bestbuy',            # Best Buy, Richfield MN
    'target',             # Target, Minneapolis MN
    'polaris',            # Polaris Industries, Medina MN
    'sleepnumber',        # Sleep Number, Minneapolis MN
]

def fetch_greenhouse(slug: str) -> list:
    try:
        r = SESSION.get(
            f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs',
            timeout=10
        )
        if r.status_code != 200:
            return []
        data = r.json()
        company_name = (data.get('company') or {}).get('name') or slug.replace('-', ' ').title()
        results = []
        for j in (data.get('jobs') or []):
            title = j.get('title', '')
            if not is_internship(title):
                continue
            offices = j.get('offices') or []
            loc = ', '.join(o.get('name', '') for o in offices if o.get('name'))
            if not loc:
                loc_obj = j.get('location') or {}
                loc = loc_obj.get('name', '') if isinstance(loc_obj, dict) else ''
            if not is_mn_or_remote(loc):
                continue
            url = j.get('absolute_url', '')
            if not url:
                continue
            results.append(_job(company_name, title, loc or 'Remote', url, 'greenhouse'))
        return results
    except Exception as e:
        log(f'  [greenhouse] {slug}: {e}')
        return []

# ── Ashby ────────────────────────────────────────────────────────────────────

ASHBY_SLUGS = [
    'm13',          # M13 / Robyn AI — data analyst intern
    'resend',       # Resend — email infra analytics
    'claylabs',     # Clay Labs — data analytics
    'legora',       # Legora — data analytics
    'decagon',      # Decagon — ops/analytics
    'perplexityai', # Perplexity AI
    'anysphere',    # Cursor / AI
    'hex',          # Hex — collaborative analytics notebooks
    'baseten',      # Baseten — ML infra
    'vanta',        # Vanta — compliance analytics
    'watershed',    # Watershed — climate analytics
    'retool',       # Retool — internal tools
    'lightdash',    # Lightdash — BI / analytics
    'motherduck',   # MotherDuck — data warehouse
    'evidence',     # Evidence — analytics dashboards
    'hyperquery',   # HyperQuery — analytics
    'cortex',       # Cortex — platform analytics
    'hatchet',      # Hatchet — workflow engine
    'fireworks',    # Fireworks AI
    'together',     # Together AI
    'comet',        # Comet — ML experiment tracking
    'whylabs',      # WhyLabs — data observability
    'gretel',       # Gretel — synthetic data
    'modal',        # Modal — cloud compute
    'prefect',      # Prefect — data workflows
    'astronomer',   # Astronomer — Airflow
    'census',       # Census — reverse ETL
    'chargebee',    # Chargebee — subscription analytics
]

def fetch_ashby(slug: str) -> list:
    try:
        r = SESSION.get(
            f'https://api.ashbyhq.com/posting-api/job-board/{slug}',
            timeout=10
        )
        if r.status_code != 200:
            return []
        data = r.json()
        company_name = (data.get('organization') or {}).get('name') or slug.title()
        results = []
        for j in (data.get('jobPostings') or []):
            title = j.get('title', '')
            if not is_internship(title):
                continue
            loc = j.get('location') or j.get('locationName') or ''
            if not is_mn_or_remote(loc):
                continue
            url = j.get('jobUrl') or j.get('applyUrl') or ''
            if not url:
                continue
            results.append(_job(company_name, title, loc or 'Remote', url, 'ashby'))
        return results
    except Exception as e:
        log(f'  [ashby] {slug}: {e}')
        return []

# ── Lever ────────────────────────────────────────────────────────────────────

LEVER_SLUGS = [
    'voltus',       # Energy data analytics
    'grammarly',    # Writing analytics
    'coursera',     # EdTech analytics
    'duolingo',     # EdTech analytics
    'reddit',       # Data analytics
    'pinterest',    # Data analytics
    'carta',        # Finance analytics
    'plaid',        # Fintech analytics
    'chime',        # Fintech
    'robinhood',    # Fintech analytics
    'box',          # Cloud storage analytics
    'dropbox',      # Cloud storage
    'postman',      # API analytics
    'springhealth', # Mental health
    'cerebral',     # Healthcare analytics
    'quora',        # Knowledge analytics
    'mparticle',    # Customer data platform
    'surveymonkey', # Survey analytics
    'zendesk',      # CX analytics
    'intercom',     # Customer messaging analytics
    'driftt',       # Conversational marketing
    'lob',          # Direct mail analytics
]

def fetch_lever(slug: str) -> list:
    try:
        r = SESSION.get(
            f'https://api.lever.co/v0/postings/{slug}?mode=json&limit=500',
            timeout=10
        )
        if r.status_code != 200:
            return []
        results = []
        for j in (r.json() or []):
            title = j.get('text', '')
            if not is_internship(title):
                continue
            cats = j.get('categories') or {}
            locs = cats.get('allLocations') or []
            loc = locs[0] if locs else cats.get('location', '')
            if not is_mn_or_remote(loc):
                continue
            url = j.get('hostedUrl') or j.get('applyUrl') or ''
            if not url:
                continue
            company = j.get('company') or slug.replace('-', ' ').title()
            results.append(_job(company, title, loc or 'Remote', url, 'lever'))
        return results
    except Exception as e:
        log(f'  [lever] {slug}: {e}')
        return []

# ── Workday (major MN employers) ─────────────────────────────────────────────
# These are the big MN companies that don't use Greenhouse/Ashby/Lever

WORKDAY_COMPANIES = [
    # (display_name, tenant, wd_host, career_path)
    ('Target',           'target',        'wd5', 'targetcareers'),
    ('Best Buy',         'bestbuy',       'wd5', 'bestbuy_careers'),
    ('Medtronic',        'medtronic',     'wd1', 'medtronic_careers'),
    ('US Bank',          'usbank',        'wd5', 'US_Bank_Careers'),
    ('3M',               '3m',            'wd1', '3M'),
    ('Ameriprise',       'ameriprise',    'wd5', 'ameriprise_careers'),
    ('Piper Sandler',    'pipersandler',  'wd501','Piper_Sandler_Careers'),
    ('Allianz Life',     'allianzlife',   'wd3', 'Allianz_External_Careers'),
    ('Polaris',          'polarisinc',    'wd5', 'Polaris_Careers'),
    ('Toro Company',     'thetorocompany','wd5', 'thetorocompany'),
    ('Andersen Windows', 'andersenwindows','wd5','Andersen_External_Careers'),
    ('Sleep Number',     'sleepnumber',   'wd5', 'sleepnumber_careers'),
    ('Wells Fargo',      'wellsfargo',    'wd5', 'Wells_Fargo_External'),
    ('UnitedHealth',     'uhg',           'wd5', 'corporateUHC'),
    ('Optum',            'uhg',           'wd5', 'Optum'),
    ('Ecolab',           'ecolab',        'wd5', 'ecolab_careers'),
    ('Xcel Energy',      'xcelenergy',    'wd5', 'XcelEnergy'),
    ('CHS Inc.',         'chsinc',        'wd5', 'CHS'),
]

def fetch_workday(display_name: str, tenant: str, wd_host: str, career_path: str) -> list:
    """Query Workday's internal JSON API for intern postings."""
    api_url = f'https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{career_path}/jobs'
    payload = {
        'appliedFacets': {},
        'limit': 20,
        'offset': 0,
        'searchText': 'intern',
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Calypso-CSRF-Token': '1',
    }
    try:
        r = SESSION.post(api_url, json=payload, headers=headers, timeout=12)
        if r.status_code not in (200, 201):
            return []
        data = r.json()
        postings = data.get('jobPostings') or []
        results = []
        for j in postings:
            title = j.get('title', '')
            if not is_internship(title):
                continue
            loc = j.get('locationsText') or j.get('locations') or ''
            if isinstance(loc, list):
                loc = ', '.join(loc)
            if not is_mn_or_remote(loc):
                continue
            ext_path = j.get('externalPath') or ''
            url = f'https://{tenant}.{wd_host}.myworkdayjobs.com/{career_path}{ext_path}' if ext_path else api_url
            results.append(_job(display_name, title, loc or 'Minnesota', url, 'workday'))
        return results
    except Exception as e:
        log(f'  [workday] {display_name}: {e}')
        return []

# ── LinkedIn guest API ───────────────────────────────────────────────────────
# Targeted at MIS / Business Analytics / Data Analytics

LINKEDIN_SEARCHES = [
    # ── MN in-person ──
    {'keywords': 'data analyst intern',           'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'business analyst intern',        'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'business analytics internship',  'location': 'Minnesota, United States'},
    {'keywords': 'data analytics intern',          'location': 'Minnesota, United States'},
    {'keywords': 'MIS intern',                     'location': 'Minnesota, United States'},
    {'keywords': 'information systems intern',     'location': 'Minnesota, United States'},
    {'keywords': 'business intelligence intern',   'location': 'Minnesota, United States'},
    {'keywords': 'IT intern',                      'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'operations analyst intern',      'location': 'Minnesota, United States'},
    {'keywords': 'finance intern',                 'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'accounting intern',              'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'marketing analytics intern',     'location': 'Minnesota, United States'},
    {'keywords': 'systems analyst intern',         'location': 'Minnesota, United States'},
    {'keywords': 'supply chain intern',            'location': 'Minnesota, United States'},
    {'keywords': 'project management intern',      'location': 'Minnesota, United States'},
    # ── Remote ──
    {'keywords': 'data analyst intern',            'location': 'United States', 'f_WT': '2'},
    {'keywords': 'business analyst intern',        'location': 'United States', 'f_WT': '2'},
    {'keywords': 'data analytics intern',          'location': 'United States', 'f_WT': '2'},
    {'keywords': 'business intelligence intern',   'location': 'United States', 'f_WT': '2'},
    {'keywords': 'MIS analytics internship',       'location': 'United States', 'f_WT': '2'},
    {'keywords': 'operations analyst intern',      'location': 'United States', 'f_WT': '2'},
    {'keywords': 'marketing analytics intern',     'location': 'United States', 'f_WT': '2'},
    {'keywords': 'product analyst intern',         'location': 'United States', 'f_WT': '2'},
    {'keywords': 'finance analyst intern',         'location': 'United States', 'f_WT': '2'},
    {'keywords': 'information systems internship', 'location': 'United States', 'f_WT': '2'},
]

def fetch_linkedin(params: dict) -> list:
    try:
        qs = {
            'keywords': params['keywords'],
            'location': params.get('location', ''),
            'f_E': '1',
            'f_JT': 'I',
            'sortBy': 'DD',
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
        for i, jid in enumerate(job_ids):
            title   = titles[i]    if i < len(titles)    else ''
            company = companies[i] if i < len(companies) else 'Unknown'
            loc     = locations[i] if i < len(locations) else params.get('location', '')
            if not is_internship(title):
                continue
            if not is_mn_or_remote(loc):
                continue
            results.append(_job(company, title, loc, f'https://www.linkedin.com/jobs/view/{jid}', 'linkedin'))
        return results
    except Exception as e:
        log(f'  [linkedin] {params["keywords"]}: {e}')
        return []

# ── Dedup ────────────────────────────────────────────────────────────────────

def dedup(jobs: list) -> list:
    seen = set()
    out  = []
    for j in jobs:
        key = j['url'].split('?')[0].rstrip('/')
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out

# ── Main ─────────────────────────────────────────────────────────────────────

def scan() -> list:
    all_jobs = []

    log(f'[scan] MN + Remote Internship Scanner — MIS / Business Analytics focus')
    log(f'[scan] Greenhouse: {len(GREENHOUSE_SLUGS)} | Ashby: {len(ASHBY_SLUGS)} | '
        f'Lever: {len(LEVER_SLUGS)} | Workday: {len(WORKDAY_COMPANIES)} | '
        f'LinkedIn: {len(LINKEDIN_SEARCHES)} searches')
    log('')

    log('[scan] Greenhouse API...')
    for slug in GREENHOUSE_SLUGS:
        jobs = fetch_greenhouse(slug)
        if jobs:
            log(f'  + {slug}: {len(jobs)} internships')
        all_jobs.extend(jobs)
        time.sleep(0.08)

    log('[scan] Ashby API...')
    for slug in ASHBY_SLUGS:
        jobs = fetch_ashby(slug)
        if jobs:
            log(f'  + {slug}: {len(jobs)} internships')
        all_jobs.extend(jobs)
        time.sleep(0.08)

    log('[scan] Lever API...')
    for slug in LEVER_SLUGS:
        jobs = fetch_lever(slug)
        if jobs:
            log(f'  + {slug}: {len(jobs)} internships')
        all_jobs.extend(jobs)
        time.sleep(0.08)

    log('[scan] Workday API (major MN employers)...')
    for (name, tenant, host, path) in WORKDAY_COMPANIES:
        jobs = fetch_workday(name, tenant, host, path)
        if jobs:
            log(f'  + {name}: {len(jobs)} internships')
        all_jobs.extend(jobs)
        time.sleep(0.2)

    log('[scan] LinkedIn guest API...')
    for params in LINKEDIN_SEARCHES:
        jobs = fetch_linkedin(params)
        if jobs:
            kw  = params['keywords']
            loc = 'Remote' if params.get('f_WT') == '2' else params.get('location', '')
            log(f'  + LinkedIn "{kw}" / {loc}: {len(jobs)} jobs')
        all_jobs.extend(jobs)
        time.sleep(1.2)

    all_jobs = dedup(all_jobs)
    all_jobs.sort(key=lambda j: (
        0 if is_internship(j['role']) else 1,
        (j.get('company') or '').lower()
    ))

    log(f'\n[scan] Done — {len(all_jobs)} unique internships found.')
    with open(JOBS_OUTPUT, 'w') as f:
        json.dump(all_jobs, f, indent=2)
    log(f'[scan] Written to {JOBS_OUTPUT}')
    return all_jobs

if __name__ == '__main__':
    jobs = scan()
    print(f'\n{"─"*72}')
    mn  = sum(1 for j in jobs if any(t in (j['location'] or '').lower() for t in MN_TERMS))
    rem = sum(1 for j in jobs if any(t in (j['location'] or '').lower() for t in REMOTE_TERMS))
    print(f'  Total: {len(jobs)}  |  MN: {mn}  |  Remote: {rem}')
    print(f'{"─"*72}')
    for j in jobs[:20]:
        src = (j.get('source') or '')[:10].ljust(10)
        print(f'  [{src}] {(j["company"] or "")[:26]:26s} | {(j["role"] or "")[:38]:38s} | {j["location"]}')
    if len(jobs) > 20:
        print(f'  ... and {len(jobs)-20} more')
    print(f'{"─"*72}')
