// Records the GIFs and screenshots of the TUI docs page (wiki/features/tui.mdx).
// Usage: just docs-tui-media [name ...] [--theme=light|dark]
//
// For every tape in tapes/ and both themes (light = Catppuccin Latte, dark = Catppuccin Mocha) it
//   1. runs `vhs` on the tape against a throwaway copy of the golden fixture, in an isolated HOME / XDG setup,
//   2. derives the key timeline from the tape (timeline.mjs) and draws each pressed key as a box at the bottom right,
//   3. writes site/public/media/tui/<name>.<theme>.gif and <name>-<shot>.<theme>.png.
// The overlay is ffmpeg `overlay` fed by box images from ImageMagick: this ffmpeg has no drawtext, and vhs has no key overlay.
// Needs: vhs, ffmpeg, ffprobe, magick (all Homebrew), go/bin/okf (just go-build). Never touches the user config, the live
// catalogue or the real clipboard: the tape shell gets a PATH that holds only a fake herdr and a few tools (no pbcopy).
import { execFileSync, spawnSync } from 'node:child_process';
import { chmodSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { intervals, parseTape, stillLabels } from './timeline.mjs';

const repo = fileURLToPath(new URL('../../', import.meta.url));
const okf = join(repo, 'go/bin/okf');
const fixture = join(repo, 'tests/golden/catalogue');
const tapeDir = fileURLToPath(new URL('./tapes/', import.meta.url));
const outDir = join(repo, 'site/public/media/tui');
// A fixed, short work path: the TUI header shows the catalogue root, and it should read well in the GIFs.
const work = join(realpathSync('/tmp'), 'okf-tui-media'); // the TUI shows the resolved path: /private/tmp on macOS
const THEMES = {
	light: { vhs: 'Catppuccin Latte', tui: 'latte', bg: '#e6e9eef2', edge: '#7287fd', text: '#4c4f69' },
	dark: { vhs: 'Catppuccin Mocha', tui: 'mocha', bg: '#181825f2', edge: '#b4befe', text: '#cdd6f4' },
};
const FPS = 25; // frame rate of the vhs recording
const SIZE = { width: 1200, height: 700 };
const CANVAS = { w: 900, h: 56, margin: 14 }; // key overlay area, right-aligned at the bottom

const only = process.argv.slice(2).find((a) => a.startsWith('--theme='))?.slice(8);
const names = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const sh = (cmd, args, opts = {}) => execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'], ...opts });
for (const tool of ['vhs', 'ffmpeg', 'ffprobe', 'magick']) {
	if (spawnSync('which', [tool]).status !== 0) throw new Error(`${tool} not found (brew install ${tool === 'ffprobe' ? 'ffmpeg' : tool})`);
}
if (!existsSync(okf)) throw new Error('go/bin/okf is missing: run just go-build');
const font = process.env.OKF_MEDIA_FONT || sh('fc-match', ['-f', '%{file}', 'JetBrains Mono:bold']);

// ---- throwaway environment -------------------------------------------------------------------------------------------
rmSync(work, { recursive: true, force: true });
for (const d of ['state', 'bin', 'shots', 'boxes', 'seq']) mkdirSync(join(work, d), { recursive: true });
for (const d of [join(work, 'kc'), join(work, 'kc-bare')]) cpSync(fixture, d, { recursive: true });
const isolated = { PATH: process.env.PATH, HOME: work };
sh(okf, ['--root', join(work, 'kc'), 'build-index'], { env: isolated });
// kc-bare keeps no index: the index tape builds it live.
if (process.env.VOYAGE_API_KEY) sh(okf, ['--root', join(work, 'kc'), 'build-semantic-index'], { env: { ...isolated, VOYAGE_API_KEY: process.env.VOYAGE_API_KEY } });
else console.warn('VOYAGE_API_KEY is not set: semantic index skipped, the semantic dot stays grey and find runs lexical only');

// The shell of every tape sees only these tools: no pbcopy/wl-copy (real clipboard), no real herdr, no editor.
symlinkSync(okf, join(work, 'bin/okf'));
for (const tool of ['clear', 'cat']) symlinkSync(sh('which', [tool]).trim(), join(work, 'bin', tool));
writeFileSync(join(work, 'agents.json'), JSON.stringify({ id: 'x', result: { type: 'agent_list', agents: [
	{ agent: 'claude', agent_status: 'idle', pane_id: 'wA:p2', workspace_id: 'wA', cwd: join(work, 'kc'), terminal_title_stripped: 'write the release notes' },
	{ agent: 'omp', agent_status: 'working', pane_id: 'wA:p3', workspace_id: 'wA', cwd: join(work, 'kc'), terminal_title_stripped: 'review the runbooks' },
	{ agent: 'omp', agent_status: 'blocked', pane_id: 'wA:p4', workspace_id: 'wA', cwd: '/srv/other', terminal_title_stripped: 'waits for approval' },
] } }));
writeFileSync(join(work, 'bin/herdr'), `#!/bin/sh
# Fake herdr of the media run: the pane under the popup runs no agent, three agents are listed, send-text is recorded.
case "$1 $2" in
"pane get") echo '{"id":"x","result":{"pane":{"pane_id":"wA:p1","workspace_id":"wA"},"type":"pane_info"}}' ;;
"agent list") cat ${work}/agents.json ;;
"pane send-text") printf '%s\\n' "$4" > ${work}/sent.md; echo '{"id":"x","result":{}}' ;;
*) echo '{"id":"x","result":{}}' ;;
esac
`);
chmodSync(join(work, 'bin/herdr'), 0o755);
for (const [name, t] of Object.entries(THEMES)) {
	mkdirSync(join(work, `cfg-${name}/okf`), { recursive: true });
	writeFileSync(join(work, `cfg-${name}/okf/config.toml`), `[tui]\ntheme = "${t.tui}"\n\n[tui.tracker]\nkind = "file"\nfile = "${work}/tasks.md"\n`);
}

// ---- tapes -----------------------------------------------------------------------------------------------------------
// A tape body may start with `# cwd: <dir under the work dir>` (default kc: okf tui finds the catalogue above it).
function compose(body, theme, name) {
	const t = THEMES[theme];
	const cwd = /^# cwd: (\S+)/m.exec(body)?.[1] ?? 'kc';
	const env = [
		'unset NO_COLOR VISUAL EDITOR HERDR_PANE_ID', 'export CLICOLOR_FORCE=1 COLORTERM=truecolor PS1="$ "',
		`export PATH=${work}/bin HOME=${work} XDG_CONFIG_HOME=${work}/cfg-${theme} XDG_STATE_HOME=${work}/state`,
		'export HERDR_ACTIVE_PANE_ID=wA:p1', `cd ${work}/${cwd}`, 'clear',
	].join('; ');
	const shots = (s) => s.replace(/^Screenshot\s+(\S+)\s*$/gm, (_, n) => `Screenshot "${work}/shots/${name}-${n}.${theme}.png"`);
	return `Output "${work}/${name}.${theme}.mp4"
Set Shell bash
Set Width ${SIZE.width}
Set Height ${SIZE.height}
Set FontSize 14
Set FontFamily "JetBrains Mono"
Set Theme "${t.vhs}"
Set Padding 10
Set Framerate ${FPS}
Set TypingSpeed 0
Hide
Type \`${env}\` Enter
Sleep 300ms
Set TypingSpeed 110ms
Show
${shots(body)}`;
}

// ---- overlay ---------------------------------------------------------------------------------------------------------
function box(label, theme) {
	const t = THEMES[theme];
	const file = join(work, 'boxes', `${theme}-${Buffer.from(label).toString('hex')}.png`);
	if (existsSync(file)) return file;
	const text = (label.trim() ? label : 'space').replace(/%/g, '%%').replace(/^@/, '\\@');
	sh('magick', ['-background', 'none', '-font', font, '-pointsize', '19', '-fill', t.text, `label:${text}`, '-bordercolor', 'none', '-border', '14x9', file]);
	const [w, h] = sh('magick', ['identify', '-format', '%w %h', file]).split(' ').map(Number);
	sh('magick', ['-size', `${w}x${h}`, 'xc:none', '-fill', t.bg, '-stroke', t.edge, '-strokewidth', '2', '-draw', `roundrectangle 1,1,${w - 2},${h - 2},9,9`, file, '-composite', file]);
	return file;
}
const canvas = (labels, theme, out) => {
	if (labels.length === 0) return sh('magick', ['-size', `${CANVAS.w}x${CANVAS.h}`, 'xc:none', `PNG32:${out}`]);
	const parts = labels.flatMap((l, i) => (i ? ['(', '-size', '10x1', 'xc:none', ')', box(l, theme)] : [box(l, theme)]));
	sh('magick', [...parts, '-background', 'none', '-gravity', 'center', '+append', '-gravity', 'east', '-extent', `${CANVAS.w}x${CANVAS.h}`, `PNG32:${out}`]);
};
const position = `x=W-w-${CANVAS.margin}:y=H-h-${CANVAS.margin}`;

function record(name, theme) {
	const tape = compose(readFileSync(join(tapeDir, `${name}.tape`), 'utf8'), theme, name);
	const tapeFile = join(work, `${name}.${theme}.tape`);
	writeFileSync(tapeFile, tape);
	rmSync(join(work, 'tasks.md'), { force: true });
	rmSync(join(work, 'sent.md'), { force: true });
	// vhs inherits this environment; the shell of the tape resets what matters (see compose). VOYAGE_API_KEY passes through.
	sh('vhs', [tapeFile], { stdio: ['ignore', 'ignore', 'inherit'] });

	const parsed = parseTape(tape);
	const mp4 = join(work, `${name}.${theme}.mp4`);
	const real = parseFloat(sh('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', mp4]));
	const scale = real / parsed.duration;
	console.log(`${name}.${theme}: tape ${parsed.duration.toFixed(1)}s, video ${real.toFixed(1)}s, scale ${scale.toFixed(3)}`);

	// One overlay image per video frame (symlinks to the box image of the interval): the concat demuxer of ffmpeg drops
	// short images, a numbered sequence at the frame rate of the recording does not.
	const seq = join(work, 'seq', `${name}.${theme}`);
	mkdirSync(seq, { recursive: true });
	const ivs = intervals(parsed, scale).map((iv, i) => {
		const png = join(work, 'boxes', `${name}.${theme}.${i}.png`);
		canvas(iv.labels, theme, png);
		return { ...iv, png };
	});
	const frames = Math.ceil(real * FPS);
	for (let f = 0; f < frames; f++) {
		const at = (f + 0.5) / FPS;
		symlinkSync((ivs.find((iv) => at >= iv.from && at < iv.to) ?? ivs.at(-1)).png, join(seq, `${String(f).padStart(5, '0')}.png`));
	}
	const gif = join(outDir, `${name}.${theme}.gif`);
	sh('ffmpeg', ['-y', '-v', 'error', '-i', mp4, '-framerate', String(FPS), '-i', join(seq, '%05d.png'), '-filter_complex',
		`[1:v]format=rgba[k];[0:v][k]overlay=${position}:eof_action=pass,fps=12.5,scale=1000:-1:flags=lanczos,split[a][b];` +
		'[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle', gif]);

	for (const still of parsed.stills) {
		const shot = basename(still.name);
		const png = join(work, 'boxes', `${shot}`);
		canvas(stillLabels(parsed, still.t), theme, png);
		sh('ffmpeg', ['-y', '-v', 'error', '-i', still.name, '-i', png, '-filter_complex', `[0:v][1:v]overlay=${position}`, join(outDir, shot)]);
	}
}

mkdirSync(outDir, { recursive: true });
const tapes = readdirSync(tapeDir).filter((f) => f.endsWith('.tape')).map((f) => f.replace(/\.tape$/, '')).filter((n) => !names.length || names.includes(n));
if (!tapes.length) throw new Error(`no tape matches ${names.join(', ')}`);
for (const name of tapes) for (const theme of Object.keys(THEMES).filter((t) => !only || t === only)) record(name, theme);
console.log(`\nmedia in ${outDir}:`);
console.log(readdirSync(outDir).sort().join('\n'));
