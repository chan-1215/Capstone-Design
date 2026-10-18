(() => {
  const options = window.pilotOptions, $ = id => document.getElementById(id);
  const client = 'pilot-' + Date.now().toString(36) + Math.random().toString(36).slice(2);
  let owned = false, starting = false, busy = false, editing = false, state = options;
  const ids = {kp:'auto-kp', heading_gain:'auto-heading-gain', max_angle:'auto-max-angle', rate:'auto-rate', speed:'auto-speed', duration:'auto-duration', curve_scale:'auto-curve-scale'};
  const speedReasons = {stopped:'정지',curve:'커브 감속',limited_path:'관측 보완 감속',curve_hold:'커브 감속 유지',
    straight_wait:'직선 복귀 대기',accelerating:'서서히 가속',base_output:'기준 출력'};
  const pathReasons = {central_dash_chain:'점선 경로', insufficient_dashes:'점선 연결 부족',
    dash_boundary_corroborated:'점선·경계 방향 일치',
    local_curve_corroborated:'급커브 근거리·경계 확인',
    dash_association_failed:'점선 방향 연결 실패', insufficient_dash_span:'관측 범위 부족',
    two_dashes_uncorroborated:'점선·경계 방향 미확인', ambiguous_dash_chain:'경로 후보 중복',
    inconsistent_dash_chain:'점선 연결 불일치', target_outside_observed_path:'전방 관측 범위 부족',
    target_outside_image:'목표점 화면 밖', path_jump:'경로 급변', settings_changed:'기준 재설정 필요'};
  const blockedReasons = {path_invalid:'경로 확인 필요', reference_required:'중앙 기준 필요',
    reference_on_straight:'직선에서 기준 설정', path_stale:'카메라 지연', path_unstable:'경로 안정화 중',
    path_error_large:'큰 오차 · 경계 근거 부족'};
  const reasons = {idle:'대기', running:'주행 중', operator_stop:'사용자 정지', time_limit:'시간 종료',
    path_lost:'경로 미확인 · 정지', path_error_large:'경로 오차 큼 · 정지', browser_timeout:'연결 지연 · 정지',
    connection_timeout:'제어 지연 · 정지', storage_error:'저장 공간 부족 · 정지', camera_error:'카메라 오류 · 정지', pilot_error:'제어 오류', stopped:'정지', shutdown:'종료'};
  const settingIds = [...Object.values(ids), 'auto-continuous'];
  function disableSettings() {
    for (const id of settingIds) $(id).disabled = state.active || owned || starting || busy;
    $('auto-duration').disabled ||= $('auto-continuous').checked;
  }
  function syncSettings(settings) {
    for (const [key,id] of Object.entries(ids)) $(id).value = settings[key];
    $('auto-continuous').checked = settings.continuous === true;
    values();
  }
  function values() {
    const values = Object.fromEntries(Object.entries(ids).map(([key,id]) => [key, Number($(id).value)]));
    values.continuous = $('auto-continuous').checked;
    $('auto-kp-value').textContent = values.kp;
    $('auto-heading-gain-value').textContent = values.heading_gain.toFixed(1);
    $('auto-max-angle-value').textContent = values.max_angle + '°';
    $('auto-rate-value').textContent = values.rate + '°/s';
    $('auto-speed-value').textContent = values.speed.toFixed(2);
    $('auto-curve-scale-value').textContent = Math.round(values.curve_scale * 100) + '%';
    $('auto-duration-value').textContent = values.continuous ? '제한 없음' : values.duration.toFixed(1) + '초';
    disableSettings();
    return values;
  }
  async function post(action, data = {}, manual = false) {
    const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 600);
    try {
      const response = await fetch((manual ? '/manual/' : '/auto/') + action, {method:'POST',
        headers:{'Content-Type':'application/json','X-Manual-Token':options.token},
        body:JSON.stringify({client, ...data}), signal:abort.signal});
      const answer = await response.json();
      if (!response.ok) throw Error(answer.error || '자율 제어 요청 실패');
      return answer;
    } finally { clearTimeout(timer); }
  }
  function stop() {
    owned = starting = false;
    navigator.sendBeacon('/manual/stop', new Blob([JSON.stringify({client, token:options.token, emergency:true})], {type:'application/json'}));
    post('stop', {emergency:true}, true).catch(error => { $('auto-error').textContent = error.message; });
  }
  function display(status) {
    if (!status.autonomous) return;
    state = status.autonomous;
    if (!editing && !busy && !starting) syncSettings(state.settings);
    const path = status.path_prediction || {};
    if (!state.active) owned = false;
    $('auto-state').textContent = reasons[state.reason] || state.reason;
    $('auto-path').textContent = path.valid ? (path.source === 'dash_boundary' ? '점선 + 경계 보완' : '점선 경로 검출') : '미검출';
    $('auto-path-detail').textContent = pathReasons[path.reason] || path.reason || '-';
    $('auto-direction').textContent = ({left:'좌측',right:'우측',straight:'직진',unknown:'-'})[path.forward_direction] || '-';
    $('auto-ready').textContent = state.active ? '주행 중' : status.manual?.armed ? '수동 제어 중' : blockedReasons[state.blocked_reason] || '준비됨';
    $('auto-reference-state').textContent = state.reference_set ? '설정됨' : '미설정';
    $('auto-error-value').textContent = path.normalized_error == null ? '-' : (path.normalized_error * (status.analysis_size?.[0] || 640) / 2).toFixed(1) + ' px';
    $('auto-prediction').textContent = state.predicted_angle == null ? '-' : state.predicted_angle.toFixed(1) + '°';
    $('auto-angle').textContent = state.steering.toFixed(1) + '°';
    $('auto-output').textContent = (state.commanded_speed || 0).toFixed(3);
    $('auto-speed-state').textContent = speedReasons[state.speed_reason] || '-';
    $('auto-remaining').textContent = state.remaining == null ? '연속' : state.remaining.toFixed(1) + '초';
    $('auto-start').disabled = busy || starting || state.active || !!state.blocked_reason || !path.valid || !state.reference_set || !!status.manual?.armed;
    $('auto-reference').disabled = busy || state.active || !path.valid || Math.abs(path.heading_degrees || 0) > 12 || !!status.manual?.armed;
    disableSettings();
    if ($('manual-enabled')) $('manual-enabled').disabled = state.active || starting;
    $('test-mode').textContent = state.active ? '자율 시험' : status.manual?.armed ? '수동 조작' : '대기';
    if (state.error) $('auto-error').textContent = state.error;
  }
  $('auto-reference').addEventListener('click', async () => {
    if (busy) return;
    busy = true;
    try { await post('reference'); $('auto-error').textContent = ''; }
    catch (error) { $('auto-error').textContent = error.message; }
    finally { busy = false; }
  });
  $('auto-start').addEventListener('click', async () => {
    if (starting || owned || state.active) return;
    starting = true; $('auto-start').disabled = true; disableSettings();
    try {
      const answer = await post('start', {settings:values()});
      if (!starting) { stop(); return; }
      owned = answer.active && answer.client === client;
      $('auto-error').textContent = '';
    } catch (error) { $('auto-error').textContent = error.message; stop(); }
    finally { starting = false; disableSettings(); }
  });
  $('auto-stop').addEventListener('click', stop);
  for (const id of settingIds) {
    $(id).addEventListener('input', () => { editing = true; values(); });
    $(id).addEventListener('change', async () => {
      if (busy || starting || state.active) return;
      busy = true; disableSettings(); $('auto-start').disabled = true;
      try { const answer = await post('settings', {settings:values()}); state = answer; syncSettings(answer.settings); $('auto-error').textContent = ''; }
      catch (error) { syncSettings(state.settings); $('auto-error').textContent = error.message; }
      finally { busy = editing = false; disableSettings(); }
    });
  }
  let heartbeatBusy = false;
  setInterval(async () => {
    if (!owned || heartbeatBusy) return;
    heartbeatBusy = true;
    try { const answer = await post('heartbeat'); if (!answer.active) owned = false; }
    catch (error) { $('auto-error').textContent = error.message; stop(); }
    finally { heartbeatBusy = false; }
  }, 150);
  window.addEventListener('robot-status', event => display(event.detail));
  window.addEventListener('blur', () => { if (owned || starting) stop(); });
  window.addEventListener('pagehide', () => { if (owned || starting) stop(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden && (owned || starting)) stop(); });
  window.addEventListener('keydown', event => { if ((event.code === 'Space' || event.code === 'Escape') && (owned || starting)) stop(); });
  values();
})();
