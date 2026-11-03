const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map(), events = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {textContent:''});
  return elements.get(id);
};
vm.runInNewContext(fs.readFileSync('static/interaction.js','utf8'), {
  document:{getElementById:element},
  window:{addEventListener:(name,fn)=>events.set(name,fn)},
  fetch:()=>{ throw Error('Read-only interaction display must not issue commands'); }
});
const display = detail => events.get('robot-status')({detail});
display({crosswalk:{detected:true,stripes:4},gesture:{initialized:false}});
assert.equal(element('crosswalk-state').textContent,'후보 검출');
assert.equal(element('gesture-engine').textContent,'준비 중');
display({crosswalk:{stop:true,stripes:4},gesture:{initialized:true,mode:'wait',
  label:'go',decision_label:'unknown',hand_detected:false,inference_ms:24},
  autonomous:{active:true,settings:{crosswalk_gesture:true},interaction:{state:'wait_gesture',go_frames:0}}});
assert.equal(element('interaction-state').textContent,'정지 · 제스처 대기');
assert.equal(element('gesture-decision').textContent,'미확인');
assert.equal(element('gesture-go-count').textContent,'0');
display({gesture:{initialized:true,mode:'off',error:'model unavailable'},
  autonomous:{active:false,settings:{crosswalk_gesture:false}}});
assert.equal(element('gesture-engine').textContent,'오류');
assert.equal(element('gesture-error').textContent,'model unavailable');
assert.equal(element('interaction-state').textContent,'비활성');
console.log('Interaction display freshness and read-only contracts passed');
