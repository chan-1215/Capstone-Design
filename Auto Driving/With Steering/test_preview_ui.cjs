const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup(hidden = false) {
  const documentEvents = {}, windowEvents = {}, requests = [];
  let source = '/stream/processed';
  const video = {
    getAttribute(name) { assert.equal(name, 'src'); return source; },
    removeAttribute(name) { assert.equal(name, 'src'); source = null; },
    set src(value) { source = value; requests.push(value); },
    get src() { return source; }
  };
  const document = {
    hidden, getElementById(id) { assert.equal(id, 'video'); return video; },
    addEventListener(type, callback) { documentEvents[type] = callback; }
  };
  const window = {addEventListener(type, callback) { windowEvents[type] = callback; }};
  const context = {window, document, fetch() { throw Error('Preview must never send robot commands'); }};
  vm.runInNewContext(fs.readFileSync('static/preview.js', 'utf8'), context);
  return {window, document, video, requests, documentEvents, windowEvents};
}

let s = setup();
assert.equal(s.requests.length, 0, 'Initial src must not open a duplicate connection');
s.window.trackPreview.select('raw');
assert.deepEqual(s.requests, ['/stream/raw']);
s.window.trackPreview.select('raw');
assert.equal(s.requests.length, 1, 'Reselecting the same tab must reuse its stream');
s.document.hidden = true;
s.documentEvents.visibilitychange();
assert.equal(s.video.src, null, 'Hidden tabs must close their image connection');
s.window.trackPreview.select('yellow');
s.window.trackPreview.reconnect();
assert.equal(s.video.src, null, 'Recovery must not reopen a hidden connection');
s.document.hidden = false;
s.documentEvents.visibilitychange();
assert.equal(s.video.src, '/stream/yellow', 'Resume the selected view, not a stale view');
assert.equal(s.requests.length, 2);
s.windowEvents.pagehide();
assert.equal(s.video.src, null);
s.windowEvents.pageshow();
assert.equal(s.video.src, '/stream/yellow');
s.window.trackPreview.reconnect();
assert.equal(s.requests.length, 4, 'Explicit visible recovery should reconnect');
s = setup(true);
assert.equal(s.video.src, null, 'A hidden initial page must not retain the HTML stream');
assert.equal(s.requests.length, 0);
console.log('Preview visibility, view selection, recovery and no-control contracts passed');
