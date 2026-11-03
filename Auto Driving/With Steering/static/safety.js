(() => {
  const button = document.getElementById('global-stop'), options = window.manualOptions;
  if (!button || !options) return;
  const client = 'safety-' + Date.now().toString(36);
  window.addEventListener('robot-status', event => {
    button.hidden = !event.detail.manual?.armed && !event.detail.autonomous?.active;
  });
  button.addEventListener('click', async () => {
    const payload = JSON.stringify({client,token:options.token,emergency:true});
    navigator.sendBeacon('/manual/stop',new Blob([payload],{type:'application/json'}));
    const abort = new AbortController(), timer = setTimeout(()=>abort.abort(),450);
    button.disabled = true;
    try {
      const response = await fetch('/manual/stop',{method:'POST',
        headers:{'Content-Type':'application/json','X-Manual-Token':options.token},
        body:payload,signal:abort.signal});
      if (!response.ok) throw Error('정지 명령 확인 실패');
      document.getElementById('manual-error').textContent = '';
    } catch (error) {
      document.getElementById('manual-error').textContent = error.message;
    } finally { clearTimeout(timer);button.disabled=false; }
  });
})();
