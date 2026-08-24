document.addEventListener('DOMContentLoaded', () => {
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const targetTabUrl = document.getElementById('targetTabUrl');
  const btnRefresh = document.getElementById('btnRefresh');

  function updateStatus() {
    chrome.runtime.sendMessage({ type: "GET_STATUS" }, (res) => {
      if (chrome.runtime.lastError || !res) {
        statusDot.className = 'status-dot';
        statusText.innerText = 'Disconnesso';
        targetTabUrl.innerText = 'Nessuna risposta';
        return;
      }

      if (res.connected) {
        statusDot.className = 'status-dot online';
        statusText.innerText = 'Connesso';
      } else {
        statusDot.className = 'status-dot';
        statusText.innerText = 'In attesa di Kitsune...';
      }

      if (res.targetTab) {
        try {
          const urlObj = new URL(res.targetTab.url);
          targetTabUrl.innerText = urlObj.hostname + (urlObj.pathname.length > 1 ? urlObj.pathname : '');
          targetTabUrl.title = res.targetTab.url;
        } catch (e) {
          targetTabUrl.innerText = res.targetTab.title || 'Tab attivo';
        }
      } else {
        targetTabUrl.innerText = 'Nessun tab Claude/ChatGPT';
      }
    });
  }

  btnRefresh.addEventListener('click', updateStatus);

  // Initial update and periodic poll while popup is open
  updateStatus();
  setInterval(updateStatus, 1500);
});
