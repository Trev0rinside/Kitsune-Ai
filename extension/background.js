/**
 * Kitsune Guardrail Relay - Background Service Worker
 * Universal WebSocket bridge between Kitsune Python engine and ANY target web chat / AI agent portal.
 * 100% domain-agnostic: Supports custom enterprise endpoints, internal intranet portals, and public SUTs.
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
        version: "1.2.0",
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

function isInternalBrowserUrl(url) {
  if (!url) return true;
  return (
    url.startsWith("chrome://") ||
    url.startsWith("chrome-extension://") ||
    url.startsWith("edge://") ||
    url.startsWith("about:") ||
    url.startsWith("devtools://")
  );
}

// --- Dynamic Universal Tab Resolver (Domain Agnostic) ---
async function findTargetTab(requestedTargetUrl = null) {
  try {
    const tabs = await chrome.tabs.query({});

    // 1. Target URL specified by user in dashboard (Enterprise custom portal / local port / specific domain)
    if (requestedTargetUrl && typeof requestedTargetUrl === "string" && requestedTargetUrl.trim().length > 0) {
      try {
        let cleanReq = requestedTargetUrl.trim().toLowerCase();
        let targetHost = cleanReq;
        if (cleanReq.startsWith("http://") || cleanReq.startsWith("https://")) {
          targetHost = new URL(cleanReq).hostname.replace(/^www\./, "");
        }
        
        const matched = tabs.find(t => {
          if (!t.url || isInternalBrowserUrl(t.url)) return false;
          const tUrl = t.url.toLowerCase();
          return tUrl.includes(targetHost) || tUrl.includes(cleanReq);
        });

        if (matched) {
          lastTargetTabInfo = { id: matched.id, url: matched.url, title: matched.title };
          return matched;
        }
      } catch (e) {
        console.warn("[Kitsune Relay] Target URL matching warning:", e);
      }
    }

    // 2. Currently focused/active tab where the security tester is currently positioned
    const activeTabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (activeTabs.length > 0 && activeTabs[0].url && !isInternalBrowserUrl(activeTabs[0].url)) {
      const activeTab = activeTabs[0];
      lastTargetTabInfo = { id: activeTab.id, url: activeTab.url, title: activeTab.title };
      return activeTab;
    }

    // 3. Active tab in any Chrome window
    const [anyActiveTab] = await chrome.tabs.query({ active: true });
    if (anyActiveTab && anyActiveTab.url && !isInternalBrowserUrl(anyActiveTab.url)) {
      lastTargetTabInfo = { id: anyActiveTab.id, url: anyActiveTab.url, title: anyActiveTab.title };
      return anyActiveTab;
    }

    // 4. Any valid non-internal web tab
    const fallbackTab = tabs.find(t => t.url && !isInternalBrowserUrl(t.url));
    if (fallbackTab) {
      lastTargetTabInfo = { id: fallbackTab.id, url: fallbackTab.url, title: fallbackTab.title };
      return fallbackTab;
    }
  } catch (err) {
    console.error("[Kitsune Relay] Error querying tabs:", err);
  }
  return null;
}

// --- Handle Probe Request from Kitsune Engine ---
async function handleProbeRequest(probe) {
  const { attempt_id, round_id, payload, target_url } = probe;
  const targetTab = await findTargetTab(target_url);

  if (!targetTab) {
    console.error("[Kitsune Relay] No target tab found to execute probe!");
    sendWsMessage({
      type: "PROBE_RESPONSE",
      attempt_id: attempt_id,
      round_id: round_id,
      raw_response: "",
      status_code: 404,
      error_message: "No open target tab detected in Chrome. Please navigate to your AI agent chat interface in a Chrome tab."
    });
    return;
  }

  console.log(`[Kitsune Relay] Forwarding probe ${attempt_id} to Tab ${targetTab.id} (${targetTab.url})`);

  async function sendToContentScript(retryOnMissing = true) {
    chrome.tabs.sendMessage(
      targetTab.id,
      {
        type: "EXECUTE_PROBE",
        attempt_id: attempt_id,
        round_id: round_id,
        payload: payload
      },
      async (response) => {
        if (chrome.runtime.lastError) {
          const errMsg = chrome.runtime.lastError.message || "";
          console.warn("[Kitsune Relay] Tab message error:", errMsg);

          if (retryOnMissing && (errMsg.includes("Receiving end does not exist") || errMsg.includes("Could not establish connection"))) {
            try {
              console.log("[Kitsune Relay] Dynamically injecting content.js into tab", targetTab.id);
              await chrome.scripting.executeScript({
                target: { tabId: targetTab.id },
                files: ["content.js"]
              });
              await new Promise(r => setTimeout(r, 400));
              return sendToContentScript(false);
            } catch (injErr) {
              console.error("[Kitsune Relay] Dynamic script injection failed:", injErr);
            }
          }

          sendWsMessage({
            type: "PROBE_RESPONSE",
            attempt_id: attempt_id,
            round_id: round_id,
            raw_response: "",
            status_code: 500,
            error_message: `Content script not ready on tab ${targetTab.url}. Please refresh the tab.`
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
  }

  sendToContentScript(true);
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
}, 4000);
