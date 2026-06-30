"""
scan_jobs.py - MIS job scanner: Greenhouse + Lever, US-wide.
Merges with existing jobs.json so no data is lost.
"""
import json, urllib.request, time, os
from datetime import datetime, timezone

TODAY = datetime.now(timezone.utc).isoformat()
HERE  = os.path.dirname(os.path.abspath(__file__))
OUT   = os.path.join(HERE, "jobs.json")

MIS_INCLUDE = [
    'analyst','analytics','data','database','sql','bi ','business intelligence',
    'reporting','business anal','information system','information technology',
    'systems analyst','management information',' mis ','mis intern',
    'erp','crm','enterprise resource','enterprise application',
    'it analyst','it intern','it specialist','it support','it operations',
    'technology analyst','technology intern','digital transformation',
    'systems integration','technical analyst',
    'operations analyst','process analyst','operations intern',
    'supply chain analyst','logistics analyst','project analyst',
    'program analyst','planning analyst','pricing analyst',
    'risk analyst','compliance analyst','audit intern','it audit',
    'quality analyst','solutions analyst','functional analyst',
    'financial analyst','finance analyst','revenue operations',
    'sales operations','customer success','treasury analyst',
    'technology consulting','management consulting','it consulting',
    'implementation','consultant intern',
    'data science','data engineer','data intern','machine learning',
    'ai analyst','cloud analyst','product analyst','research analyst',
    'market research','insights analyst','intelligence analyst',
    'workforce analyst','hr analyst','people analytics',
    'strategy analyst','growth analyst','technical program',
    'project management intern','business operations',
]
MIS_EXCLUDE = [
    'software engineer','software developer',
    'frontend developer','front-end developer','front end developer',
    'backend developer','back-end developer','back end developer',
    'full stack','fullstack','full-stack',
    'devops','site reliability','sre ',
    'network engineer','cloud engineer','infrastructure engineer',
    'mobile developer','ios developer','android developer',
    'embedded','firmware','hardware engineer',
    'mechanical engineer','civil engineer','electrical engineer',
    'graphic designer','game developer','game designer',
    'pharmacist','nursing','dental','physical therapy',
    'attorney','paralegal','journalist','copywriter','social worker',
    'security engineer','penetration test',
]

def is_mis(title):
    t = title.lower()
    if any(k in t for k in MIS_EXCLUDE): return False
    return any(k in t for k in MIS_INCLUDE)

def fetch(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', errors='replace'))
    except Exception:
        return None

# ── Verified Greenhouse board IDs ─────────────────────────────────────────────
GREENHOUSE = [
    # Analytics / Data
    ("amplitude",    "Amplitude"),
    ("braze",        "Braze"),
    ("klaviyo",      "Klaviyo"),
    ("fivetran",     "Fivetran"),
    ("hightouch",    "Hightouch"),
    ("mode",         "Mode Analytics"),
    ("inovalon",     "Inovalon"),
    # Finance / Fintech
    ("brex",         "Brex"),
    ("carta",        "Carta"),
    ("chime",        "Chime"),
    ("justworks",    "Justworks"),
    ("marqeta",      "Marqeta"),
    ("lattice",      "Lattice"),
    ("gusto",        "Gusto"),
    # Consulting / IT Services
    ("thoughtworks", "Thoughtworks"),
    ("rackner",      "Rackner"),
    # Enterprise / SaaS
    ("asana",        "Asana"),
    ("smartsheet",   "Smartsheet"),
    ("intercom",     "Intercom"),
    ("cloudflare",   "Cloudflare"),
    ("twilio",       "Twilio"),
    ("stripe",       "Stripe"),
    ("databricks",   "Databricks"),
    ("samsara",      "Samsara"),
    ("toast",        "Toast"),
    ("procore",      "Procore"),
    ("project44",    "project44"),
    ("flexport",     "Flexport"),
    # Healthcare IT
    ("inovalon",     "Inovalon"),
    # MN / Midwest
    ("jamf",         "Jamf"),
    ("doublegood",   "Double Good"),
]

# ── Lever company slugs ───────────────────────────────────────────────────────
LEVER = [
    ("voltus",       "Voltus"),
    ("palantir",     "Palantir"),
    ("mixpanel",     "Mixpanel"),
    ("segment",      "Segment"),
    ("rippling",     "Rippling"),
    ("miro",         "Miro"),
    ("loom",         "Loom"),
    ("affirm",       "Affirm"),
    ("robinhood",    "Robinhood"),
    ("coinbase",     "Coinbase"),
    ("heap",         "Heap Analytics"),
    ("fullstory",    "FullStory"),
    ("contentsquare","Contentsquare"),
    ("procore",      "Procore"),
    ("shipbob",      "ShipBob"),
    ("leidos",       "Leidos"),
    ("saic",         "SAIC"),
    ("slalom",       "Slalom"),
    ("guidehouse",   "Guidehouse"),
    ("dbtlabs",      "dbt Labs"),
    ("airbyte",      "Airbyte"),
    ("snowflake",    "Snowflake"),
    ("confluent",    "Confluent"),
    ("rubrik",       "Rubrik"),
    ("zendesk",      "Zendesk"),
    ("freshworks",   "Freshworks"),
    ("typeform",     "Typeform"),
    ("notion",       "Notion"),
    ("clickup",      "ClickUp"),
    ("airtable",     "Airtable"),
    ("webflow",      "Webflow"),
    ("canva",        "Canva"),
    ("gusto",        "Gusto"),
    ("carta",        "Carta"),
    ("navan",        "Navan"),
    ("ramp",         "Ramp"),
    ("samsara",      "Samsara"),
    ("veeva",        "Veeva Systems"),
    ("workiva",      "Workiva"),
    ("amplitude",    "Amplitude"),
    ("braze",        "Braze"),
    ("klaviyo",      "Klaviyo"),
]

def scan_greenhouse():
    results = []
    done = set()
    for board_id, co in GREENHOUSE:
        if board_id in done: continue
        done.add(board_id)
        data = fetch(f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs")
        if not data: continue
        n = 0
        for j in data.get('jobs', []):
            title = j.get('title','')
            if not is_mis(title): continue
            loc = j.get('location',{}).get('name','') or 'United States'
            url = j.get('absolute_url','')
            if not url: continue
            results.append({"company":co,"role":title,"location":loc,"url":url,"source":"greenhouse","scanned":TODAY})
            n += 1
        if n: print(f"  Greenhouse {co}: {n}")
        time.sleep(0.15)
    return results

def scan_lever():
    results = []
    done = set()
    for slug, co in LEVER:
        if slug in done: continue
        done.add(slug)
        data = fetch(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if not data or not isinstance(data, list): continue
        n = 0
        for j in data:
            title = j.get('text','')
            if not is_mis(title): continue
            cats = j.get('categories',{})
            loc = cats.get('location','') or cats.get('commitment','') or 'United States'
            url = j.get('hostedUrl','')
            if not url: continue
            results.append({"company":co,"role":title,"location":loc,"url":url,"source":"lever","scanned":TODAY})
            n += 1
        if n: print(f"  Lever {co}: {n}")
        time.sleep(0.15)
    return results

def merge(existing, new_jobs):
    urls = {j.get('url','') for j in existing if j.get('url')}
    added = 0
    for j in new_jobs:
        if j.get('url') and j['url'] not in urls:
            existing.append(j)
            urls.add(j['url'])
            added += 1
    return existing, added

if __name__ == "__main__":
    print(f"=== MIS Scanner {TODAY[:10]} ===")

    existing = []
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding='utf-8') as f:
                existing = json.load(f)
            print(f"Loaded {len(existing)} existing jobs")
        except Exception:
            pass

    print("\nGreenhouse:")
    gh = scan_greenhouse()
    print(f"  Total MIS found: {len(gh)}")

    print("\nLever:")
    lv = scan_lever()
    print(f"  Total MIS found: {len(lv)}")

    merged, added = merge(existing, gh + lv)
    print(f"\nAdded {added} new jobs. Total: {len(merged)}")

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"Saved to {OUT}")
