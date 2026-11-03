const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const events=new Map(),windows=new Map(),timers=new Map(),requests=[],elements=new Map();
let next=0,now=1000,payload,fail=false;
function element(id){
  if(!elements.has(id))elements.set(id,{hidden:true,textContent:'',alt:'',dataset:{goSrc:'/red.gif',stopSrc:'/green.gif'},
    src:'',writes:0,removeAttribute(key){this[key]='';},addEventListener(name,fn){this[name]=fn;}});
  return elements.get(id);
}
const image=element('pedestrian-signal');
let source='';Object.defineProperty(image,'src',{get:()=>source,set:value=>{source=value;image.writes++;},configurable:true});
const doc={hidden:false,getElementById:element,addEventListener:(name,fn)=>events.set(name,fn)};
function fresh(label,extra={}){return {available:true,gesture:{initialized:true,ready:true,hand_detected:true,
  mode:'preview',result_age_seconds:.05,decision_label:label,...extra}};}
payload=fresh('go');
vm.runInNewContext(fs.readFileSync('static/gesture_display.js','utf8'),{
  document:doc,window:{gestureDisplayOptions:{enabled:true},addEventListener:(name,fn)=>windows.set(name,fn)},
  performance:{now:()=>now},AbortController,
  setTimeout:(fn,ms)=>{const id=++next;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
  fetch:async(url,options)=>{requests.push({url,options});if(fail)throw Error('offline');return {ok:true,json:async()=>payload};}
});
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
async function poll(){const timer=[...timers].find(([,v])=>v.ms===100);assert.ok(timer);timers.delete(timer[0]);timer[1].fn();await flush();}
(async()=>{
  await flush();assert.equal(source,'/red.gif');assert.equal(image.hidden,false);
  assert.equal(element('pedestrian-display').dataset.state,'go');
  const writes=image.writes;await poll();assert.equal(image.writes,writes,'same label must not restart GIF');
  payload=fresh('stop');await poll();assert.equal(source,'/green.gif');
  payload=fresh('unknown',{label:'go'});await poll();assert.equal(image.hidden,true);
  assert.equal(source,'','held label must not choose a GIF');
  for(const bad of [{hand_detected:false},{ready:false},{mode:'off'},{error:'failed'},
                   {initialized:false},{result_age_seconds:1},{result_age_seconds:-1},{result_age_seconds:null}]){
    payload=fresh('stop');await poll();assert.equal(image.hidden,false);
    payload=fresh('go',bad);await poll();assert.equal(image.hidden,true,JSON.stringify(bad));
  }
  payload=fresh('stop');await poll();
  const expiry=[...timers].find(([,v])=>v.ms===450);assert.ok(expiry);expiry[1].fn();assert.equal(image.hidden,true);
  payload=fresh('go');await poll();fail=true;await poll();assert.equal(image.hidden,true);fail=false;
  payload=fresh('stop');await poll();doc.hidden=true;events.get('visibilitychange')();await flush();
  assert.equal(image.hidden,true);assert.equal(timers.size,0);
  doc.hidden=false;events.get('visibilitychange')();await flush();assert.equal(source,'/green.gif');
  windows.get('pagehide')();assert.equal(image.hidden,true);
  assert.ok(requests.every(r=>r.url==='/gesture/status' && !r.options.method && !r.options.body));
  console.log('Pedestrian red GO / green STOP, no GIF restarts, unknown/error/expiry/hide and GET-only contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
