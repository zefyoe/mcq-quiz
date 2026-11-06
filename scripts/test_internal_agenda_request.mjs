// Exercise the shared request timeout/error handling without a browser or network.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../static/internal_agenda.js', import.meta.url), 'utf8');
const element = {addEventListener() {}, querySelectorAll() { return []; }};
function client(fetch, immediateTimeout = false) {
  const scope = {window:{addEventListener() {}}, document:{currentScript:{dataset:{}}, addEventListener() {},
    querySelector() { return element; }, querySelectorAll() { return []; }, getElementById() { return element; }},
    fetch, AbortController, Error, TypeError,
    setTimeout: immediateTimeout ? fn => { queueMicrotask(fn); return 1; } : setTimeout,
    clearTimeout: immediateTimeout ? () => {} : clearTimeout};
  vm.runInNewContext(source, scope);
  return scope.window.internalAgenda.request;
}
function response(status, body, type = 'application/json', redirected = false) {
  return {ok:status>=200 && status<300, status, redirected,
    headers:{get:name => name === 'Content-Type' ? type : ''}, json:async () => body,
    blob:async () => new Blob(['pdf'],{type})};
}
assert.equal((await client(async () => response(200,{ok:true,revision:2}))('/test')).revision, 2);
await assert.rejects(client(async () => response(409,{error:'Version modifiée'}))('/test'), /Version modifiée/);
await assert.rejects(client(async () => response(200,{},'text/html',true))('/test'), /session a expiré/);
await assert.rejects(client(async () => response(503,{},'text/html'))('/test'), /données restent/);
await assert.rejects(client(async () => { throw new TypeError('offline'); })('/test'), /Connexion interrompue/);
const timeout = client((url,{signal}) => new Promise((resolve,reject) => {
  signal.addEventListener('abort', () => { const error = new Error('aborted'); error.name='AbortError'; reject(error); });
}), true);
await assert.rejects(timeout('/test'), /texte reste ici/);
assert.ok((await client(async () => response(200,{},'application/pdf'))('/pdf',{},'pdf')).blob instanceof Blob);
console.log('PASS: JSON, conflict, expired session, server failure, offline, timeout and PDF response handling.');
