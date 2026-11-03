(() => {
  const tabs = Array.from(document.querySelectorAll('[data-control-panel]'));
  function select(tab, focus = false) {
    if (tab.getAttribute('aria-selected') === 'true') return;
    // Hiding an owned controller releases its inputs; selecting never arms it.
    window.dispatchEvent(new Event('control-panel-change'));
    for (const other of tabs) {
      const selected = other === tab;
      other.setAttribute('aria-selected', String(selected));
      other.tabIndex = selected ? 0 : -1;
      document.getElementById(other.dataset.controlPanel).hidden = !selected;
    }
    if (focus) tab.focus();
  }
  for (const tab of tabs) {
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', event => {
      const index = tabs.indexOf(tab);
      const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
        : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
      if (next !== null) { event.preventDefault(); select(tabs[next], true); }
    });
  }
})();
