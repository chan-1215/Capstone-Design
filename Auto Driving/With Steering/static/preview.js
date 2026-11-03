(() => {
  'use strict';
  const video = document.getElementById('video');
  let view = 'processed';

  function pause() {
    video.removeAttribute('src');
  }

  function connect(force = false) {
    if (document.hidden) {
      pause();
      return;
    }
    const source = '/stream/' + view;
    if (force || video.getAttribute('src') !== source) video.src = source;
  }

  window.trackPreview = {
    select(next) { view = next; connect(); },
    reconnect() { connect(true); }
  };
  document.addEventListener('visibilitychange', () => connect());
  window.addEventListener('pagehide', pause);
  window.addEventListener('pageshow', () => connect());
  connect();
})();
