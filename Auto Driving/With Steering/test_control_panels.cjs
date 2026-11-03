const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const events = [], panels = {manual:{hidden:false}, auto:{hidden:true}};
function tab(name, selected) {
  const handlers = {}, attributes = {'aria-selected':String(selected)};
  return {dataset:{controlPanel:name}, tabIndex:selected?0:-1, handlers, attributes,
    addEventListener:(event, fn) => handlers[event] = fn,
    getAttribute:key => attributes[key], setAttribute:(key, value) => attributes[key] = value,
    focus() { this.focused = true; }};
}
const manual = tab('manual', true), auto = tab('auto', false);
vm.runInNewContext(fs.readFileSync('static/control_panels.js','utf8'), {
  document:{querySelectorAll:() => [manual, auto], getElementById:id => panels[id]},
  window:{dispatchEvent:event => events.push(event.type)}, Event
});
assert.deepEqual(events, []);
auto.handlers.click();
assert.equal(panels.manual.hidden, true);
assert.equal(panels.auto.hidden, false);
assert.equal(auto.attributes['aria-selected'], 'true');
assert.deepEqual(events, ['control-panel-change']);
auto.handlers.click();
assert.equal(events.length, 1);
let prevented = false;
auto.handlers.keydown({key:'ArrowRight', preventDefault:() => prevented = true});
assert.equal(prevented, true);
assert.equal(manual.focused, true);
assert.equal(manual.tabIndex, 0);
assert.equal(auto.tabIndex, -1);
assert.equal(panels.auto.hidden, true);
for (const file of ['static/manual.js', 'static/pilot.js'])
  assert.match(fs.readFileSync(file, 'utf8'), /addEventListener\('control-panel-change',.*stop\(/);
console.log('Panel navigation is display-only, keyboard accessible and releases owned controls');
