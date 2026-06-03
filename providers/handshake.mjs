// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// Handshake provider — hits the public student job search API.
// Note: full results require school login. Public/guest access returns
// a limited set of employer-published open listings.
//
// Set careers_url to: https://app.joinhandshake.com/stu/jobs
// Optional query params via the `api` field:
//   job.job_type_names[]=internship&job.remote_job_types[]=remote_only

function buildApiUrl(entry) {
  const base = 'https://app.joinhandshake.com/stu/jobs.json';
  const params = new URLSearchParams({
    page: '1',
    per_page: '25',
    sort_direction: 'desc',
    sort_column: 'core_job.created_at',
  });
  // Internship type always
  params.append('job.job_type_names[]', 'internship');
  // Allow override via api field
  if (entry.api) {
    try {
      const u = new URL(entry.api);
      u.searchParams.forEach((v, k) => params.set(k, v));
    } catch { /* ignore invalid api field */ }
  }
  return `${base}?${params}`;
}

/** @type {Provider} */
export default {
  id: 'handshake',

  detect(entry) {
    const url = entry.careers_url || '';
    if (url.includes('joinhandshake.com')) return { url };
    return null;
  },

  async fetch(entry, ctx) {
    const apiUrl = buildApiUrl(entry);
    let data;
    try {
      data = await ctx.fetchJson(apiUrl, {
        headers: {
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
    } catch (err) {
      // Auth-gated — Handshake requires school login for full results
      if (err.status === 401 || err.status === 403 || err.status === 302) {
        console.warn(`  ⚠️  handshake: login required — check ${entry.careers_url || 'joinhandshake.com'} manually`);
        return [];
      }
      throw err;
    }

    const results = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);
    return results.map(j => ({
      title: j.title || j.job_title || '',
      url: j.url || `https://app.joinhandshake.com/jobs/${j.id}`,
      company: j.employer_name || j.company?.name || entry.name,
      location: j.city ? `${j.city}, ${j.state || ''}`.trim() : (j.remote ? 'Remote' : ''),
    })).filter(j => j.title && j.url);
  },
};
