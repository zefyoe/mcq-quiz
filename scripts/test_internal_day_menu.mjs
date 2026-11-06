import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const events = new Map();
const makeMenu = () => ({open:false, matches: selector => selector === '.day-menu',
  removeAttribute() { this.open = false; }});
const first = makeMenu(), second = makeMenu();
const element = {hidden:true, addEventListener() {}, querySelectorAll() { return []; }};
const document = {currentScript:{dataset:{}},
  addEventListener(name, callback) { events.set(name,[...(events.get(name)||[]),callback]); },
  querySelector() { return element; }, getElementById() { return element; },
  querySelectorAll(selector) { return selector === '.day-menu[open]' ? [first,second].filter(m=>m.open) : []; }};
vm.runInNewContext(fs.readFileSync(new URL('../static/internal_agenda.js',import.meta.url),'utf8'),
  {document,window:{addEventListener() {}},AbortController,setTimeout,clearTimeout,Error,TypeError});
first.open = second.open = true;
for (const handler of events.get('toggle')) handler({target:second});
assert.equal(first.open,false); assert.equal(second.open,true);
const target = menu => ({closest: selector => selector === '.day-menu' ? menu : null});
for (const handler of events.get('click')) await handler({target:target(first)});
assert.equal(second.open,false);
first.open = true;
for (const handler of events.get('click')) await handler({target:target(null)});
assert.equal(first.open,false);
second.open = true;
for (const handler of events.get('keydown')) handler({key:'Escape'});
assert.equal(second.open,false);
console.log('PASS: exclusive day menus, switching dates, outside click and Escape dismissal.');
