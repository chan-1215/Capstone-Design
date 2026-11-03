const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const events=new Map(),listeners=new Map(),requests=[],beacons=[];
const button={hidden:true,disabled:false,addEventListener:(name,fn)=>listeners.set(name,fn)};
const error={textContent:''};let fail=false;
vm.runInNewContext(fs.readFileSync('static/safety.js','utf8'),{
  window:{manualOptions:{token:'test-token'},addEventListener:(name,fn)=>events.set(name,fn)},
  document:{getElementById:id=>id==='global-stop'?button:error},
  navigator:{sendBeacon:(url,body)=>beacons.push({url,body})},
  Blob,Date,AbortController,setTimeout:()=>0,clearTimeout:()=>{},
  fetch:async(url,options)=>{requests.push({url,data:JSON.parse(options.body)});return {ok:!fail};}
});
(async()=>{
  events.get('robot-status')({detail:{manual:{armed:true},autonomous:{active:false}}});
  assert.equal(button.hidden,false);
  await listeners.get('click')();
  assert.equal(beacons[0].url,'/manual/stop');
  assert.equal(requests[0].url,'/manual/stop');
  assert.equal(requests[0].data.emergency,true);
  assert.equal(requests[0].data.token,'test-token');
  assert.equal(button.disabled,false);
  events.get('robot-status')({detail:{manual:{armed:false},autonomous:{active:false}}});
  assert.equal(button.hidden,true);
  fail=true;await listeners.get('click')();
  assert.equal(error.textContent,'정지 명령 확인 실패');
  assert.equal(button.disabled,false);
  assert.equal(requests.some(x=>x.url!=='/manual/stop'),false);
  console.log('Sticky emergency stop visibility, ownership-independent stop and failure contracts passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
