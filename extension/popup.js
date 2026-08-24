document.addEventListener('DOMContentLoaded', () => {
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const targetTabUrl = document.getElementById('targetTabUrl');
  const btnRefresh = document.getElementById('btnRefresh');

  function updateStatus() {
    chrome.runtime.sendMessage({ type: "GET_STATUS" }, (res) => {
      if (chrome.runtime.lastError || !res) {
        statusDot.className = 'status-dot';
        statusText.innerText = 'Disconnected';
        targetTabUrl.innerText = 'No response';
        return;
      }

      if (res.connected) {
        statusDot.className = 'status-dot online';
        statusText.innerText = 'Connected';
      } else {
        statusDot.className = 'status-dot';
        statusText.innerText = 'Waiting for Engine...';
      }

      if (res.targetTab) {
        try {
          const urlObj = new URL(res.targetTab.url);
          targetTabUrl.innerText = urlObj.hostname + (urlObj.pathname.length > 1 ? urlObj.pathname : '');
          targetTabUrl.title = res.targetTab.url;
        } catch (e) {
          targetTabUrl.innerText = res.targetTab.title || 'Active Tab';
        }
      } else {
        targetTabUrl.innerText = 'No Claude/ChatGPT tab';
      }
    });
  }

  btnRefresh.addEventListener('click', updateStatus);

  // Initial update and periodic poll while popup is open
  updateStatus();
  setInterval(updateStatus, 1500);
});
