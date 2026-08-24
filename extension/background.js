/**
 * Kitsune Guardrail Relay - Background Service Worker
 * Manages WebSocket bridge between Kitsune Python engine and active target tabs.
 */

const WS_URL = "ws://127.0.0.1:8888/ws/relay";
let ws = null;
let isConnected = false;
let reconnectTimer = null;
let lastTargetTabInfo = null;

// --- Initialize WebSocket Connection ---
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  console.log("[Kitsune Relay] Connecting to WebSocket at", WS_URL);

  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = async () => {
      isConnected = true;
      console.log("[Kitsune Relay] Connected to Kitsune engine!");
      chrome.action.setBadgeText({ text: "ON" });
      chrome.action.setBadgeBackgroundColor({ color: "#10b981" });

      // Send initial handshake with active tab info
      const activeTab = await findTargetTab();
      sendWsMessage({
        type: "HANDSHAKE",
        client: "chrome-extension-relay",
        version: "1.0.0",
        active_tab: activeTab ? { id: activeTab.id, url: activeTab.url, title: activeTab.title } : null
      });
    };

    ws.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log("[Kitsune Relay] Received WS message:", message.type, message);

        if (message.type === "PROBE_REQUEST") {
          await handleProbeRequest(message);
        } else if (message.type === "PING") {
          sendWsMessage({ type: "PONG" });
        }
      } catch (err) {
        console.error("[Kitsune Relay] Error parsing WS message:", err);
      }
    };

    ws.onclose = () => {
      isConnected = false;
      console.warn("[Kitsune Relay] WebSocket disconnected. Reconnecting in 3s...");
      chrome.action.setBadgeText({ text: "OFF" });
      chrome.action.setBadgeBackgroundColor({ color: "#ef4444" });
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error("[Kitsune Relay] WebSocket error:", err);
      ws.close();
    };
  } catch (err) {
    console.error("[Kitsune Relay] Failed to create WebSocket:", err);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connectWebSocket();
  }, 3000);
}

function sendWsMessage(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

// --- Find Active Target Tab (Claude.ai / ChatGPT / Target Chat) ---
async function findTargetTab() {
  try {
    const tabs = await chrome.tabs.query({});
    // Priority 1: claude.ai or chatgpt.com
    const target = tabs.find(t => t.url && (
      t.url.includes("claude.ai") || 
      t.url.includes("chatgpt.com") || 
      t.url.includes("chat.openai.com")
    ));
    if (target) {
      lastTargetTabInfo = { id: target.id, url: target.url, title: target.title };
      return target;
    }
    // Priority 2: Currently active focused tab
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (activeTab && activeTab.url && !activeTab.url.startsWith("chrome://")) {
      lastTargetTabInfo = { id: activeTab.id, url: activeTab.url, title: activeTab.title };
      return activeTab;
    }
  } catch (err) {
    console.error("[Kitsune Relay] Error querying tabs:", err);
  }
  return null;
}

// --- Handle Probe Request from Kitsune Engine ---
async function handleProbeRequest(probe) {
  const { attempt_id, round_id, payload } = probe;
  const targetTab = await findTargetTab();

  if (!targetTab) {
    console.error("[Kitsune Relay] No target tab found to execute probe!");
    sendWsMessage({
      type: "PROBE_RESPONSE",
      attempt_id: attempt_id,
      round_id: round_id,
      raw_response: "",
      status_code: 404,
      error_message: "No open Claude.ai or ChatGPT tab detected in Chrome. Please open claude.ai in a tab."
    });
    return;
  }

  console.log(`[Kitsune Relay] Forwarding probe ${attempt_id} to Tab ${targetTab.id} (${targetTab.url})`);

  try {
    // Send to content script in target tab
    chrome.tabs.sendMessage(
      targetTab.id,
      {
        type: "EXECUTE_PROBE",
        attempt_id: attempt_id,
        round_id: round_id,
        payload: payload
      },
      (response) => {
        if (chrome.runtime.lastError) {
          console.error("[Kitsune Relay] Tab message error:", chrome.runtime.lastError.message);
          sendWsMessage({
            type: "PROBE_RESPONSE",
            attempt_id: attempt_id,
            round_id: round_id,
            raw_response: "",
            status_code: 500,
            error_message: `Content script not active on tab ${targetTab.url}. Refresh the tab.`
          });
          return;
        }

        console.log(`[Kitsune Relay] Probe ${attempt_id} completed successfully from tab!`);
        sendWsMessage({
          type: "PROBE_RESPONSE",
          attempt_id: attempt_id,
          round_id: round_id,
          raw_response: response ? response.raw_response : "",
          latency_ms: response ? response.latency_ms : 0,
          refused: response ? response.refused : false,
          status_code: 200
        });
      }
    );
  } catch (err) {
    console.error("[Kitsune Relay] Error executing probe in tab:", err);
    sendWsMessage({
      type: "PROBE_RESPONSE",
      attempt_id: attempt_id,
      round_id: round_id,
      raw_response: "",
      status_code: 500,
      error_message: err.message
    });
  }
}

// --- Listen to Messages from Extension Popup ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "GET_STATUS") {
    findTargetTab().then((tab) => {
      sendResponse({
        connected: isConnected,
        wsUrl: WS_URL,
        targetTab: tab ? { id: tab.id, url: tab.url, title: tab.title } : null
      });
    });
    return true; // async sendResponse
  }
});

// Start connection on extension load
connectWebSocket();

// Periodic heartbeat & tab monitor
setInterval(async () => {
  if (!isConnected) {
    connectWebSocket();
  } else {
    const activeTab = await findTargetTab();
    sendWsMessage({
      type: "HEARTBEAT",
      active_tab: activeTab ? { id: activeTab.id, url: activeTab.url } : null
    });
  }
}, 5000);
