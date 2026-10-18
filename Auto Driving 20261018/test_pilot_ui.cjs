// DOM contract tests without a browser or physical GPIO.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map(), events = new Map();
const settings = {kp:60, heading_gain:.8, max_angle:20, rate:60, speed:.26, duration:3, continuous:false, curve_scale:.55};
const state = {active:false, settings:{...settings}, remaining:0, steering:0, predicted_angle:0, reference_set:true, reason:'idle'};
function element(id) {
  if (!elements.has(id)) elements.set(id, {value:0, checked:false, disabled:false, textContent:'',
    listeners:{}, addEventListener(type,fn) { this.listeners[type] = fn; }});
  return elements.get(id);
}
for (const [key,id] of Object.entries({kp:'kp',heading_gain:'heading-gain',max_angle:'max-angle',rate:'rate',speed:'speed',duration:'duration',curve_scale:'curve-scale'})) {
  element('auto-'+id).value=settings[key];
}
let fail=false, requests=[];
const context={window:{pilotOptions:state, addEventListener:(name,fn)=>events.set(name,fn)},
  document:{getElementById:element,addEventListener:()=>{}},
  navigator:{sendBeacon:()=>{}},Blob,AbortController,Math,Date,
  setInterval:()=>{},setTimeout:()=>0,clearTimeout:()=>{},
  fetch:async (url,options)=>{
    const data=JSON.parse(options.body);requests.push({url,data});
    if(fail)return {ok:false,json:async()=>({error:'rejected'})};
    state.settings={...data.settings};
    return {ok:true,json:async()=>({...state})};
  }};
vm.runInNewContext(fs.readFileSync('static/pilot.js','utf8'),context);
const display=()=>events.get('robot-status')({detail:{autonomous:state,path_prediction:{valid:true}}});
(async()=>{
  display();
  assert.equal(element('auto-curve-scale-value').textContent,'55%');
  assert.equal(element('auto-output').textContent,'0.000');
  element('auto-continuous').checked=true;
  element('auto-continuous').listeners.input();
  assert.equal(element('auto-duration').disabled,true);
  assert.equal(element('auto-duration-value').textContent,'제한 없음');
  await element('auto-continuous').listeners.change();
  assert.equal(requests.at(-1).data.settings.continuous,true);
  state.active=true;state.remaining=null;display();
  assert.equal(element('auto-remaining').textContent,'연속');
  assert.equal(element('auto-continuous').disabled,true);
  assert.equal(element('auto-speed').disabled,true);
  assert.equal(element('auto-curve-scale').disabled,true);
  state.active=false;state.remaining=0;display();
  element('auto-continuous').checked=false;
  element('auto-continuous').listeners.input();
  fail=true;
  await element('auto-continuous').listeners.change();
  assert.equal(element('auto-continuous').checked,true);
  assert.equal(element('auto-error').textContent,'rejected');
  fail=false;element('auto-continuous').checked=false;
  element('auto-continuous').listeners.input();
  await element('auto-continuous').listeners.change();
  assert.equal(element('auto-duration').disabled,false);
  assert.equal(element('auto-duration-value').textContent,'3.0초');
  console.log('Pilot UI continuous/finite/active/error contracts passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
