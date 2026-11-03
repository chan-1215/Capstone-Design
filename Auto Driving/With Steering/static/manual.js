(() => {
  const options = window.manualOptions;
  const $ = id => document.getElementById(id);
  const client = globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2);
  const keyboard = new Set(), pointers = new Map();
  const buttons = Array.from(document.querySelectorAll('[data-key]'));
  const keyCodes = {KeyW:'w', KeyS:'s', KeyA:'a', KeyD:'d'};
  let armed = false, wanted = false, sequence = 0, busy = false, pending = false;
  let arming = false, stopping = 0, generation = 0;
  const steeringIds = ['manual-left-angle', 'manual-right-angle'];
  const reasons = {disabled:'입력 대기', ready:'입력 대기', manual:'수동 조작', stopped:'정지',
    waiting_gesture:'제스처 대기',pilot:'자율 제어',time_limit:'시험 시간 종료',operator_stop:'사용자 정지',
    connection_timeout:'통신 지연 · 정지', camera_error:'카메라 오류 · 정지', hardware_error:'장치 오류', shutdown:'종료'};

  function keys() {
    const held = new Set([...keyboard, ...pointers.values()]);
    return Object.fromEntries(['w','s','a','d'].map(key => [key, held.has(key)]));
  }
  function manualVisible() { return !document.hidden && !$('manual-panel').hidden; }
  function acceptsInput() {
    return manualVisible() && !stopping && (!arming || wanted) && (!busy || armed);
  }
  function drawButtons() {
    const held = keys();
    for (const id of steeringIds) $(id).disabled = Object.values(held).some(Boolean);
    for (const button of buttons) {
      button.disabled = !options.motors_enabled && 'ws'.includes(button.dataset.key);
      button.classList.toggle('pressed', held[button.dataset.key]);
    }
  }
  function disarm() {
    generation++;
    armed = wanted = false;
    keyboard.clear(); pointers.clear(); drawButtons();
  }
  function display(state) {
    $('manual-state').textContent = reasons[state.reason] || state.reason;
    $('steer-angle').textContent = state.angle + '°';
    $('servo-signal').textContent = state.pwm_active ? '켜짐' : '꺼짐';
    $('motor-left-output').textContent = (state.motor_outputs?.[0] || 0).toFixed(3);
    $('motor-right-output').textContent = (state.motor_outputs?.[1] || 0).toFixed(3);
    $('motor-write-count').textContent = String(state.motor_write_count || 0);
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
      if (!response.ok) {
        const error = Error(state.error || '수동 제어 요청 실패');
        error.stopSource = 'request_rejected';
        throw error;
      }
      return state;
    } catch (error) {
      if (abort.signal.aborted) {
        const timeout = Error('수동 명령 응답 지연(450ms)으로 정지');
        timeout.stopSource = 'request_timeout';
        throw timeout;
      }
      throw error;
    } finally { clearTimeout(timer); }
  }
  function beaconStop(emergency = false, source = 'operator') {
    navigator.sendBeacon('/manual/stop', new Blob([
      JSON.stringify({client, token:options.token, emergency, source})
    ], {type:'application/json'}));
  }
  function stop(emergency = false, source = 'operator') {
    const wasActive = armed || wanted;
    disarm();
    if (!wasActive && !emergency) return;
    const epoch = generation;
    stopping++;
    beaconStop(emergency, source);
    post('stop', {emergency, source}).then(display).catch(() => {
      if (epoch === generation) $('manual-state').textContent = '연결 끊김';
    }).finally(() => { stopping--; });
  }
  async function send() {
    if (!armed) return;
    pending = true;
    if (busy) return;
    busy = true;
    do {
      pending = false;
      const epoch = generation;
      try {
        const state = await post('input', {sequence:++sequence, keys:keys(),
          speed:Number($('drive-speed').value), motor1_scale:Number($('motor1-scale').value),
          motor2_scale:Number($('motor2-scale').value),
          left_angle:Number($('manual-left-angle').value), right_angle:Number($('manual-right-angle').value)});
        if (wanted && epoch === generation) display(state);
      } catch (error) {
        if (epoch === generation) {
          $('manual-error').textContent = error.message;
          stop(false, error.stopSource || 'request_error');
        }
      }
    } while (pending && armed);
    busy = false;
  }
  async function startFromInput() {
    if (armed || wanted || arming || stopping || busy || !manualVisible()) return;
    if (!Object.values(keys()).some(Boolean)) return;
    wanted = arming = true;
    const epoch = ++generation;
    try {
      const state = await post('arm', {});
      // A late arm reply must never replay keys released or cancelled while waiting.
      if (epoch !== generation || !wanted || !manualVisible() || !Object.values(keys()).some(Boolean)) {
        beaconStop(false, 'cancelled_arm');
        await post('stop', {emergency:false, source:'cancelled_arm'});
        return;
      }
      armed = true; sequence = 0;
      $('manual-error').textContent = '';
      display(state); drawButtons(); send();
    } catch (error) {
      if (epoch === generation) {
        $('manual-error').textContent = error.message;
        stop(false, error.stopSource || 'request_error');
      } else beaconStop(false, 'cancelled_arm');
    } finally { arming = false; drawButtons(); }
  }
  function changed() {
    drawButtons();
    if (wanted && !armed && !Object.values(keys()).some(Boolean)) stop(false, 'released_before_arm');
    else send();
  }
  window.addEventListener('keydown', event => {
    if (event.code === 'Space' || event.code === 'Escape') {
      event.preventDefault(); stop(true, 'keyboard_stop'); return;
    }
    const key = keyCodes[event.code];
    if (!acceptsInput() || !key || event.repeat || (!options.motors_enabled && 'ws'.includes(key))) return;
    if (event.target.matches('textarea,input,select,[contenteditable="true"]')) return;
    event.preventDefault(); keyboard.add(key); changed(); startFromInput();
  });
  window.addEventListener('keyup', event => {
    if (keyboard.delete(keyCodes[event.code])) { event.preventDefault(); changed(); }
  });
  for (const button of buttons) button.addEventListener('pointerdown', event => {
    if (button.disabled || !acceptsInput() || (event.button !== undefined && event.button !== 0)) return;
    event.preventDefault(); button.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, button.dataset.key); changed(); startFromInput();
  });
  for (const name of ['pointerup','pointercancel','lostpointercapture'])
    window.addEventListener(name, event => { if (pointers.delete(event.pointerId)) changed(); });
  window.addEventListener('blur', () => stop(false, 'window_blur'));
  window.addEventListener('control-panel-change', () => stop(false, 'tab_change'));
  window.addEventListener('pagehide', () => { if (armed || wanted) beaconStop(false, 'page_exit'); disarm(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(false, 'page_hidden'); });
  $('manual-stop').addEventListener('click', () => stop(true, 'stop_button'));
  $('global-stop')?.addEventListener('click', () => stop(false, 'global_stop'));
  for (const id of ['drive-speed','motor1-scale','motor2-scale'])
    $(id).addEventListener('input', () => {
      $(id + '-value').textContent = Number($(id).value).toFixed(2) + (id === 'drive-speed' ? '' : 'x');
      send();
    });
  function steeringLabels() {
    for (const [index, id] of steeringIds.entries()) {
      const key = index === 0 ? 'a' : 'd';
      const value = (index === 0 ? '-' : '+') + Number($(id).value) + '°';
      $(id + '-value').textContent = value;
      buttons.find(button => button.dataset.key === key).title = key.toUpperCase() + ' · ' + value;
    }
  }
  for (const id of steeringIds) $(id).addEventListener('input', steeringLabels);
  steeringLabels();
  setInterval(send, 100);
  drawButtons();
})();
