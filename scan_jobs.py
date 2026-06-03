#!/usr/bin/env python3
"""
scan_jobs.py — Minnesota & Remote Internship Scanner
Searches Greenhouse, Ashby, Lever APIs + Indeed RSS + LinkedIn guest API
Focuses exclusively on Minnesota (Twin Cities + state) and Remote US internships
Includes small AND large companies
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JOBS_OUTPUT = "jobs.json"

# ── Keyword filters ────────────────────────────────────────────────────────────

INTERN_KEYWORDS = [
    'intern', 'internship', 'co-op', 'coop', 'co op', 'extern', 'externship',
    'fellowship', 'summer analyst', 'winter analyst', 'spring analyst',
    'summer associate', 'student worker', 'practicum', 'apprentice'
]

MN_KEYWORDS = [
    'minnesota', 'minneapolis', 'st. paul', 'saint paul', 'twin cities',
    'duluth', 'rochester, mn', 'eden prairie', 'bloomington, mn', 'bloomington mn',
    'plymouth, mn', 'maple grove', 'burnsville', 'woodbury', 'brooklyn park',
    'eagan', 'blaine', 'lakeville', 'coon rapids', 'apple valley', ' mn ',
    ', mn', ' mn,', 'minnetonka', 'richfield', 'st paul', 'maplewood mn',
    'roseville mn', 'cottage grove', 'stillwater mn', 'shakopee', 'mankato',
    'st cloud', 'golden valley', 'hopkins mn', 'inver grove'
]

REMOTE_KEYWORDS = [
    'remote', 'work from home', 'wfh', 'distributed', 'anywhere in the us',
    'anywhere in us', 'us remote', 'remote us', 'remote - us', 'remote (us)',
    'remote, us', 'remote united states', 'fully remote', 'telecommute',
    'remote / hybrid', 'hybrid remote', 'remote first', 'virtual'
]

# Block non-US international
BLOCK_KEYWORDS = [
    'india', 'bengaluru', 'hyderabad', 'pune', 'mumbai', 'delhi', 'chennai',
    'united kingdom', 'london', 'germany', 'berlin', 'munich', 'france', 'paris',
    'spain', 'barcelona', 'madrid', 'netherlands', 'amsterdam', 'sweden',
    'stockholm', 'singapore', 'japan', 'tokyo', 'brazil', 'australia', 'sydney',
    'philippines', 'manila', 'poland', 'warsaw', 'canada only', 'toronto',
    'ontario', 'british columbia',
]


def is_mn_or_remote(location: str) -> bool:
    if not location:
        return True  # no location = don't exclude
    loc = location.lower()
    if any(kw in loc for kw in BLOCK_KEYWORDS):
        return False
    return any(kw in loc for kw in MN_KEYWORDS) or any(kw in loc for kw in REMOTE_KEYWORDS)


def is_internship(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in INTERN_KEYWORDS)


# ── HTTP Session ───────────────────────────────────────────────────────────────

def make_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=0.4, status_forcelist=[429, 500, 502, 503, 504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.mount('http://',  HTTPAdapter(max_retries=retry))
    s.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, */*',
    })
    return s

SESSION = make_session()


# ── Company lists ──────────────────────────────────────────────────────────────

# Greenhouse ATS slugs — large + small companies that post MN and/or remote internships
GREENHOUSE_SLUGS = [
    # MN-headquartered / large MN presence
    'target', 'bestbuy', 'generalmills', 'landolakes', 'jamf',
    'arcticwolfnetworks', 'spscommerce', 'digitalriver', 'cargill',
    'securian', 'ameriprise', 'healthcatalyst', 'wellbeam',
    # National / remote-friendly tech
    'figma', 'notion', 'stripe', 'brex', 'rippling', 'gusto', 'lattice',
    'hightouch', 'doublegood', 'rackner', 'databricks', 'klaviyo', 'hubspot',
    'amplitude', 'mixpanel', 'fullstory', 'alteryx', 'fivetran', 'airbyte',
    'intercom', 'cockroachlabs', 'matillion', 'dbtlabs', 'dagsterlabs',
    'montecarlodata', 'zapier', 'airtable', 'miro', 'mercury', 'pilot',
    'deel', 'workos', 'datadog', 'cloudflare', 'confluent', 'elastic',
    'splunk', 'pagerduty', 'atlassian', 'zendesk', 'freshworks',
    'gong', 'outreach', 'salesloft', 'clari', 'chorus', 'mindtickle',
    'heap', 'segment', 'drift', 'intercom', 'hotjar',
    # AI/ML companies (many post remote internships)
    'anthropic', 'cohere', 'scaleai', 'huggingface',
    'weights-biases', 'arize', 'whylabs', 'gretel',
    # Data/Analytics tools
    'prefect', 'astronomer', 'meltano', 'dremio', 'starburst',
    'paradime', 'transform', 'y42', 'datacoves',
    # Finance tech
    'plaid', 'carta', 'affirm', 'marqeta', 'brex',
    # Healthcare tech (some MN)
    'optum', 'wellbeam', 'wellskyhealth', 'healthcatalyst',
    # Small/startup
    'ramp', 'puzzle', 'replit', 'railway', 'modal',
    'novu', 'trigger', 'inngest', 'liveblocks',
    # MN small/mid companies
    'logicgate', 'smartcare', 'daiohs', 'brightplan',
    # Retail/Consumer (MN)
    'target', 'mybella', 'caribou', 'dairyqueen',
]

# Remove duplicates while preserving order
_seen = set()
GREENHOUSE_SLUGS = [x for x in GREENHOUSE_SLUGS if not (x in _seen or _seen.add(x))]

# Ashby ATS slugs
ASHBY_SLUGS = [
    'm13', 'resend', 'claylabs', 'legora', 'decagon', 'perplexityai',
    'anysphere', 'hex', 'baseten', 'vanta', 'watershed', 'retool',
    'loom', 'chargebee', 'census', 'brainfish', 'orb',
    'temporal', 'humanloop', 'whylabs', 'gretel', 'trifacta',
    'motherduck', 'evidence', 'hyperquery', 'lightdash',
    'notdiamond', 'hatchet', 'trigger', 'resend', 'infisical',
    'cortex', 'incident', 'fireworks', 'together', 'comet',
    'neptune', 'apideck', 'prismatic', 'knock', 'courier',
]

# Remove duplicates
_seen2 = set()
ASHBY_SLUGS = [x for x in ASHBY_SLUGS if not (x in _seen2 or _seen2.add(x))]

# Lever ATS slugs
LEVER_SLUGS = [
    'voltus', 'grammarly', 'coursera', 'duolingo', 'reddit',
    'pinterest', 'carta', 'plaid', 'chime', 'robinhood',
    'box', 'dropbox', 'docusign', 'postman',
    'zendesk', 'intercom', 'drift',
    'springhealth', 'cerebral', 'brightline',
]

# Indeed RSS feeds — MN and Remote specifically
INDEED_FEEDS = [
    ('https://www.indeed.com/rss?q=data+analyst+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=business+analyst+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=MIS+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=information+systems+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=business+intelligence+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=data+analytics+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=operations+analyst+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=systems+analyst+intern&l=Minnesota&sort=date&limit=25', 'MN'),
    ('https://www.indeed.com/rss?q=data+analyst+intern&l=Remote&sort=date&limit=25', 'Remote'),
    ('https://www.indeed.com/rss?q=business+analyst+intern&l=Remote&sort=date&limit=25', 'Remote'),
    ('https://www.indeed.com/rss?q=data+analytics+intern&l=Remote&sort=date&limit=25', 'Remote'),
    ('https://www.indeed.com/rss?q=MIS+internship&l=Remote&sort=date&limit=25', 'Remote'),
    ('https://www.indeed.com/rss?q=business+intelligence+internship&l=Remote&sort=date&limit=25', 'Remote'),
]

# LinkedIn guest API search configurations
LINKEDIN_SEARCHES = [
    {'keywords': 'data analyst intern', 'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'business analyst intern', 'location': 'Minneapolis, Minnesota, United States'},
    {'keywords': 'data analytics internship', 'location': 'Minnesota, United States'},
    {'keywords': 'MIS intern', 'location': 'Minnesota, United States'},
    {'keywords': 'information systems intern', 'location': 'Minnesota, United States'},
    {'keywords': 'business intelligence intern', 'location': 'Minnesota, United States'},
    {'keywords': 'data analyst internship remote', 'location': 'United States', 'f_WT': '2'},
    {'keywords': 'business analyst intern remote', 'location': 'United States', 'f_WT': '2'},
    {'keywords': 'data analytics intern remote', 'location': 'United States', 'f_WT': '2'},
    {'keywords': 'MIS business analytics intern', 'location': 'United States', 'f_WT': '2'},
]


# ── Fetchers ───────────────────────────────────────────────────────────────────

def fetch_greenhouse(slug: str) -> list:
    try:
        url = f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs'
        resp = SESSION.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        company_name = data.get('company', {}).get('name', slug.replace('-', ' ').title())
        jobs = data.get('jobs', [])
        results = []
        for j in jobs:
            title = j.get('title', '')
            if not is_internship(title):
                continue
            offices = j.get('offices', [])
            loc = ', '.join(o.get('name', '') for o in offices if o.get('name'))
            if not loc:
                loc = j.get('location', {}).get('name', '') if isinstance(j.get('location'), dict) else ''
            if not is_mn_or_remote(loc):
                continue
            job_url = j.get('absolute_url', '')
            if not job_url:
                continue
            results.append({
                'company': company_name,
                'role': title,
                'location': loc or 'Remote',
                'url': job_url,
                'source': 'greenhouse',
            })
        return results
    except Exception as e:
        print(f'  [greenhouse] {slug}: {e}', file=sys.stderr)
        return []


def fetch_ashby(slug: str) -> list:
    try:
        url = f'https://api.ashbyhq.com/posting-api/job-board/{slug}'
        resp = SESSION.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        company_name = data.get('organization', {}).get('name', slug.replace('-', ' ').title())
        postings = data.get('jobPostings', [])
        results = []
        for j in postings:
            title = j.get('title', '')
            if not is_internship(title):
                continue
            loc = j.get('location', '') or j.get('locationName', '') or ''
            if not is_mn_or_remote(loc):
                continue
            job_url = j.get('jobUrl', '') or j.get('applyUrl', '')
            if not job_url:
                continue
            results.append({
                'company': company_name,
                'role': title,
                'location': loc or 'Remote',
                'url': job_url,
                'source': 'ashby',
            })
        return results
    except Exception as e:
        print(f'  [ashby] {slug}: {e}', file=sys.stderr)
        return []


def fetch_lever(slug: str) -> list:
    try:
        url = f'https://api.lever.co/v0/postings/{slug}?mode=json&limit=500'
        resp = SESSION.get(url, timeout=10)
        if resp.status_code != 200:
            return []
        postings = resp.json()
        results = []
        for j in postings:
            title = j.get('text', '')
            if not is_internship(title):
                continue
            cats = j.get('categories', {})
            loc = cats.get('location', '')
            if not loc and isinstance(cats.get('allLocations'), list):
                loc = cats['allLocations'][0] if cats['allLocations'] else ''
            if not is_mn_or_remote(loc):
                continue
            job_url = j.get('hostedUrl', '') or j.get('applyUrl', '')
            if not job_url:
                continue
            company = j.get('company', slug.replace('-', ' ').title())
            results.append({
                'company': company,
                'role': title,
                'location': loc or 'Remote',
                'url': job_url,
                'source': 'lever',
            })
        return results
    except Exception as e:
        print(f'  [lever] {slug}: {e}', file=sys.stderr)
        return []


def fetch_indeed(feed_url: str, region: str) -> list:
    try:
        headers = {
            'Accept': 'application/rss+xml,application/xml,text/xml,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        resp = SESSION.get(feed_url, timeout=15, headers=headers)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        # Indeed namespace
        ns = 'https://www.indeed.com/about/rss'
        results = []
        for item in root.findall('.//item'):
            title_el   = item.find('title')
            link_el    = item.find('link')
            if title_el is None or link_el is None:
                continue
            title = (title_el.text or '').strip()
            url   = (link_el.text or '').strip()
            if not is_internship(title):
                continue
            # Try to get employer name
            company = 'Unknown'
            for tag in [f'{{{ns}}}employer', 'source']:
                el = item.find(tag)
                if el is not None and el.text:
                    company = el.text.strip()
                    break
            # Location
            loc = region  # default to feed region
            for tag in [f'{{{ns}}}jobLocation', f'{{{ns}}}location']:
                el = item.find(tag)
                if el is not None and el.text:
                    loc = el.text.strip()
                    break
            results.append({
                'company': company,
                'role': title,
                'location': loc,
                'url': url,
                'source': 'indeed',
            })
        return results
    except Exception as e:
        print(f'  [indeed] {region}: {e}', file=sys.stderr)
        return []


def fetch_linkedin(search_params: dict) -> list:
    try:
        params = {
            'keywords': search_params['keywords'],
            'location': search_params.get('location', ''),
            'f_E': '1',     # Entry level
            'f_JT': 'I',    # Internship job type
            'sortBy': 'DD', # Date descending
            'start': '0',
        }
        if 'f_WT' in search_params:
            params['f_WT'] = search_params['f_WT']

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.linkedin.com/jobs/',
        }
        base = 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?'
        resp = SESSION.get(base + urlencode(params), timeout=15, headers=headers)
        if resp.status_code != 200:
            return []

        html = resp.text
        results = []

        # Extract job IDs and metadata via regex
        id_pat      = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
        title_pat   = re.compile(r'class="base-search-card__title"[^>]*>\s*([^<]+)', re.DOTALL)
        company_pat = re.compile(r'class="base-search-card__subtitle"[^>]*>(?:\s*<[^>]+>)*\s*([^<\n]+)', re.DOTALL)
        loc_pat     = re.compile(r'class="job-search-card__location"[^>]*>\s*([^<\n]+)', re.DOTALL)

        job_ids   = id_pat.findall(html)
        titles    = [t.strip() for t in title_pat.findall(html)]
        companies = [c.strip() for c in company_pat.findall(html)]
        locations = [l.strip() for l in loc_pat.findall(html)]

        for i, job_id in enumerate(job_ids):
            title   = titles[i]   if i < len(titles)    else ''
            company = companies[i] if i < len(companies) else 'Unknown'
            loc     = locations[i] if i < len(locations) else search_params.get('location', '')

            if not is_internship(title):
                continue
            if not is_mn_or_remote(loc):
                continue

            results.append({
                'company': company,
                'role': title,
                'location': loc,
                'url': f'https://www.linkedin.com/jobs/view/{job_id}',
                'source': 'linkedin',
            })

        return results
    except Exception as e:
        print(f'  [linkedin] {search_params["keywords"]}: {e}', file=sys.stderr)
        return []


# ── Dedup & Normalize ──────────────────────────────────────────────────────────

def dedup(jobs: list) -> list:
    seen = set()
    result = []
    for j in jobs:
        key = j['url'].split('?')[0].rstrip('/')
        if key not in seen:
            seen.add(key)
            result.append(j)
    return result


def normalize(j: dict) -> dict:
    return {
        'company':  j.get('company', 'Unknown').strip(),
        'role':     j.get('role', 'Unknown').strip(),
        'location': j.get('location', '').strip(),
        'url':      j.get('url', '').strip(),
        'applied':  False,
        'source':   j.get('source', ''),
        'scanned':  datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def log(msg: str):
    print(msg)
    sys.stdout.flush()


def scan(verbose=True) -> list:
    all_jobs = []
    total_sources = len(GREENHOUSE_SLUGS) + len(ASHBY_SLUGS) + len(LEVER_SLUGS)

    log(f'[scan] MN & Remote Internship Scanner starting...')
    log(f'[scan] Checking {len(GREENHOUSE_SLUGS)} Greenhouse + {len(ASHBY_SLUGS)} Ashby + {len(LEVER_SLUGS)} Lever companies')
    log(f'[scan] + {len(INDEED_FEEDS)} Indeed feeds + {len(LINKEDIN_SEARCHES)} LinkedIn searches')

    # Greenhouse
    log('[scan] Greenhouse API...')
    for slug in GREENHOUSE_SLUGS:
        jobs = fetch_greenhouse(slug)
        if jobs:
            log(f'  + greenhouse/{slug}: {len(jobs)} intern listings')
        all_jobs.extend(jobs)
        time.sleep(0.08)

    # Ashby
    log('[scan] Ashby API...')
    for slug in ASHBY_SLUGS:
        jobs = fetch_ashby(slug)
        if jobs:
            log(f'  + ashby/{slug}: {len(jobs)} intern listings')
        all_jobs.extend(jobs)
        time.sleep(0.08)

    # Lever
    log('[scan] Lever API...')
    for slug in LEVER_SLUGS:
        jobs = fetch_lever(slug)
        if jobs:
            log(f'  + lever/{slug}: {len(jobs)} intern listings')
        all_jobs.extend(jobs)
        time.sleep(0.08)

    # Indeed RSS
    log('[scan] Indeed RSS...')
    for feed_url, region in INDEED_FEEDS:
        jobs = fetch_indeed(feed_url, region)
        if jobs:
            log(f'  + indeed/{region}: {len(jobs)} listings')
        all_jobs.extend(jobs)
        time.sleep(0.4)

    # LinkedIn
    log('[scan] LinkedIn guest API...')
    for params in LINKEDIN_SEARCHES:
        jobs = fetch_linkedin(params)
        if jobs:
            log(f'  + linkedin "{params["keywords"]}": {len(jobs)} listings')
        all_jobs.extend(jobs)
        time.sleep(1.2)

    # Normalize, dedup, sort
    all_jobs = [normalize(j) for j in all_jobs if j.get('url')]
    all_jobs = dedup(all_jobs)
    all_jobs.sort(key=lambda j: (
        0 if is_internship(j['role']) else 1,
        j.get('company', '').lower()
    ))

    log(f'[scan] Done — {len(all_jobs)} unique MN/Remote internships found.')

    with open(JOBS_OUTPUT, 'w') as f:
        json.dump(all_jobs, f, indent=2)
    log(f'[scan] Written to {JOBS_OUTPUT}')

    return all_jobs


if __name__ == '__main__':
    jobs = scan()
    print(f'\n{"─"*70}')
    print(f'Total: {len(jobs)} internships')
    print(f'{"─"*70}')
    for j in jobs[:15]:
        src = j.get("source","")[:10].ljust(10)
        print(f"  [{src}] {j['company'][:28]:28s} | {j['role'][:38]:38s} | {j['location']}")
    if len(jobs) > 15:
        print(f'  ... and {len(jobs)-15} more')
