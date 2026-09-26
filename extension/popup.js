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
  const btnLaunch = document.getElementById('btnLaunch');
  const engagementId = document.getElementById('engagementId');
  const launchHint = document.getElementById('launchHint');

  let runInFlight = false;

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
      } else if (stats.runInFlight) {
        setState('busy', 'Run in flight');
      } else {
        setState('online', 'Linked to engine');
      }

      runInFlight = !!stats.runInFlight;
      updateLaunchButton(res.connected);
      if (stats.lastRunError) launchHint.innerText = `Last run: ${stats.lastRunError}`;

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

  function updateLaunchButton(connected) {
    if (!btnLaunch) return;
    // While a run is in flight the button becomes a Stop control; otherwise it
    // launches (disabled only when the engine isn't connected).
    btnLaunch.classList.toggle('is-stop', runInFlight);
    if (runInFlight) {
      btnLaunch.disabled = false;
      btnLaunch.innerText = '⏹ Stop test';
    } else {
      btnLaunch.disabled = !connected;
      btnLaunch.innerText = 'Launch test on bound tab';
    }
  }

  function stopRun() {
    btnLaunch.disabled = true;
    btnLaunch.innerText = 'Stopping…';
    launchHint.innerText = 'Aborting run…';
    chrome.runtime.sendMessage({ type: 'STOP_RUN' }, (res) => {
      if (chrome.runtime.lastError || !res) {
        launchHint.innerText = 'Service worker asleep — retry.';
      } else {
        runInFlight = false;
        launchHint.innerText = res.ok ? 'Run stopped.' : (res.error || 'Stop failed.');
      }
      updateStatus();
    });
  }

  if (btnLaunch) {
    btnLaunch.addEventListener('click', () => {
      // Running → this click stops it.
      if (runInFlight) { stopRun(); return; }

      const engagement = (engagementId.value || '').trim();
      if (!engagement) {
        launchHint.innerText = 'Engagement ID is required.';
        engagementId.focus();
        return;
      }
      btnLaunch.disabled = true;
      btnLaunch.innerText = 'Launching…';
      launchHint.innerText = 'Sending to engine…';

      const num = (id) => {
        const el = document.getElementById(id);
        const v = el ? parseFloat(el.value) : NaN;
        return Number.isFinite(v) ? v : null;
      };

      chrome.runtime.sendMessage(
        {
          type: 'LAUNCH_RUN',
          engagement_id: engagement,
          params: {
            max_rounds: num('maxRounds'),
            attempts_per_round: num('attemptsPerRound'),
            confidence_threshold: num('confThreshold'),
            multiturn_depth: num('multiturnDepth')
          }
        },
        (res) => {
          if (chrome.runtime.lastError || !res) {
            launchHint.innerText = 'Service worker asleep — retry.';
            updateStatus();
            return;
          }
          if (res.ok) {
            runInFlight = true;
            launchHint.innerText = `Launched on ${res.target || 'bound tab'}.`;
          } else {
            launchHint.innerText = res.error || 'Launch failed.';
          }
          updateStatus();
        }
      );
    });
  }

  btnRefresh.addEventListener('click', updateStatus);

  // Forget learned capture selectors (per-site) so the next probe recalibrates.
  const btnClearCache = document.getElementById('btnClearCache');
  if (btnClearCache) {
    btnClearCache.addEventListener('click', async () => {
      try {
        const all = await chrome.storage.local.get(null);
        const keys = Object.keys(all).filter(k => k.startsWith('kitsune_capture_'));
        if (keys.length) await chrome.storage.local.remove(keys);
        btnClearCache.innerText = keys.length ? `Cleared ${keys.length}` : 'Nothing cached';
      } catch (e) {
        btnClearCache.innerText = 'Failed';
      }
      setTimeout(() => { btnClearCache.innerText = 'Clear cache'; }, 1800);
    });
  }

  updateStatus();
  setInterval(updateStatus, 1200);
});
