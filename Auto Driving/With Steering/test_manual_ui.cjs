'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/manual.js', 'utf8');
const flush = async () => {for (let i=0;i<6;i++) await new Promise(resolve=>setImmediate(resolve));};

function harness(motors = true) {
  const events = new Map(), docEvents = new Map(), elements = new Map(), requests = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value:'', disabled:false, hidden:false, textContent:'', listeners:new Map(),
      classList:{toggle() {}}, dataset:{},
      addEventListener(name, fn) {this.listeners.set(name, fn);}, setPointerCapture() {}
    });
    return elements.get(id);
  }
  const buttons = ['w','s','a','d'].map(key => {
    const button = element('key-'+key); button.dataset.key = key; return button;
  });
  for (const [id,value] of Object.entries({'drive-speed':'.28','motor1-scale':'1','motor2-scale':'1',
    'manual-left-angle':'105','manual-right-angle':'85'})) element(id).value = value;
  let heartbeat, deferredArm, deferredInput, timeoutCallback;
  let holdArm = false, holdInput = false, foreign = false, rejectInput = false, timeoutInput = false;
  const state = {armed:false,owner:null,angle:0,motor_outputs:[0,0],reason:'disabled'};
  const context = {
    window:{manualOptions:{token:'test',motors_enabled:motors},addEventListener:(name,fn)=>events.set(name,fn)},
    document:{getElementById:element,querySelectorAll:()=>buttons,hidden:false,
      addEventListener:(name,fn)=>docEvents.set(name,fn)},
    navigator:{sendBeacon() {}}, Blob, AbortController, crypto:{randomUUID:()=>'one'},
    setTimeout:fn=>{timeoutCallback=fn;return 0;},clearTimeout() {},setInterval:fn=>{heartbeat=fn;},
    fetch:async(url,options)=>{
      const body = JSON.parse(options.body); requests.push({url,body});
      if (url.endsWith('/arm')) {
        if (holdArm) await new Promise(resolve=>{deferredArm=resolve;});
        if (foreign) return {ok:false,json:async()=>({error:'Another browser owns control'})};
        Object.assign(state,{armed:true,owner:'one',reason:'ready'});
      }
      if (url.endsWith('/stop')) Object.assign(state,{armed:false,owner:null,reason:'stopped',motor_outputs:[0,0]});
      if (url.endsWith('/input')) {
        if (timeoutInput) await new Promise((resolve,reject)=>{
          options.signal.addEventListener('abort',()=>reject(Error('aborted')));
        });
        if (holdInput) await new Promise(resolve=>{deferredInput=resolve;});
        if (rejectInput || !state.armed) return {ok:false,json:async()=>({error:'Lease expired'})};
        state.angle = body.keys.a === body.keys.d ? 0 : body.keys.a ? -body.left_angle : body.right_angle;
        state.motor_outputs = [0,0].map(()=>body.speed*(Number(body.keys.w)-Number(body.keys.s)));
        state.reason = 'manual';
      }
      return {ok:true,json:async()=>({...state})};
    }
  };
  vm.runInNewContext(source,context);
  return {element,requests,state,context,events,docEvents,
    heartbeat:()=>heartbeat(),holdArm:()=>{holdArm=true;},releaseArm:()=>{holdArm=false;deferredArm();},
    holdInput:()=>{holdInput=true;},releaseInput:()=>{holdInput=false;deferredInput();},
    foreign:()=>{foreign=true;},rejectInput:()=>{rejectInput=true;},
    timeoutInput:()=>{timeoutInput=true;},fireTimeout:()=>timeoutCallback(),
    key(name,code,extra={}) {events.get(name)({code,repeat:false,preventDefault() {},target:{matches:()=>false},...extra});},
    pointer(key,id=1) {element('key-'+key).listeners.get('pointerdown')({pointerId:id,button:0,preventDefault() {}});},
    releasePointer(id=1) {events.get('pointerup')({pointerId:id});}
  };
}

(async()=>{
  const h=harness(), e=h.element;
  assert.equal(e('manual-left-angle-value').textContent,'-105°');
  e('manual-left-angle').value='30'; e('manual-right-angle').value='25';
  e('manual-left-angle').listeners.get('input')(); h.heartbeat(); await flush();
  assert.equal(h.requests.length,0,'Page load, slider edits and timers cannot arm');
  assert.equal(e('key-a').title,'A · -30°'); assert.equal(e('key-d').title,'D · +25°');
  assert.equal(e('key-w').disabled,false);
  h.key('keydown','KeyW'); h.key('keydown','KeyA'); await flush();
  assert.equal(h.requests.filter(r=>r.url.endsWith('/arm')).length,1);
  assert.equal(h.state.angle,-30); assert.equal(h.state.motor_outputs[0],.28);
  assert.equal(e('manual-left-angle').disabled,true);
  h.key('keyup','KeyA'); h.key('keyup','KeyW'); await flush();
  assert.equal(h.state.angle,0); assert.equal(h.state.motor_outputs[0],0);
  assert.equal(e('manual-left-angle').disabled,false);
  h.pointer('d'); await flush(); assert.equal(h.state.angle,25);
  h.releasePointer(); await flush(); assert.equal(h.state.angle,0);
  h.key('keydown','Space'); await flush(); assert.equal(h.state.armed,false);
  let count=h.requests.length;
  h.heartbeat(); h.key('keydown','KeyW',{repeat:true}); await flush();
  assert.equal(h.requests.length,count,'Held keys and heartbeats cannot resume after stop');
  h.key('keyup','KeyW'); h.key('keydown','KeyW'); await flush();
  assert.equal(h.state.armed,true,'A fresh press can start after stop');
  e('global-stop').listeners.get('click')(); await flush(); assert.equal(h.state.armed,false);

  for (const cancel of ['release','stop','tab','blur','hidden','pagehide','global']) {
    const t=harness(); t.holdArm(); t.key('keydown','KeyW'); await flush();
    if (cancel==='release') t.key('keyup','KeyW');
    if (cancel==='stop') t.key('keydown','Escape');
    if (cancel==='tab') {t.events.get('control-panel-change')();t.element('manual-panel').hidden=true;}
    if (cancel==='blur') t.events.get('blur')();
    if (cancel==='hidden') {t.context.document.hidden=true;t.docEvents.get('visibilitychange')();}
    if (cancel==='pagehide') t.events.get('pagehide')();
    if (cancel==='global') t.element('global-stop').listeners.get('click')();
    await flush(); t.releaseArm(); await flush(); t.heartbeat(); await flush();
    assert.equal(t.requests.some(r=>r.url.endsWith('/input')),false,'Late arm cannot move after '+cancel);
    assert.equal(t.state.armed,false,'Late arm must be released after '+cancel);
  }

  const hidden=harness(); hidden.element('manual-panel').hidden=true;
  hidden.key('keydown','KeyW'); hidden.pointer('w'); await flush();
  assert.equal(hidden.requests.length,0,'Autonomous tab cannot activate manual controls');
  hidden.element('manual-panel').hidden=false;
  hidden.key('keydown','KeyW',{target:{matches:()=>true}}); await flush();
  assert.equal(hidden.requests.length,0,'Editing a form cannot start motors');
  const locked=harness(false); locked.key('keydown','KeyW'); locked.pointer('w'); await flush();
  assert.equal(locked.requests.length,0,'Unconfirmed motors stay locked');
  locked.pointer('a'); await flush(); assert.equal(locked.state.angle,-105);
  const foreign=harness(); foreign.foreign(); foreign.key('keydown','KeyW'); await flush();
  assert.equal(foreign.requests.some(r=>r.url.endsWith('/input')),false);
  assert.equal(foreign.requests.some(r=>r.body.emergency),false,'Cannot steal another owner');

  const late=harness(); late.holdInput(); late.key('keydown','KeyW'); await flush();
  late.key('keydown','Space'); await flush(); late.releaseInput(); await flush();
  count=late.requests.length; late.heartbeat(); late.key('keydown','KeyW',{repeat:true}); await flush();
  assert.equal(late.requests.length,count,'A late input reply cannot reactivate controls');
  const fault=harness(); fault.rejectInput(); fault.key('keydown','KeyW'); await flush();
  count=fault.requests.length; fault.heartbeat(); fault.key('keydown','KeyW',{repeat:true}); await flush();
  assert.equal(fault.requests.length,count,'A failed input requires a fresh press');
  assert.equal(fault.requests.at(-1).body.source,'request_rejected');
  const timeout=harness(); timeout.timeoutInput(); timeout.key('keydown','KeyW'); await flush();
  timeout.fireTimeout(); await flush();
  assert.equal(timeout.requests.at(-1).body.source,'request_timeout');
  assert.equal(timeout.state.armed,false);
  assert.match(timeout.element('manual-error').textContent,/450ms/);
  console.log('Direct manual input, steering and cancellation UI tests passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
