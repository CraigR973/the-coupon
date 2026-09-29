import { api } from './lib.mjs';
const r = await api('/api/v1/leagues/the-coupon/gameweek/current', { persona: 'Carol' });
const s = r.json;
console.log(r.status, Object.keys(s));
for (const f of s.fixtures) {
  console.log(f.fixture_id, f.home, 'v', f.away, f.competition, Object.keys(f).join(','));
  for (const x of f.selections) console.log('   ', JSON.stringify(x));
}
