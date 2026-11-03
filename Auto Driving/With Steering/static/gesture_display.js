(() => {
  const image = document.getElementById('pedestrian-signal');
  const screen = document.getElementById('pedestrian-display');
  const placeholder = document.getElementById('signal-placeholder');
  const state = document.getElementById('signal-state');
  const enabled = window.gestureDisplayOptions?.enabled === true;
  const displayMaxAgeMs = 500; // Display only; worker/control freshness is unchanged.
  let selected = null, nextPoll = null, expiry = null, request = null, generation = 0;

  function clear(message = '인식 대기') {
    clearTimeout(expiry);
    selected = null;
    image.hidden = true;
    image.removeAttribute('src');
    image.alt = '';
    screen.dataset.state = 'unknown';
    placeholder.textContent = message;
    placeholder.hidden = false;
    state.textContent = message;
  }
  function display(payload, roundTripMs) {
    const g = payload.gesture;
    if (!payload.available || !g) { clear('제스처 미사용'); return; }
    if (g.error) { clear('인식 오류'); return; }
    if (!g.initialized) { clear('준비 중'); return; }
    const age = g.result_age_seconds;
    const remaining = displayMaxAgeMs - age * 1000 - roundTripMs;
    if (!Number.isFinite(age) || age < 0 || remaining <= 0) { clear('갱신 대기'); return; }
    if (!['preview', 'wait'].includes(g.mode) || g.ready !== true || g.hand_detected !== true ||
        !['go', 'stop'].includes(g.decision_label)) { clear(); return; }
    const label = g.decision_label;
    // Labels describe VEHICLE requests; colours address the PEDESTRIAN.
    if (selected !== label) {
      image.src = label === 'go' ? image.dataset.goSrc : image.dataset.stopSrc;
      image.alt = label === 'go' ? 'GO 인식 · 보행자 대기 신호' : 'STOP 인식 · 보행자용 초록 신호';
      selected = label;
    }
    image.hidden = false;
    placeholder.hidden = true;
    screen.dataset.state = label;
    state.textContent = '차량 ' + label.toUpperCase() + ' 인식';
    clearTimeout(expiry);
    // Fail closed when updates stop. This display NEVER authorizes motor motion.
    expiry = setTimeout(() => clear('갱신 대기'), remaining);
  }
  async function poll(epoch) {
    if (document.hidden || epoch !== generation) return;
    const controller = new AbortController();
    request = controller;
    const started = performance.now();
    const deadline = setTimeout(() => controller.abort(), 400);
    try {
      const response = await fetch('/gesture/status', {cache:'no-store', signal:controller.signal});
      if (!response.ok) throw Error('Gesture display unavailable');
      const payload = await response.json();
      if (epoch === generation && !document.hidden) display(payload, performance.now() - started);
    } catch (_) {
      if (epoch === generation) clear('연결 대기');
    } finally {
      clearTimeout(deadline);
      if (request === controller) request = null;
      if (epoch === generation && !document.hidden) nextPoll = setTimeout(() => poll(epoch), 100);
    }
  }
  function pause() {
    generation++;
    clearTimeout(nextPoll);
    request?.abort();
    clear();
  }
  function resume() {
    pause();
    if (!enabled) { clear('제스처 미사용'); return; }
    if (!document.hidden) poll(generation);
  }
  document.addEventListener('visibilitychange', resume);
  window.addEventListener('pagehide', pause);
  window.addEventListener('pageshow', resume);
  image.addEventListener('error', () => clear('이미지 오류'));
  resume();
})();
