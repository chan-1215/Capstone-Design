(() => {
  const options = window.manualOptions;
  const $ = id => document.getElementById(id);
  const client = globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2);
  const keyboard = new Set(), pointers = new Map();
  const buttons = Array.from(document.querySelectorAll('[data-key]'));
  const keyCodes = {KeyW:'w', KeyS:'s', KeyA:'a', KeyD:'d'};
  let armed = false, wanted = false, sequence = 0, busy = false, pending = false;
  const enabled = $('manual-enabled');
  const reasons = {disabled:'비활성', ready:'대기', manual:'수동 조작', stopped:'정지',
    connection_timeout:'통신 지연 · 정지', camera_error:'카메라 오류 · 정지', hardware_error:'장치 오류', shutdown:'종료'};

  function keys() {
    const held = new Set([...keyboard, ...pointers.values()]);
    return Object.fromEntries(['w','s','a','d'].map(key => [key, held.has(key)]));
  }
  function drawButtons() {
    const held = keys();
    for (const button of buttons) {
      button.disabled = !armed || (!options.motors_enabled && 'ws'.includes(button.dataset.key));
      button.classList.toggle('pressed', held[button.dataset.key]);
    }
  }
  function disarm() {
    armed = wanted = false; enabled.checked = false;
    keyboard.clear(); pointers.clear(); drawButtons();
  }
  function display(state) {
    $('manual-state').textContent = reasons[state.reason] || state.reason;
    $('steer-angle').textContent = state.angle + '°';
    $('servo-signal').textContent = state.pwm_active ? '켜짐' : '꺼짐';
    $('test-mode').textContent = state.armed ? '수동 조작' : '수동 대기';
    if (!state.armed || state.owner !== client) disarm();
    if (state.error) $('manual-error').textContent = state.error;
  }
  async function post(action, values) {
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 450);
    try {
      const response = await fetch('/manual/' + action, {
        method:'POST', headers:{'Content-Type':'application/json', 'X-Manual-Token':options.token},
        body:JSON.stringify({client, ...values}), signal:abort.signal
      });
      const state = await response.json();
      if (!response.ok) throw Error(state.error || '수동 제어 요청 실패');
      return state;
    } finally { clearTimeout(timer); }
  }
  function beaconStop(emergency = false) {
    navigator.sendBeacon('/manual/stop', new Blob([
      JSON.stringify({client, token:options.token, emergency})
    ], {type:'application/json'}));
  }
  function stop(emergency = false) {
    const wasActive = armed || wanted;
    disarm();
    if (!wasActive && !emergency) return;
    beaconStop(emergency);
    post('stop', {emergency}).then(display).catch(() => {
      $('manual-state').textContent = '연결 끊김';
    });
  }
  async function send() {
    if (!armed) return;
    pending = true;
    if (busy) return;
    busy = true;
    do {
      pending = false;
      try {
        const state = await post('input', {sequence:++sequence, keys:keys(),
          speed:Number($('drive-speed').value), motor1_scale:Number($('motor1-scale').value),
          motor2_scale:Number($('motor2-scale').value)});
        if (wanted) display(state);
      } catch (error) {
        $('manual-error').textContent = error.message;
        stop();
      }
    } while (pending && armed);
    busy = false;
  }
  enabled.addEventListener('change', async () => {
    wanted = enabled.checked;
    if (!wanted) { stop(true); return; }
    try {
      const state = await post('arm', {});
      if (!wanted) { stop(true); return; }
      armed = true; sequence = 0;
      $('manual-error').textContent = '';
      display(state); drawButtons(); send();
    } catch (error) {
      $('manual-error').textContent = error.message;
      disarm(); beaconStop();
    }
  });
  function changed() { drawButtons(); send(); }
  window.addEventListener('keydown', event => {
    if (event.code === 'Space' || event.code === 'Escape') {
      event.preventDefault(); stop(true); return;
    }
    const key = keyCodes[event.code];
    if (!armed || !key || event.repeat || (!options.motors_enabled && 'ws'.includes(key))) return;
    if (event.target.matches('textarea,input[type=text],input[type=number]')) return;
    event.preventDefault(); keyboard.add(key); changed();
  });
  window.addEventListener('keyup', event => {
    if (keyboard.delete(keyCodes[event.code])) { event.preventDefault(); changed(); }
  });
  for (const button of buttons) button.addEventListener('pointerdown', event => {
    if (button.disabled) return;
    event.preventDefault(); button.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, button.dataset.key); changed();
  });
  for (const name of ['pointerup','pointercancel','lostpointercapture'])
    window.addEventListener(name, event => { if (pointers.delete(event.pointerId)) changed(); });
  window.addEventListener('blur', () => stop());
  window.addEventListener('pagehide', () => { if (armed || wanted) beaconStop(); disarm(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  $('manual-stop').addEventListener('click', () => stop(true));
  for (const id of ['drive-speed','motor1-scale','motor2-scale'])
    $(id).addEventListener('input', () => {
      $(id + '-value').textContent = Number($(id).value).toFixed(2) + (id === 'drive-speed' ? '' : 'x');
      send();
    });
  setInterval(send, 100);
  drawButtons();
})();
