(() => {
  const $ = id => document.getElementById(id);
  const set = (id, value) => { if ($(id)) $(id).textContent = value; };
  window.addEventListener('robot-status', event => {
    const status = event.detail, cross = status.crosswalk || {}, gesture = status.gesture;
    const pilot = status.autonomous;
    set('crosswalk-state', cross.reliable === false ? '인식 과부하' : cross.stop ? '정지 구간' : cross.stable ? '확인됨' : cross.detected ? '후보 검출' : '미검출');
    set('crosswalk-count', (cross.stripes || 0) + '개');
    const states = {follow:'주행',crosswalk_approach:'횡단보도 접근',wait_gesture:'정지 · 제스처 대기',depart:'횡단보도 출발'};
    set('interaction-state', !pilot?.settings.crosswalk_gesture ? '비활성' : !pilot.active ? '대기' : states[pilot.interaction?.state] || '-');
    set('gesture-go-count', String(pilot?.interaction?.go_frames || 0));
    if (gesture) {
      set('gesture-engine', gesture.error ? '오류' : !gesture.initialized ? '준비 중' : gesture.mode === 'off' ? '주행 중 대기' : gesture.result_age_seconds > .2 ? '갱신 대기' : '준비됨');
      set('gesture-hand', gesture.hand_detected ? '검출' : '미검출');
      set('gesture-decision', ({go:'GO',stop:'STOP',unknown:'미확인'})[gesture.decision_label] || '미확인');
      set('gesture-ms', gesture.inference_ms == null ? '-' : gesture.inference_ms.toFixed(1)+' ms');
      set('gesture-fps', (gesture.inference_fps || 0).toFixed(1)+' FPS');
      set('gesture-hand-frames', (gesture.hand_frames || 0)+' / '+(gesture.sequence_length || 30));
      set('gesture-error', gesture.error || '');
    }
  });
})();
