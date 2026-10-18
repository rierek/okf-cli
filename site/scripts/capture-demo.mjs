// Captures real okf output for the home page: runs the built binary against copies of the golden fixture catalogue and
// writes src/data/demo.json (HTML with Catppuccin tones, see custom.css). Usage: just docs-capture (needs go/bin/okf).
// The semantic capture calls the Voyage embedding API with the fixture text: it needs VOYAGE_API_KEY. Without the key
// the previous semantic capture in demo.json stays.
import { execFileSync, spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const okf = root + 'go/bin/okf';
const fixture = root + 'tests/golden/catalogue';
const dataFile = new URL('../src/data/demo.json', import.meta.url);
const work = realpathSync(mkdtempSync(join(tmpdir(), 'okf-demo-')));
const home = join(work, 'home');
mkdirSync(home);
// Copies keep the fixture in the repo untouched: the index builds write .fts/ and .tagvec/ into the catalogue.
const lexical = join(work, 'lexical'); // FTS index only: find runs the lexical arm alone
const semantic = join(work, 'semantic'); // FTS index plus embeddings: find runs both arms
for (const dir of [lexical, semantic]) cpSync(fixture, dir, { recursive: true });

const baseEnv = { PATH: process.env.PATH, HOME: home, COLUMNS: '80', NO_COLOR: '1' };
const key = process.env.VOYAGE_API_KEY;
// Host paths never reach the page: every catalogue root prints as ~/kc.
const hide = (text, ...roots) => roots.reduce((t, r) => t.split(r).join('~/kc'), text);
const run = (cat, args, { notes = false, env = baseEnv } = {}) => {
	const r = spawnSync(okf, ['--root', cat, ...args], { env, encoding: 'utf8' });
	// Notes (a skipped or leading arm) go to stderr, before the results.
	return hide((notes ? r.stderr : '') + r.stdout, cat);
};
const quote = (a) => (/[\s~]/.test(a) ? `'${a}'` : a);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const span = (tone, s, extra = '') => `<span style="color:var(--ctp-${tone})${extra}">${s}</span>`;
// Tone rules: first column keys and paths get an accent, notes are dim. Output stays the captured text.
const tint = (text) => text.split('\n').map((l) => {
	if (/^(rank|slug|status|path):/.test(l)) return l.replace(/^(\w+:)(.*)$/, (_, k, v) => span('overlay1', esc(k)) + esc(v));
	if (/^(note|warning):/.test(l)) return span('overlay1', esc(l));
	if (/^\s*\d+\s/.test(l)) return esc(l).replace(/(\S+\.md)/, (m) => span('sapphire', m));
	if (/^(ok|OK)\b/.test(l)) return span('green', esc(l));
	if (/\.md\b/.test(l)) return esc(l).replace(/(\/?[\w./-]+\.md)/, (m) => span('sapphire', m));
	return esc(l);
}).join('\n').replace(/\n+$/, '');
const shot = (args, text, keep) => ({ command: 'okf ' + args.map(quote).join(' '), html: tint(text.split('\n').slice(0, keep).join('\n')) });

const out = existsSync(dataFile) ? JSON.parse(readFileSync(dataFile, 'utf8')) : {};
try {
	// Catalogue-wide jobs run on the fixture itself (read-only commands).
	const plain = (args, keep) => shot(args, run(fixture, args), keep);
	out.ctx = plain(['ctx', 'show', 'onboarding'], 9);
	out.check = plain(['check'], 6);
	out.rename = plain(['rename', 'recipes/soup.md', 'recipes/broth.md'], 12);

	execFileSync(okf, ['--root', lexical, 'build-index'], { env: baseEnv });
	execFileSync(okf, ['--root', semantic, 'build-index'], { env: baseEnv });

	// Two arms: the same query on a lexical-only catalogue and on one with embeddings.
	const q = ['find', 'kneading and proofing', '--limit', '2'];
	out.words = shot(q, run(lexical, q, { notes: true }), 20);
	if (key) {
		const env = { ...baseEnv, VOYAGE_API_KEY: key };
		execFileSync(okf, ['--root', semantic, 'build-semantic-index'], { env });
		out.meaning = shot(q, run(semantic, q, { notes: true, env }), 20);
	} else if (!out.meaning) throw new Error('VOYAGE_API_KEY is not set and demo.json has no semantic capture');
	else console.warn('VOYAGE_API_KEY not set: kept the previous semantic capture');

	// Two scopes: the whole catalogue, then one bundle through --where.
	const all = ['find', 'overview', '--limit', '2'];
	const one = ['find', 'overview', '--where', 'path ~ recipes/', '--limit', '2'];
	out.scopeAll = shot(all, run(lexical, all), 18);
	out.scopeOne = shot(one, run(lexical, one), 18);
} finally {
	rmSync(work, { recursive: true, force: true });
}
delete out.find;
out.generated = { date: new Date().toISOString().slice(0, 10) };
mkdirSync(new URL('../src/data/', import.meta.url), { recursive: true });
writeFileSync(dataFile, JSON.stringify(out, null, 1) + '\n');
console.log('captured', Object.keys(out).join(', '));
