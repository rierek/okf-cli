// Captures real okf output for the home page: runs the built binary against the golden fixture catalogue and writes
// src/data/demo.json (HTML with Catppuccin tones, see custom.css). Usage: just docs-capture (needs go/bin/okf).
import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const okf = root + 'go/bin/okf';
const cat = root + 'tests/golden/catalogue';
const env = { PATH: process.env.PATH, HOME: '/tmp/okf-docs-capture-home', COLUMNS: '80', NO_COLOR: '1' };
// Host paths never reach the page: the fixture root prints as ~/kc.
const run = (...args) => {
	let out;
	try { out = execFileSync(okf, ['--root', cat, ...args], { env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }); }
	catch (e) { out = e.stdout ?? ''; }
	return out.split(cat).join('~/kc');
};
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

// [arguments, number of output lines kept]
const cmds = {
	find: [['find', 'recipe'], 14],
	ctx: [['ctx', 'show', 'onboarding'], 9],
	check: [['check'], 6],
	rename: [['rename', 'recipes/soup.md', 'recipes/broth.md'], 12],
};
const out = {};
for (const [k, [args, keep]] of Object.entries(cmds)) out[k] = { command: 'okf ' + args.join(' '), html: tint(run(...args).split('\n').slice(0, keep).join('\n')) };
out.generated = { date: new Date().toISOString().slice(0, 10) };
mkdirSync(new URL('../src/data/', import.meta.url), { recursive: true });
writeFileSync(new URL('../src/data/demo.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('captured', Object.keys(cmds).join(', '));
