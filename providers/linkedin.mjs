// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// LinkedIn provider — hits the public guest jobs API (no auth required).
// Set careers_url to a linkedin.com/jobs/search/ URL with ?keywords= and &location= params.
// Example: https://www.linkedin.com/jobs/search/?keywords=MIS+intern&location=Minneapolis

function buildGuestApiUrl(careersUrl) {
  let keywords = '', location = '';
  try {
    const u = new URL(careersUrl);
    keywords = u.searchParams.get('keywords') || '';
    location = u.searchParams.get('location') || '';
  } catch {
    throw new Error(`linkedin: invalid careers_url: ${careersUrl}`);
  }
  if (!keywords) throw new Error('linkedin: careers_url must include ?keywords=...');
  const base = 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search';
  return `${base}?keywords=${encodeURIComponent(keywords)}&location=${encodeURIComponent(location)}&start=0&count=25`;
}

function stripHtml(str) {
  return str.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"').trim();
}

/** @type {Provider} */
export default {
  id: 'linkedin',

  detect(entry) {
    const url = entry.careers_url || '';
    if (url.includes('linkedin.com/jobs')) return { url };
    return null;
  },

  async fetch(entry, ctx) {
    const apiUrl = buildGuestApiUrl(entry.careers_url || '');
    const html = await ctx.fetchText(apiUrl, {
      headers: {
        Accept: 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
      },
    });

    const jobs = [];
    // Each job is a <li> block containing a base-card div
    const liRegex = /<li>([\s\S]*?)<\/li>/g;
    let match;

    while ((match = liRegex.exec(html)) !== null) {
      const li = match[1];

      // Canonical job view link
      const linkMatch = li.match(/href="(https:\/\/www\.linkedin\.com\/jobs\/view\/[^"?]+)/);
      if (!linkMatch) continue;
      const url = linkMatch[1];

      const titleMatch = li.match(/class="[^"]*base-search-card__title[^"]*"[^>]*>([\s\S]*?)<\/h3>/);
      const companyMatch = li.match(/class="[^"]*base-search-card__subtitle[^"]*"[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)<\/a>/);
      const locationMatch = li.match(/class="[^"]*job-search-card__location[^"]*"[^>]*>([\s\S]*?)<\/span>/);

      const title    = titleMatch    ? stripHtml(titleMatch[1])    : '';
      const company  = companyMatch  ? stripHtml(companyMatch[1])  : '';
      const location = locationMatch ? stripHtml(locationMatch[1]) : '';

      if (title && url) {
        jobs.push({ title, url, company, location });
      }
    }

    return jobs;
  },
};
