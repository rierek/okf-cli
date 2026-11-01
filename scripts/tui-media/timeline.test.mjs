// Run: node --test scripts/tui-media/
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { intervals, parseTape, stillLabels } from './timeline.mjs';

const tape = `
Set TypingSpeed 100ms
Hide
Type "setup" Enter
Sleep 9s
Show
Type "ab"
Sleep 1s
Ctrl+K
Down@200ms 2
Screenshot "x.png"
Sleep 3s
`;

test('hidden time does not count, typed text grows per character', () => {
	const p = parseTape(tape);
	assert.equal(p.slots[0].start, 0);
	assert.deepEqual(p.slots[0].labels.map((l) => l.text), ['a', 'ab']);
	assert.equal(p.slots[1].labels[0].text, 'ctrl+k');
	assert.ok(Math.abs(p.slots[1].start - 1.2) < 1e-9); // 2 chars * 100ms + 1s
	assert.deepEqual(p.slots.slice(2).map((s) => s.labels[0].text), ['↓', '↓']);
	assert.ok(Math.abs(p.slots[3].start - p.slots[2].start - 0.2) < 1e-9);
	assert.equal(p.stills[0].name, 'x.png');
	assert.deepEqual(stillLabels(p, p.stills[0].t), ['↓']);
});

test('intervals cover the video, newest boxes last', () => {
	const p = parseTape(tape);
	const iv = intervals(p);
	assert.equal(iv[0].from, 0);
	assert.ok(Math.abs(iv.at(-1).to - p.duration) < 1e-9);
	assert.deepEqual(iv[0].labels, ['a']);
	assert.deepEqual(iv[1].labels, ['ab']);
	const both = iv.find((i) => i.labels.length === 2);
	assert.deepEqual(both.labels, ['ctrl+k', '↓']);
});
