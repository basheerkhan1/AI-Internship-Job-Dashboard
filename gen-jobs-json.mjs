#!/usr/bin/env node
import { readFileSync, writeFileSync, existsSync } from 'fs';

const PIPELINE_PATH = 'data/pipeline.md';
const OUT_PATH = 'jobs.json';

const jobs = [];

if (existsSync(PIPELINE_PATH)) {
  for (const line of readFileSync(PIPELINE_PATH, 'utf-8').split('\n')) {
    const m = line.match(/^-\s*\[([x ])\]\s*(https?:\/\/[^\s|]+)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$/);
    if (m) {
      const [, done, url, company, role] = m;
      jobs.push({ url: url.trim(), company: company.trim(), role: role.trim(), applied: done === 'x' });
    }
  }
}

writeFileSync(OUT_PATH, JSON.stringify(jobs, null, 2));
console.log(`Generated ${OUT_PATH} with ${jobs.length} jobs`);
