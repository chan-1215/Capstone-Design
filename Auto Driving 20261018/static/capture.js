(() => {
  const options = window.captureOptions, $ = id => document.getElementById(id);
  const client = 'capture-' + Date.now().toString(36) + Math.random().toString(36).slice(2);
  let recording = false, busy = false;
  function display(state) {
    recording = state.recording;
    $('record-label').textContent = state.stopping ? '저장 중' : recording ? '녹화 정지' : '녹화 시작';
    $('record-icon').src = '/static/icons/' + (recording ? 'square' : 'video') + '.svg';
    $('capture-video').classList.toggle('recording', recording);
    $('capture-video').title = recording ? '영상 녹화 정지' : '영상 녹화 시작';
    $('capture-video').disabled = busy || state.stopping;
    const seconds = Math.floor(state.elapsed_seconds);
    $('record-time').textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0');
    $('capture-free').textContent = state.free_mib + ' MiB';
    $('capture-directory').textContent = state.directory;
    if (state.error) $('capture-error').textContent = state.error;
    const list = $('capture-files');
    list.replaceChildren();
    for (const file of state.files) {
      const item = document.createElement('li'), link = document.createElement('a'), size = document.createElement('small');
      link.textContent = file.name;
      if (!(recording && (state.active_files || state.last_files).includes(file.path))) {
        link.href = '/media/' + file.path.split('/').map(encodeURIComponent).join('/');
        link.setAttribute('download', file.name);
      }
      size.textContent = (file.bytes / 1024).toFixed(0) + ' KiB';
      item.append(link, size); list.append(item);
    }
  }
  async function action(name) {
    if (busy) return;
    busy = true; $('capture-photo').disabled = $('capture-video').disabled = true;
    try {
      const response = await fetch('/capture/' + name, {method:'POST',
        headers:{'Content-Type':'application/json','X-Manual-Token':options.token}, body:JSON.stringify({client})});
      const state = await response.json();
      if (!response.ok) throw Error(state.error || '촬영 요청 실패');
      $('capture-error').textContent = ''; display(state);
    } catch (error) { $('capture-error').textContent = error.message; }
    finally { busy = false; $('capture-photo').disabled = false; $('capture-video').disabled = false; }
  }
  $('capture-photo').addEventListener('click', () => action('photo'));
  $('capture-video').addEventListener('click', () => action(recording ? 'stop' : 'start'));
  window.addEventListener('robot-status', event => { if (event.detail.capture) display(event.detail.capture); });
  display(options);
})();
