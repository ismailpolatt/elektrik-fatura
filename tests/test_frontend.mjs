import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../static/index.html', import.meta.url), 'utf8');
const inline = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]);
for (const script of inline) new vm.Script(script);
const utilities = html.slice(html.indexOf('    function parseTurkishNumber('), html.indexOf('    function formatTL('));
const context = vm.createContext({ window: { innerHeight: 900, addEventListener() {} },
  document: { documentElement: { style: { setProperty() {} } } }, setTimeout, clearTimeout,
  AbortController, Date });
vm.runInContext(utilities, context);
for (const [text, expected] of [['878.350', 878.35], ['24883,827', 24883.827], ['1.500,75', 1500.75],
  ['1,500.75', 1500.75], ['1.500.000', 1500000], ['-10', -10]]) {
  assert.equal(context.parseTurkishNumber(text), expected, text);
}
for (const text of ['12abc34', '1,2,3', '1.2.3', '1..2', '', true, Infinity, NaN]) {
  assert.ok(Number.isNaN(context.parseTurkishNumber(text)), String(text));
}
console.log('Ön yüz sözdizimi ve 15 sayı biçimi kontrolü geçti.');
