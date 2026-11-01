// Key timeline of a vhs tape: when each visible key press happens, relative to the start of the recording.
// vhs sleeps after every key press (TypingSpeed, or the @time of the command) and after every typed character;
// Sleep adds its own time; Hide ... Show frames are not in the video. The result drives the key overlay (build.mjs).
// ponytail: times come from the tape, not from the recorder. build.mjs scales them to the real video length.

export const HOLD = 1.0; // seconds a key box stays after the last press of its group
const MAX_BOXES = 3;

const KEYS = {
	enter: 'enter', tab: 'tab', space: 'space', backspace: 'backspace', escape: 'esc', up: '↑', down: '↓', left: '←',
	right: '→', pageup: 'pgup', pagedown: 'pgdn', delete: 'del', home: 'home', end: 'end',
};

export function seconds(text) {
	const m = /^([\d.]+)(ms|s|m)?$/.exec(text);
	if (!m) throw new Error(`bad duration: ${text}`);
	return parseFloat(m[1]) * { ms: 0.001, s: 1, m: 60, undefined: 1 }[m[2]];
}

// "Shift+Tab" -> "shift+tab", "Ctrl+K" -> "ctrl+k", "Down" -> "↓"
function keyLabel(name) {
	return name.split('+').map((p) => KEYS[p.toLowerCase()] ?? p.toLowerCase()).join('+');
}

// Returns { slots, stills, duration }. A slot is one key or one Type string: { start, end, labels: [{ t, text }] },
// a typed string grows one character at a time, so the box follows the typing.
export function parseTape(source) {
	const slots = [];
	const stills = [];
	let t = 0;
	let visible = true;
	let speed = 0.05; // vhs default TypingSpeed
	for (const raw of source.split('\n')) {
		const line = raw.trim();
		if (!line || line.startsWith('#')) continue;
		const [, cmd, at, rest] = /^([A-Za-z+]+)(?:@(\S+))?\s*(.*)$/.exec(line);
		const lower = cmd.toLowerCase();
		if (lower === 'hide') visible = false;
		else if (lower === 'show') visible = true;
		else if (lower === 'set') {
			const m = /^TypingSpeed\s+(\S+)/.exec(rest);
			if (m) speed = seconds(m[1]);
		} else if (!visible) continue;
		else if (lower === 'sleep') t += seconds(rest);
		else if (lower === 'screenshot') stills.push({ t, name: rest.replace(/^"|"$/g, '') });
		else if (lower === 'type') {
			const text = JSON.parse(rest);
			const step = at ? seconds(at) : speed;
			const slot = { start: t, end: 0, labels: [] };
			[...text].forEach((_, i) => {
				slot.labels.push({ t: t + i * step, text: [...text].slice(0, i + 1).join('') });
			});
			t += [...text].length * step;
			slot.end = t - step + HOLD;
			slots.push(slot);
		} else if (/^(enter|tab|space|backspace|escape|up|down|left|right|pageup|pagedown|delete|home|end)$/.test(lower)
			|| /^(ctrl|alt|shift)\+/.test(lower)) {
			const step = at ? seconds(at) : speed;
			const count = rest ? parseInt(rest, 10) : 1;
			for (let i = 0; i < count; i++) {
				slots.push({ start: t, end: t + HOLD, labels: [{ t, text: keyLabel(cmd) }] });
				t += step;
			}
		}
	}
	return { slots, stills, duration: t };
}

const labelAt = (slot, t) => slot.labels.findLast((l) => l.t <= t)?.text;

// Intervals of constant overlay content: [{ from, to, labels: [text, ...] }], oldest box first, at most MAX_BOXES.
export function intervals({ slots, duration }, scale = 1) {
	const sc = slots.map((s) => ({ ...s, start: s.start * scale, end: s.end * scale, labels: s.labels.map((l) => ({ ...l, t: l.t * scale })) }));
	const end = duration * scale;
	const cuts = new Set([0, end]);
	for (const s of sc) {
		cuts.add(s.start);
		cuts.add(Math.min(s.end, end));
		s.labels.forEach((l) => cuts.add(l.t));
	}
	const pts = [...cuts].filter((x) => x >= 0 && x <= end).sort((a, b) => a - b);
	const out = [];
	for (let i = 0; i + 1 < pts.length; i++) {
		const [from, to] = [pts[i], pts[i + 1]];
		if (to - from < 1e-6) continue;
		const labels = sc.filter((s) => s.start <= from + 1e-9 && from < s.end - 1e-9).slice(-MAX_BOXES)
			.map((s) => labelAt(s, from));
		out.push({ from, to, labels });
	}
	return out;
}

// The key that led to a still: the label of the last key group before time t, however long ago.
export function stillLabels({ slots }, t) {
	const last = slots.filter((s) => s.start <= t).slice(-1)[0];
	return last ? [labelAt(last, t)] : [];
}
