document.addEventListener('DOMContentLoaded', () => {
  const card = document.getElementById('relayCard');
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const targetTabUrl = document.getElementById('targetTabUrl');
  const wsEndpoint = document.getElementById('wsEndpoint');
  const statProbes = document.getElementById('statProbes');
  const statRefusals = document.getElementById('statRefusals');
  const statLatency = document.getElementById('statLatency');
  const lastSeen = document.getElementById('lastSeen');
  const btnRefresh = document.getElementById('btnRefresh');

  function ago(ts) {
    if (!ts) return 'never';
    const s = Math.round((Date.now() - ts) / 1000);
    if (s < 5) return 'just now';
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    return `${Math.round(s / 3600)}h ago`;
  }

  function setState(kind, label) {
    card.classList.toggle('is-linked', kind !== 'offline');
    card.classList.toggle('is-busy', kind === 'busy');
    statusDot.className = 'status-dot' + (kind === 'offline' ? '' : ` ${kind === 'busy' ? 'busy' : 'online'}`);
    statusText.innerText = label;
  }

  function updateStatus() {
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
      if (chrome.runtime.lastError || !res) {
        setState('offline', 'Service worker asleep');
        targetTabUrl.innerText = 'Reopen this popup to wake it';
        return;
      }

      const stats = res.stats || {};

      if (!res.connected) {
        setState('offline', 'Waiting for engine');
      } else if (stats.busy) {
        setState('busy', `Probing${stats.lastRound ? ` · round ${stats.lastRound}` : ''}`);
      } else {
        setState('online', 'Linked to engine');
      }

      if (wsEndpoint && res.wsUrl) wsEndpoint.innerText = res.wsUrl.replace(/^ws:\/\//, '');

      if (res.targetTab) {
        try {
          const u = new URL(res.targetTab.url);
          targetTabUrl.innerText = u.hostname + (u.pathname.length > 1 ? u.pathname : '');
        } catch (e) {
          targetTabUrl.innerText = res.targetTab.title || 'Active tab';
        }
        targetTabUrl.title = res.targetTab.url;
      } else {
        targetTabUrl.innerText = 'No eligible tab open';
        targetTabUrl.title = '';
      }

      statProbes.innerText = stats.probes || 0;
      statRefusals.innerText = stats.refusals || 0;
      statLatency.innerText = stats.lastLatencyMs ? `${(stats.lastLatencyMs / 1000).toFixed(1)}s` : '—';
      lastSeen.innerText = stats.lastError ? stats.lastError : ago(stats.lastAt);
    });
  }

  btnRefresh.addEventListener('click', updateStatus);

  updateStatus();
  setInterval(updateStatus, 1200);
});
