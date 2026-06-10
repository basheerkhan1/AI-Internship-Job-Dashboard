#!/usr/bin/env python3
"""
scan_jobs.py — MN + Remote Internship Scanner (MIS / Business Analytics focus)
Sources: Greenhouse, Ashby, Lever, Workday, SimplyHired, LinkedIn
Uses ThreadPoolExecutor to run API calls in parallel — much faster.
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

JOBS_OUTPUT = "jobs.json"

# ── Internship filter — word boundary, no false matches on "internal/international" ──
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
    'minnesota','minneapolis','st. paul','saint paul','twin cities',
    'eden prairie','bloomington, mn','maple grove','burnsville','woodbury',
    'brooklyn park','eagan','lakeville','apple valley',', mn',' mn,',' mn ',
    'minnetonka','richfield','st paul','maplewood','roseville','golden valley',
    'plymouth, mn','shoreview','wayzata','arden hills','inver grove',
    'shakopee','brooklyn center','fridley','mendota','blaine','medina, mn',
    'bayport','duluth, mn','stillwater, mn','owatonna','mankato','rochester, mn',
    'coon rapids','andover, mn','cottage grove','south st. paul',
]
REMOTE_TERMS = [
    'remote','work from home','wfh','distributed','anywhere in the us',
    'us remote','remote us','remote - us','remote (us)','remote, us',
    'remote united states','fully remote','telecommute','virtual',
    'remote / hybrid','hybrid remote','remote first',
    'united states','usa','u.s.','flex','flexible location',
    'hybrid','nationwide','anywhere in us','us-based','work anywhere',
]
BLOCK_TERMS = [
    'india','bengaluru','hyderabad','pune','mumbai','united kingdom','london',
    'germany','berlin','munich','france','paris','spain','netherlands',
    'amsterdam','singapore','japan','tokyo','brazil','australia','sydney',
    'philippines','poland','warsaw',
]
def is_mn_or_remote(loc: str) -> bool:
    if not loc: return True
    l = loc.lower()
    if any(b in l for b in BLOCK_TERMS): return False
    return any(t in l for t in MN_TERMS) or any(t in l for t in REMOTE_TERMS)

# ── MIS relevance filter — keeps tech/data/business roles, drops unrelated ───
_NON_MIS_RE = re.compile(
    r'\b(pharmac|clinical\s|nursing|medical\s+lab|dental|'
    r'physical\s+therapy|occupational\s+therapy|'
    r'attorney|paralegal|law\s+clerk|legal\s+assistant|'
    r'graphic\s+design|illustration|visual\s+arts?|animation\s+|'
    r'journalist|public\s+relations|copywriter|editorial\s+intern|'
    r'civil\s+engineer|mechanical\s+engineer|structural\s+engineer|'
    r'construction\s+intern|landscap|horticultur|agricultur|'
    r'social\s+worker|counselor|therapist|'
    r'retail\s+store|store\s+manag|cashier|'
    r'content\s+creation|social\s+media|'
    r'human\s+resources\s+intern|hr\s+intern(?!\s*(technology|information|systems|tech))|'
    r'sales\s+intern(?!\s*(analytics|technology|operations|enablement))|'
    r'marketing\s+intern(?!\s*(analytics|data|digital|technology))|'
    r'manufacturing\s+engineer\w*|traffic\s+engineer\w*|'
    r'mechanical\s+engineer\w*|civil\s+engineer\w*|structural\s+engineer\w*|'
    r'seasonal\s+(engineer\w*|labor|traffic)|warehouse\s+associate|'
    r'ministry|chaplain|spiritual|game\s+artist|'
    r'respiratory|biology\s+research|life\s+science\s+intern|'
    r'internship\s+in\s+marketing(?!\s*(analytics|data|digital)))\b',
    re.IGNORECASE
)
def is_mis_relevant(title: str) -> bool:
    return not bool(_NON_MIS_RE.search(title or ''))

def _now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def log(msg): print(msg, flush=True)

def _job(company, role, location, url, source):
    return {
        'company':  (company or '').strip(),
        'role':     (role or '').strip(),
        'location': (location or '').strip(),
        'url':      (url or '').strip(),
        'applied':  False,
        'source':   source,
        'scanned':  _now(),
    }

# ── HTTP session ──────────────────────────────────────────────────────────────
def make_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
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

# ── Greenhouse ────────────────────────────────────────────────────────────────
GREENHOUSE_SLUGS = [
    # MN companies
    'generalmills','landolakes','jamf','arcticwolfnetworks','spscommerce',
    'digitalriver','healthcatalyst','cariboucoffee','securian','cargill',
    'andersencorporation','chsinc','donaldson','graco','bestbuy','target',
    'polaris','sleepnumber','allianzlife',
    # Analytics / MIS (remote-friendly)
    'amplitude','mixpanel','heap','fullstory','alteryx','databricks',
    'dbtlabs','fivetran','confluent','elastic','datadog','hashicorp',
    'starburst','dremio','thoughtspot','sigma','matillion','montecarlodata',
    'atlan','stripe','brex','rippling','gusto','lattice','carta','mercury',
    'pilot','ramp','hubspot','klaviyo','gong','outreach','salesloft','clari',
    'hightouch','rackner','doublegood','cohere','anthropic','scaleai',
    'intercom','postman','pagerduty','splunk','cloudflare','zendesk',
    'freshworks','drift','notion','figma','airtable','zapier','miro',
    'cockroachlabs','airbyte','prefect','astronomer',
    # IT / cybersecurity / support (remote-friendly)
    'crowdstrike','sentinelone','lacework','snyk','wiz',
    'qualys','tenable','rapid7','huntress','abnormalsecurity',
    'knowbe4','proofpoint','sailpoint','beyondtrust','cyberark',
    'okta','auth0','onelogin','ping','duo',
    'servicenow','freshservice','jira','atlassian',
    'msp-anywhere','connectwise','n-able','kaseya',
    # MN IT companies
    'atomicdata','sps-commerce','stellent','entrust','code42',
]

def fetch_greenhouse(slug):
    try:
        r = SESSION.get(f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs', timeout=10)
        if r.status_code != 200: return []
        data = r.json()
        name = (data.get('company') or {}).get('name') or slug.title()
        out  = []
        for j in (data.get('jobs') or []):
            title = j.get('title','')
            if not is_internship(title): continue
            offices = j.get('offices') or []
            loc = ', '.join(o.get('name','') for o in offices if o.get('name'))
            if not loc:
                loc = (j.get('location') or {}).get('name','') if isinstance(j.get('location'),dict) else ''
            if not is_mn_or_remote(loc): continue
            url = j.get('absolute_url','')
            if url: out.append(_job(name, title, loc or 'Remote', url, 'greenhouse'))
        return out
    except: return []

# ── Ashby ─────────────────────────────────────────────────────────────────────
ASHBY_SLUGS = [
    'm13','resend','claylabs','legora','decagon','perplexityai','anysphere',
    'hex','baseten','vanta','watershed','retool','lightdash','motherduck',
    'evidence','hyperquery','cortex','hatchet','fireworks','together','comet',
    'whylabs','gretel','modal','prefect','astronomer','census','chargebee',
    'linear','loom','notion','craft','coda',
]
def fetch_ashby(slug):
    try:
        r = SESSION.get(f'https://api.ashbyhq.com/posting-api/job-board/{slug}', timeout=10)
        if r.status_code != 200: return []
        data = r.json()
        name = (data.get('organization') or {}).get('name') or slug.title()
        out  = []
        for j in (data.get('jobPostings') or []):
            title = j.get('title','')
            if not is_internship(title): continue
            loc = j.get('location') or j.get('locationName') or ''
            if not is_mn_or_remote(loc): continue
            url = j.get('jobUrl') or j.get('applyUrl') or ''
            if url: out.append(_job(name, title, loc or 'Remote', url, 'ashby'))
        return out
    except: return []

# ── Lever ─────────────────────────────────────────────────────────────────────
LEVER_SLUGS = [
    'voltus','grammarly','coursera','duolingo','reddit','pinterest','carta',
    'plaid','chime','robinhood','box','dropbox','postman','springhealth',
    'cerebral','quora','mparticle','surveymonkey','zendesk','intercom',
    'driftt','lob','heap','figma',
]
def fetch_lever(slug):
    try:
        r = SESSION.get(f'https://api.lever.co/v0/postings/{slug}?mode=json&limit=500', timeout=10)
        if r.status_code != 200: return []
        out = []
        for j in (r.json() or []):
            title = j.get('text','')
            if not is_internship(title): continue
            cats = j.get('categories') or {}
            locs = cats.get('allLocations') or []
            loc  = locs[0] if locs else cats.get('location','')
            if not is_mn_or_remote(loc): continue
            url = j.get('hostedUrl') or j.get('applyUrl') or ''
            company = j.get('company') or slug.title()
            if url: out.append(_job(company, title, loc or 'Remote', url, 'lever'))
        return out
    except: return []

# ── Workday (major MN employers) ──────────────────────────────────────────────
WORKDAY_COMPANIES = [
    ('Target',           'target',          'wd5', 'targetcareers'),
    ('Best Buy',         'bestbuy',         'wd5', 'bestbuy_careers'),
    ('Medtronic',        'medtronic',       'wd1', 'medtronic_careers'),
    ('US Bank',          'usbank',          'wd5', 'US_Bank_Careers'),
    ('3M',               '3m',              'wd1', '3M'),
    ('Ameriprise',       'ameriprise',      'wd5', 'ameriprise_careers'),
    ('Piper Sandler',    'pipersandler',    'wd501','Piper_Sandler_Careers'),
    ('Allianz Life',     'allianzlife',     'wd3', 'Allianz_External_Careers'),
    ('Polaris',          'polarisinc',      'wd5', 'Polaris_Careers'),
    ('Toro Company',     'thetorocompany',  'wd5', 'thetorocompany'),
    ('Andersen Windows', 'andersenwindows', 'wd5', 'Andersen_External_Careers'),
    ('Sleep Number',     'sleepnumber',     'wd5', 'sleepnumber_careers'),
    ('Wells Fargo',      'wellsfargo',      'wd5', 'Wells_Fargo_External'),
    ('UnitedHealth',     'uhg',             'wd5', 'corporateUHC'),
    ('Optum',            'uhg',             'wd5', 'Optum'),
    ('Ecolab',           'ecolab',          'wd5', 'ecolab_careers'),
    ('Xcel Energy',      'xcelenergy',      'wd5', 'XcelEnergy'),
    ('CHS Inc.',         'chsinc',          'wd5', 'CHS'),
    ('Digi International','digiintl',       'wd5', 'DigiInternational'),
    ('SurModics',        'surmodics',       'wd5', 'SurModics'),
    ('Graco',            'graco',           'wd5', 'Graco_ExternalJobs'),
    ('H.B. Fuller',      'hbfuller',        'wd5', 'HBFuller'),
    ('Donaldson',        'donaldson',       'wd5', 'Donaldson'),
    ('Deluxe Corp',      'deluxecorp',      'wd5', 'deluxe_careers'),
    ('Securian',         'securian',        'wd5', 'SecurianFinancial'),
    # IT / tech companies in MN on Workday
    ('Mayo Clinic',      'mayo-clinic',     'wd5', 'MayoClinicExt'),
    ('Hennepin County',  'hennepin',        'wd5', 'HennepinCounty'),
    ('State of MN',      'minnjobs',        'wd5', 'minnjobs'),
    ('Fastenal',         'fastenal',        'wd5', 'Fastenal'),
    ('Tennant Company',  'tennantco',       'wd5', 'Tennant'),
    ('Entrust',          'entrust',         'wd5', 'Entrust'),
    # Big 4 + Consulting — top ISM intern hirers
    ('Deloitte',         'deloitte',        'wd5', 'Deloitte_Careers'),
    ('PwC',              'pwc',             'wd3', 'Global_Campus_Hiring'),
    ('KPMG',             'kpmg',            'wd5', 'KPMG_Careers'),
    ('Accenture',        'accenture',       'wd103','Accenture_Careers'),
    ('Capgemini',        'capgemini',       'wd3', 'Capgemini'),
    ('CGI',              'cgi',             'wd5', 'CGI'),
    ('Booz Allen',       'bah',             'wd1', 'BAH'),
    ('Leidos',           'leidos',          'wd5', 'Leidos'),
    ('ManTech',          'mantech',         'wd5', 'ManTech'),
    # Financial services ISM roles
    ('JPMorgan Chase',   'jpmorganchase',   'wd5', 'jpmorganchase'),
    ('Thomson Reuters',  'thomsonreuters',  'wd5', 'tr_external'),
    ('Ameritas',         'ameritas',        'wd5', 'Ameritas'),
    ('Nationwide',       'nationwide',      'wd5', 'nationwide-ext'),
    # MN healthcare IT
    ('Allina Health',    'allinahealth',    'wd5', 'Allina_Health_Careers'),
    ('HealthPartners',   'healthpartners',  'wd5', 'HealthPartners'),
    ('Prime Therapeutics','primetherapeutics','wd5','PrimeTherapeutics'),
]
def fetch_workday(display_name, tenant, wd_host, career_path):
    api = f'https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{career_path}/jobs'
    try:
        r = SESSION.post(api,
            json={'appliedFacets':{},'limit':20,'offset':0,'searchText':'intern'},
            headers={'Content-Type':'application/json','X-Calypso-CSRF-Token':'1'},
            timeout=12)
        if r.status_code not in (200,201): return []
        out = []
        for j in (r.json().get('jobPostings') or []):
            title = j.get('title','')
            if not is_internship(title): continue
            loc = j.get('locationsText') or ''
            if isinstance(loc, list): loc = ', '.join(loc)
            if not is_mn_or_remote(loc): continue
            ext = j.get('externalPath') or ''
            url = f'https://{tenant}.{wd_host}.myworkdayjobs.com/{career_path}{ext}' if ext else api
            out.append(_job(display_name, title, loc or 'Minnesota', url, 'workday'))
        return out
    except: return []

# ── SimplyHired RSS ───────────────────────────────────────────────────────────
SIMPLYHIRED_FEEDS = [
    # Analytics / MIS — MN
    ('data analyst internship',        'Minnesota'),
    ('business analyst intern',        'Minnesota'),
    ('MIS intern',                     'Minnesota'),
    ('information systems intern',     'Minnesota'),
    ('data analytics internship',      'Minnesota'),
    ('business intelligence intern',   'Minnesota'),
    # IT roles — MN
    ('IT intern',                      'Minnesota'),
    ('help desk intern',               'Minnesota'),
    ('cybersecurity intern',           'Minnesota'),
    ('software developer intern',      'Minnesota'),
    ('technical support intern',       'Minnesota'),
    ('network intern',                 'Minnesota'),
    # Remote
    ('data analyst internship',        'Remote'),
    ('business analyst intern',        'Remote'),
    ('IT intern',                      'Remote'),
    ('cybersecurity intern',           'Remote'),
    ('software developer intern',      'Remote'),
]
def fetch_simplyhired(query, location):
    try:
        params = {'q': query, 'l': location, 'job_type': 'intern', 'output': 'rss'}
        r = SESSION.get('https://www.simplyhired.com/search', params=params,
                        headers={'Accept':'application/rss+xml,*/*'}, timeout=12)
        if r.status_code != 200: return []
        root = ET.fromstring(r.content)
        out  = []
        for item in root.findall('.//item'):
            title_el = item.find('title')
            link_el  = item.find('link')
            if title_el is None or link_el is None: continue
            title = (title_el.text or '').strip()
            url   = (link_el.text or '').strip()
            if not is_internship(title): continue
            # Try to get company/location
            company = ''
            for tag in ['{http://www.simplyHired.com/about/rss}Company', 'source']:
                el = item.find(tag)
                if el is not None and el.text:
                    company = el.text.strip(); break
            loc = location
            for tag in ['{http://www.simplyHired.com/about/rss}Location']:
                el = item.find(tag)
                if el is not None and el.text:
                    loc = el.text.strip(); break
            if not is_mn_or_remote(loc): continue
            out.append(_job(company or 'Unknown', title, loc, url, 'simplyhired'))
        return out
    except: return []

# ── Google Jobs (via search JSON-LD) ─────────────────────────────────────────
GOOGLE_SEARCHES = [
    # Analytics / MIS
    'data analyst internship Minnesota 2026',
    'business analyst internship Minneapolis MN',
    'MIS internship Minnesota',
    'information systems intern Minnesota',
    'business intelligence internship Minnesota',
    'data analytics intern remote 2026',
    'operations analyst internship Minnesota',
    # IT roles
    'IT intern Minnesota 2026',
    'cybersecurity internship Minnesota',
    'help desk intern Minneapolis MN',
    'software developer internship Minnesota',
    'IT support intern Minnesota',
    'network intern Minnesota',
    'web developer intern Minnesota',
    'IT analyst internship remote 2026',
    'technical support intern remote United States',
]

def fetch_google_jobs(query: str) -> list:
    try:
        url = f'https://www.google.com/search?q={quote_plus(query)}&ibp=htl;jobs&hl=en'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        r = SESSION.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return []
        html = r.text
        # Extract JSON-LD job postings
        jsonld_re = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
        out = []
        for raw in jsonld_re.findall(html):
            try:
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict): continue
                    if item.get('@type') != 'JobPosting': continue
                    title = item.get('title', '')
                    if not is_internship(title): continue
                    org   = item.get('hiringOrganization') or {}
                    company = org.get('name', 'Unknown') if isinstance(org, dict) else 'Unknown'
                    loc_obj = item.get('jobLocation') or {}
                    if isinstance(loc_obj, list): loc_obj = loc_obj[0] if loc_obj else {}
                    addr = (loc_obj.get('address') or {}) if isinstance(loc_obj, dict) else {}
                    city  = addr.get('addressLocality', '') if isinstance(addr, dict) else ''
                    state = addr.get('addressRegion', '')   if isinstance(addr, dict) else ''
                    loc   = ', '.join(filter(None, [city, state]))
                    if not loc and 'remote' in query.lower():
                        loc = 'Remote'
                    if not is_mn_or_remote(loc): continue
                    job_url = item.get('url') or item.get('sameAs') or ''
                    if job_url:
                        out.append(_job(company, title, loc or 'Minnesota', job_url, 'google'))
            except Exception:
                pass
        return out
    except Exception:
        return []

# ── LinkedIn guest API ────────────────────────────────────────────────────────
LINKEDIN_SEARCHES = [
    # ── MN: Core MIS / Analytics ──
    {'keywords':'data analyst intern',              'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'business analyst intern',          'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'data analytics intern',            'location':'Minnesota, United States'},
    {'keywords':'MIS intern',                       'location':'Minnesota, United States'},
    {'keywords':'information systems intern',       'location':'Minnesota, United States'},
    {'keywords':'business intelligence intern',     'location':'Minnesota, United States'},
    {'keywords':'systems analyst intern',           'location':'Minnesota, United States'},
    {'keywords':'operations analyst intern',        'location':'Minnesota, United States'},
    {'keywords':'data science intern',              'location':'Minnesota, United States'},
    {'keywords':'analytics intern',                 'location':'Minnesota, United States'},
    {'keywords':'reporting analyst intern',         'location':'Minnesota, United States'},
    {'keywords':'process improvement intern',       'location':'Minnesota, United States'},
    {'keywords':'product analyst intern',           'location':'Minnesota, United States'},
    {'keywords':'ERP intern',                       'location':'Minnesota, United States'},
    {'keywords':'digital transformation intern',    'location':'Minnesota, United States'},
    # ── MN: IT / Software ──
    {'keywords':'IT intern',                        'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'technology intern',                'location':'Minneapolis, Minnesota, United States'},
    {'keywords':'software engineer intern',         'location':'Minnesota, United States'},
    {'keywords':'software developer intern',        'location':'Minnesota, United States'},
    {'keywords':'web developer intern',             'location':'Minnesota, United States'},
    {'keywords':'application developer intern',     'location':'Minnesota, United States'},
    {'keywords':'full stack intern',                'location':'Minnesota, United States'},
    {'keywords':'IT support intern',                'location':'Minnesota, United States'},
    {'keywords':'help desk intern',                 'location':'Minnesota, United States'},
    {'keywords':'technical support intern',         'location':'Minnesota, United States'},
    {'keywords':'cybersecurity intern',             'location':'Minnesota, United States'},
    {'keywords':'network intern',                   'location':'Minnesota, United States'},
    {'keywords':'cloud computing intern',           'location':'Minnesota, United States'},
    {'keywords':'database intern',                  'location':'Minnesota, United States'},
    {'keywords':'IT analyst intern',                'location':'Minnesota, United States'},
    {'keywords':'computer science intern',          'location':'Minnesota, United States'},
    {'keywords':'systems administrator intern',     'location':'Minnesota, United States'},
    {'keywords':'QA intern',                        'location':'Minnesota, United States'},
    {'keywords':'DevOps intern',                    'location':'Minnesota, United States'},
    # ── MN: Business / Finance (tech-adjacent) ──
    {'keywords':'financial analyst intern',         'location':'Minnesota, United States'},
    {'keywords':'finance technology intern',        'location':'Minnesota, United States'},
    {'keywords':'supply chain analytics intern',    'location':'Minnesota, United States'},
    {'keywords':'project management intern',        'location':'Minnesota, United States'},
    {'keywords':'product management intern',        'location':'Minnesota, United States'},
    {'keywords':'digital marketing analytics intern','location':'Minnesota, United States'},
    {'keywords':'marketing analytics intern',       'location':'Minnesota, United States'},
    {'keywords':'UX design intern',                 'location':'Minnesota, United States'},
    {'keywords':'IT consulting intern',             'location':'Minnesota, United States'},
    {'keywords':'technology consulting intern',     'location':'Minnesota, United States'},
    {'keywords':'risk analytics intern',            'location':'Minnesota, United States'},
    {'keywords':'IT audit intern',                  'location':'Minnesota, United States'},
    # ── Remote: Core MIS / Analytics ──
    {'keywords':'data analyst intern',              'location':'United States','f_WT':'2'},
    {'keywords':'business analyst intern',          'location':'United States','f_WT':'2'},
    {'keywords':'data analytics intern',            'location':'United States','f_WT':'2'},
    {'keywords':'business intelligence intern',     'location':'United States','f_WT':'2'},
    {'keywords':'MIS intern',                       'location':'United States','f_WT':'2'},
    {'keywords':'information systems intern',       'location':'United States','f_WT':'2'},
    {'keywords':'operations analyst intern',        'location':'United States','f_WT':'2'},
    {'keywords':'product analyst intern',           'location':'United States','f_WT':'2'},
    {'keywords':'data science intern',              'location':'United States','f_WT':'2'},
    {'keywords':'analytics intern',                 'location':'United States','f_WT':'2'},
    {'keywords':'reporting analyst intern',         'location':'United States','f_WT':'2'},
    {'keywords':'machine learning intern',          'location':'United States','f_WT':'2'},
    {'keywords':'AI intern',                        'location':'United States','f_WT':'2'},
    {'keywords':'Python analytics intern',          'location':'United States','f_WT':'2'},
    {'keywords':'Tableau intern',                   'location':'United States','f_WT':'2'},
    {'keywords':'Power BI intern',                  'location':'United States','f_WT':'2'},
    {'keywords':'SQL intern',                       'location':'United States','f_WT':'2'},
    # ── Remote: IT / Software ──
    {'keywords':'IT intern',                        'location':'United States','f_WT':'2'},
    {'keywords':'software engineer intern',         'location':'United States','f_WT':'2'},
    {'keywords':'software developer intern',        'location':'United States','f_WT':'2'},
    {'keywords':'web developer intern',             'location':'United States','f_WT':'2'},
    {'keywords':'full stack intern',                'location':'United States','f_WT':'2'},
    {'keywords':'cybersecurity intern',             'location':'United States','f_WT':'2'},
    {'keywords':'cloud intern',                     'location':'United States','f_WT':'2'},
    {'keywords':'IT support intern',                'location':'United States','f_WT':'2'},
    {'keywords':'technical support intern',         'location':'United States','f_WT':'2'},
    {'keywords':'help desk intern',                 'location':'United States','f_WT':'2'},
    {'keywords':'DevOps intern',                    'location':'United States','f_WT':'2'},
    {'keywords':'QA intern',                        'location':'United States','f_WT':'2'},
    # ── Remote: Business / Finance (tech-adjacent) ──
    {'keywords':'financial analyst intern',         'location':'United States','f_WT':'2'},
    {'keywords':'project management intern',        'location':'United States','f_WT':'2'},
    {'keywords':'product management intern',        'location':'United States','f_WT':'2'},
    {'keywords':'supply chain analytics intern',    'location':'United States','f_WT':'2'},
    {'keywords':'UX intern',                        'location':'United States','f_WT':'2'},
    {'keywords':'IT consulting intern',             'location':'United States','f_WT':'2'},
    {'keywords':'technology consulting intern',     'location':'United States','f_WT':'2'},
    {'keywords':'digital marketing analytics intern','location':'United States','f_WT':'2'},
    # ── MN: ISM / Management Information Systems ──
    {'keywords':'information systems management intern','location':'Minnesota, United States'},
    {'keywords':'management information systems intern','location':'Minnesota, United States'},
    {'keywords':'IT business analyst intern',       'location':'Minnesota, United States'},
    {'keywords':'business systems analyst intern',  'location':'Minnesota, United States'},
    {'keywords':'ERP intern',                       'location':'Minnesota, United States'},
    {'keywords':'SAP intern',                       'location':'Minnesota, United States'},
    {'keywords':'technology management intern',     'location':'Minnesota, United States'},
    {'keywords':'IT project management intern',     'location':'Minnesota, United States'},
    {'keywords':'enterprise systems intern',        'location':'Minnesota, United States'},
    {'keywords':'IT governance intern',             'location':'Minnesota, United States'},
    {'keywords':'systems integration intern',       'location':'Minnesota, United States'},
    {'keywords':'technology solutions intern',      'location':'Minnesota, United States'},
    {'keywords':'IS analyst intern',                'location':'Minnesota, United States'},
    {'keywords':'technology analyst intern',        'location':'Minnesota, United States'},
    {'keywords':'IT audit intern',                  'location':'Minnesota, United States'},
    {'keywords':'accounting information systems intern','location':'Minnesota, United States'},
    {'keywords':'business technology intern',       'location':'Minnesota, United States'},
    # ── Remote: ISM ──
    {'keywords':'information systems management intern','location':'United States','f_WT':'2'},
    {'keywords':'management information systems intern','location':'United States','f_WT':'2'},
    {'keywords':'IT business analyst intern',       'location':'United States','f_WT':'2'},
    {'keywords':'business systems analyst intern',  'location':'United States','f_WT':'2'},
    {'keywords':'ERP intern',                       'location':'United States','f_WT':'2'},
    {'keywords':'SAP intern',                       'location':'United States','f_WT':'2'},
    {'keywords':'technology management intern',     'location':'United States','f_WT':'2'},
    {'keywords':'IT project management intern',     'location':'United States','f_WT':'2'},
    {'keywords':'enterprise systems intern',        'location':'United States','f_WT':'2'},
    {'keywords':'systems integration intern',       'location':'United States','f_WT':'2'},
    {'keywords':'IT governance intern',             'location':'United States','f_WT':'2'},
    {'keywords':'technology analyst intern',        'location':'United States','f_WT':'2'},
    {'keywords':'IT audit intern',                  'location':'United States','f_WT':'2'},
    {'keywords':'accounting information systems intern','location':'United States','f_WT':'2'},
    {'keywords':'business technology intern',       'location':'United States','f_WT':'2'},
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
        if r.status_code == 999:   # LinkedIn anti-bot block — back off
            time.sleep(8)
            return []
        if r.status_code == 429:   # Rate limit — back off longer
            time.sleep(15)
            return []
        if r.status_code != 200: return []
        if len(r.text) < 200: return []  # Empty bot-detection response
        html = r.text
        id_pat  = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"')
        t_pat   = re.compile(r'class="base-search-card__title"[^>]*>\s*([^<]+)', re.DOTALL)
        co_pat  = re.compile(r'class="base-search-card__subtitle"[^>]*>(?:\s*<[^>]+>)*\s*([^<\n]+)', re.DOTALL)
        loc_pat = re.compile(r'class="job-search-card__location"[^>]*>\s*([^<\n]+)', re.DOTALL)
        jids  = id_pat.findall(html)
        titles = [t.strip() for t in t_pat.findall(html)]
        cos    = [c.strip() for c in co_pat.findall(html)]
        locs   = [l.strip() for l in loc_pat.findall(html)]
        out = []
        for i, jid in enumerate(jids):
            title = titles[i] if i < len(titles) else ''
            co    = cos[i]    if i < len(cos)    else 'Unknown'
            loc   = locs[i]   if i < len(locs)   else params.get('location','')
            if not is_internship(title): continue
            if not is_mn_or_remote(loc): continue
            out.append(_job(co, title, loc, f'https://www.linkedin.com/jobs/view/{jid}', 'linkedin'))
        return out
    except: return []

# ── Jobicy public API (free remote jobs, no auth) ─────────────────────────────
def fetch_jobicy():
    try:
        r = SESSION.get('https://jobicy.com/api/v2/remote-jobs?count=50&tag=intern',
                        timeout=12)
        if r.status_code != 200: return []
        out = []
        for j in (r.json().get('jobs') or []):
            title   = j.get('jobTitle', '')
            if not is_internship(title): continue
            if not is_mis_relevant(title): continue
            company = j.get('companyName', 'Unknown')
            loc     = j.get('jobGeo', 'Remote') or 'Remote'
            url     = j.get('url', '')
            if url: out.append(_job(company, title, loc, url, 'jobicy'))
        return out
    except: return []

# ── RemoteOK public API (no auth, always works on GitHub Actions) ─────────────
def fetch_remoteok():
    try:
        r = SESSION.get('https://remoteok.com/api?tags=intern',
                        headers={'Accept':'application/json','User-Agent':'Mozilla/5.0'}, timeout=15)
        if r.status_code != 200: return []
        out = []
        for j in (r.json() or []):
            if not isinstance(j, dict): continue
            title = j.get('position','')
            if not title: continue
            tags = ' '.join(j.get('tags') or []).lower()
            if not is_internship(title) and 'intern' not in tags: continue
            if not is_mis_relevant(title): continue
            company = j.get('company','Unknown')
            loc = j.get('location','') or 'Remote'
            if not is_mn_or_remote(loc): continue
            url = j.get('apply_url') or j.get('url','')
            if url: out.append(_job(company, title, loc, url, 'remoteok'))
        return out
    except: return []

# ── The Muse API (free, no auth, 20 results/page) ────────────────────────────
def fetch_muse(pages=12):
    out = []
    for page in range(pages):
        try:
            r = SESSION.get(
                f'https://www.themuse.com/api/public/jobs?level=Internship&page={page}&descending=true',
                timeout=12)
            if r.status_code != 200: break
            results = r.json().get('results', [])
            if not results: break
            for j in results:
                title = j.get('name', '')
                if not is_internship(title): continue
                if not is_mis_relevant(title): continue
                company = (j.get('company') or {}).get('name', 'Unknown')
                locs = j.get('locations') or []
                loc = ', '.join(l.get('name', '') for l in locs) or 'Flexible'
                if not is_mn_or_remote(loc): continue
                url = j.get('refs', {}).get('landing_page', '') or j.get('refs', {}).get('url', '')
                if url:
                    out.append(_job(company, title, loc or 'Remote', url, 'themuse'))
            time.sleep(0.3)
        except: break
    return out

# ── Dedup ─────────────────────────────────────────────────────────────────────
def dedup(jobs):
    seen = set(); out = []
    for j in jobs:
        key = (j['url'].split('?')[0].rstrip('/'))
        if key not in seen:
            seen.add(key); out.append(j)
    return out

# ── Main ──────────────────────────────────────────────────────────────────────
def scan():
    all_jobs = []

    log(f'[scan] MN + Remote Internship Scanner (parallel)')
    log(f'[scan] Greenhouse:{len(GREENHOUSE_SLUGS)} Ashby:{len(ASHBY_SLUGS)} '
        f'Lever:{len(LEVER_SLUGS)} Workday:{len(WORKDAY_COMPANIES)} '
        f'SimplyHired:{len(SIMPLYHIRED_FEEDS)} LinkedIn:{len(LINKEDIN_SEARCHES)}')
    log('')

    # Run Greenhouse + Ashby + Lever + Workday in parallel
    log('[scan] Running APIs in parallel...')
    futures = {}
    with ThreadPoolExecutor(max_workers=15) as ex:
        for slug in GREENHOUSE_SLUGS:
            futures[ex.submit(fetch_greenhouse, slug)] = f'greenhouse/{slug}'
        for slug in ASHBY_SLUGS:
            futures[ex.submit(fetch_ashby, slug)] = f'ashby/{slug}'
        for slug in LEVER_SLUGS:
            futures[ex.submit(fetch_lever, slug)] = f'lever/{slug}'
        for (name, tenant, host, path) in WORKDAY_COMPANIES:
            futures[ex.submit(fetch_workday, name, tenant, host, path)] = f'workday/{name}'

        for future in as_completed(futures):
            label = futures[future]
            jobs  = future.result()
            if jobs:
                log(f'  + {label}: {len(jobs)} internships')
            all_jobs.extend(jobs)

    log(f'[scan] API pass done — {len(all_jobs)} raw results so far')

    # Google Jobs
    log('[scan] Google Jobs...')
    for q in GOOGLE_SEARCHES:
        jobs = fetch_google_jobs(q)
        if jobs:
            log(f'  + Google Jobs "{q}": {len(jobs)}')
        all_jobs.extend(jobs)
        time.sleep(1.5)

    # SimplyHired RSS
    log('[scan] SimplyHired RSS...')
    for (query, location) in SIMPLYHIRED_FEEDS:
        jobs = fetch_simplyhired(query, location)
        if jobs:
            log(f'  + SimplyHired "{query}" / {location}: {len(jobs)}')
        all_jobs.extend(jobs)
        time.sleep(0.4)

    # Jobicy remote jobs API (free, no auth)
    log('[scan] Jobicy remote jobs...')
    jobicy_jobs = fetch_jobicy()
    if jobicy_jobs:
        log(f'  + Jobicy: {len(jobicy_jobs)} internships')
    all_jobs.extend(jobicy_jobs)

    # RemoteOK (free public API — reliable fallback)
    log('[scan] RemoteOK public API...')
    remoteok_jobs = fetch_remoteok()
    if remoteok_jobs:
        log(f'  + RemoteOK: {len(remoteok_jobs)} internships')
    all_jobs.extend(remoteok_jobs)

    # The Muse (free API, 12 pages = ~240 raw internships)
    log('[scan] The Muse API...')
    muse_jobs = fetch_muse(pages=12)
    if muse_jobs:
        log(f'  + The Muse: {len(muse_jobs)} internships')
    all_jobs.extend(muse_jobs)

    # LinkedIn (sequential — rate sensitive)
    log('[scan] LinkedIn guest API...')
    for params in LINKEDIN_SEARCHES:
        jobs = fetch_linkedin(params)
        loc_label = 'Remote' if params.get('f_WT') == '2' else params.get('location','')
        if jobs:
            log(f'  + LinkedIn "{params["keywords"]}" / {loc_label}: {len(jobs)}')
        all_jobs.extend(jobs)
        time.sleep(1.5)  # slightly longer — LinkedIn rate limits on GH Actions IPs

    # Merge with existing jobs.json so old results are never erased
    existing = []
    try:
        with open(JOBS_OUTPUT) as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # New scan results take precedence (fresher data), existing fills the gaps
    seen = {j['url'].split('?')[0].rstrip('/'): j for j in all_jobs}
    added = 0
    for j in existing:
        key = j['url'].split('?')[0].rstrip('/')
        if key not in seen:
            seen[key] = j
            added += 1

    all_jobs = list(seen.values())
    all_jobs = [j for j in all_jobs if is_mis_relevant(j.get('role',''))]
    all_jobs = dedup(all_jobs)
    all_jobs.sort(key=lambda j: (
        0 if is_internship(j['role']) else 1,
        (j.get('company') or '').lower()
    ))

    log(f'\n[scan] Done — {len(all_jobs)} unique internships ({added} kept from previous scan).')
    with open(JOBS_OUTPUT, 'w') as f:
        json.dump(all_jobs, f, indent=2)
    log(f'[scan] Saved to {JOBS_OUTPUT}')
    return all_jobs

if __name__ == '__main__':
    jobs = scan()
    mn  = sum(1 for j in jobs if any(t in (j['location']or'').lower() for t in MN_TERMS))
    rem = sum(1 for j in jobs if any(t in (j['location']or'').lower() for t in REMOTE_TERMS))
    print(f'\n  Total:{len(jobs)}  MN:{mn}  Remote:{rem}\n')
    for j in jobs[:25]:
        print(f'  [{j["source"]:10}] {(j["company"]or"")[:26]:26} | {(j["role"]or"")[:40]:40} | {j["location"]}')
    if len(jobs) > 25:
        print(f'  ...and {len(jobs)-25} more')
