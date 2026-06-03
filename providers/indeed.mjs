// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// Indeed provider — fetches jobs via the public RSS feed.
// Set careers_url to an indeed.com/rss search URL.
// Example: https://www.indeed.com/rss?q=MIS+intern&l=Minneapolis%2C+MN&sort=date

function stripHtml(str) {
  return str.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/&quot;/g, '"').trim();
}

function extractCdata(tag, xml) {
  const m = xml.match(new RegExp(`<${tag}><!\\[CDATA\\[([\\s\\S]*?)\\]\\]><\\/${tag}>`));
  if (m) return m[1].trim();
  const m2 = xml.match(new RegExp(`<${tag}>([^<]*)<\\/${tag}>`));
  return m2 ? stripHtml(m2[1]) : '';
}

/** @type {Provider} */
export default {
  id: 'indeed',

  detect(entry) {
    const url = entry.careers_url || '';
    if (url.includes('indeed.com')) return { url };
    return null;
  },

  async fetch(entry, ctx) {
    const url = entry.api || entry.careers_url;
    if (!url) throw new Error('indeed: no careers_url configured');

    const xml = await ctx.fetchText(url, {
      headers: { Accept: 'application/rss+xml, application/xml, text/xml, */*' },
    });

    const jobs = [];
    const itemRegex = /<item>([\s\S]*?)<\/item>/g;
    let match;

    while ((match = itemRegex.exec(xml)) !== null) {
      const item = match[1];

      // Indeed RSS title format: "Job Title - Company Name"
      const rawTitle = extractCdata('title', item);
      const dashIdx = rawTitle.lastIndexOf(' - ');
      const title   = dashIdx !== -1 ? rawTitle.slice(0, dashIdx).trim() : rawTitle;
      const company = dashIdx !== -1 ? rawTitle.slice(dashIdx + 3).trim() : (extractCdata('source', item) || entry.name);

      const link = extractCdata('link', item) || (() => {
        const m2 = item.match(/<link>([^<]+)<\/link>/);
        return m2 ? m2[1].trim() : '';
      })();

      const city    = extractCdata('indeed:city', item);
      const state   = extractCdata('indeed:state', item);
      const location = [city, state].filter(Boolean).join(', ');

      if (title && link) {
        jobs.push({ title, url: link, company, location });
      }
    }

    return jobs;
  },
};
