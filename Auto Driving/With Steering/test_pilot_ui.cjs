// DOM contract tests without a browser or physical GPIO.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map(), events = new Map();
const settings = {kp:60, heading_gain:.8, max_left_angle:105, max_right_angle:85, rate:60, speed:.26, duration:3, continuous:false,curve_scale:.85};
const state = {active:false, settings:{...settings}, remaining:0, steering:0, predicted_angle:0, reference_set:true, reason:'idle'};
function element(id) {
  if (!elements.has(id)) elements.set(id, {value:0, checked:false, disabled:false, textContent:'',
    listeners:{}, addEventListener(type,fn) { this.listeners[type] = fn; }});
  return elements.get(id);
}
for (const [key,id] of Object.entries({kp:'kp',heading_gain:'heading-gain',max_left_angle:'max-left-angle',max_right_angle:'max-right-angle',rate:'rate',speed:'speed',duration:'duration',curve_scale:'curve-scale'})) {
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
const display=(path={valid:true})=>events.get('robot-status')({detail:{autonomous:state,path_prediction:path}});
(async()=>{
  display();
  assert.equal(element('auto-max-left-angle-value').textContent,'-105°');
  assert.equal(element('auto-max-right-angle-value').textContent,'+85°');
  assert.equal(element('auto-curve-scale-value').textContent,'85%');
  assert.equal(element('auto-output').textContent,'0.000');
  display({valid:true,source:'single_dash_boundary',reason:'single_dash_corroborated'});
  assert.equal(element('auto-path').textContent,'단일 점선 + 경계 보완');
  assert.equal(element('auto-path-detail').textContent,'단일 점선 중심·경계 확인');
  assert.equal(element('auto-reference').disabled,true);
  display({valid:true,source:'dash_boundary',reason:'near_centres_corroborated'});
  assert.equal(element('auto-path-detail').textContent,'근거리 중심점·경계 확인');
  element('auto-continuous').checked=true;
  element('auto-continuous').listeners.input();
  assert.equal(element('auto-duration').disabled,true);
  assert.equal(element('auto-duration-value').textContent,'제한 없음');
  await element('auto-continuous').listeners.change();
  assert.equal(requests.at(-1).data.settings.continuous,true);
  assert.equal(requests.at(-1).data.settings.max_left_angle,105);
  assert.equal(requests.at(-1).data.settings.max_right_angle,85);
  assert.equal('max_angle' in requests.at(-1).data.settings,false);
  assert.equal(requests.at(-1).data.settings.curve_scale,.85);
  state.active=true;state.remaining=null;state.turn_direction='left';
  display({valid:true,forward_direction:'straight'});
  assert.equal(element('auto-direction').textContent,'좌측');
  assert.equal(element('auto-remaining').textContent,'연속');
  assert.equal(element('auto-continuous').disabled,true);
  assert.equal(element('auto-speed').disabled,true);
  assert.equal(element('auto-curve-scale').disabled,true);
  assert.equal(element('auto-max-left-angle').disabled,true);
  assert.equal(element('auto-max-right-angle').disabled,true);
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
  state.gesture_available=true;display();
  element('auto-crosswalk-gesture').checked=true;
  element('auto-crosswalk-gesture').listeners.input();
  assert.equal(element('auto-continuous').checked,true);
  assert.equal(element('auto-continuous').disabled,true);
  await element('auto-crosswalk-gesture').listeners.change();
  assert.equal(requests.at(-1).data.settings.crosswalk_gesture,true);
  assert.equal(requests.at(-1).data.settings.continuous,true);
  element('auto-turn-recovery').checked=true;
  element('auto-turn-recovery').listeners.input();
  await element('auto-turn-recovery').listeners.change();
  assert.equal(requests.at(-1).data.settings.turn_recovery,true);
  element('auto-lap-mode').checked=true;
  element('auto-lap-mode').listeners.input();
  assert.equal(element('auto-continuous').checked,true);
  assert.equal(element('auto-continuous').disabled,true);
  assert.equal(element('auto-kp').value,35);
  assert.equal(element('auto-heading-gain').value,1);
  await element('auto-lap-mode').listeners.change();
  assert.equal(requests.at(-1).data.settings.lap_mode,true);
  assert.equal(requests.at(-1).data.settings.kp,35);
  element('auto-boundary-guidance').checked=true;
  element('auto-boundary-guidance').listeners.input();
  assert.equal(element('auto-lap-mode').checked,true);
  assert.equal(element('auto-heading-gain').value,1);
  await element('auto-boundary-guidance').listeners.change();
  assert.equal(requests.at(-1).data.settings.boundary_guidance,true);
  display({valid:true,source:'single_dash_boundary',reason:'boundary_guided_curve',guidance_mode:'boundary_curve'});
  assert.equal(element('auto-path').textContent,'경계 방향 + 근거리 흰점');
  assert.equal(element('auto-path-detail').textContent,'노란 경계 방향 · 관측 흰점 목표');
  assert.equal(element('auto-reference').disabled,true);
  state.active=true;state.recovery_active=true;display();
  assert.equal(element('auto-turn-recovery').disabled,true);
  assert.equal(element('auto-crosswalk-gesture').disabled,true);
  assert.equal(element('auto-lap-mode').disabled,true);
  assert.equal(element('auto-boundary-guidance').disabled,true);
  assert.equal(element('auto-state').textContent,'짧은 커브 복구');
  console.log('Pilot UI continuous/finite/active/error/recovery/crossing contracts passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
