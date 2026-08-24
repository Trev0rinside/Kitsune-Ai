"""Extension Relay Manager: WebSocket bridge coordinator between Python Engine and Chrome Extension."""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from fastapi import WebSocket
from reverse_guardrail.core.logger import logger


class ExtensionRelayManager:
    """Manages active Chrome Extension WebSocket connections and dispatches probe tasks."""

    _instance: Optional["ExtensionRelayManager"] = None

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._pending_probes: Dict[str, asyncio.Future] = {}
        self.last_known_target_tab: Optional[Dict[str, Any]] = None
        self.last_heartbeat_time: float = 0.0

    @classmethod
    def get_instance(cls) -> "ExtensionRelayManager":
        if cls._instance is None:
            cls._instance = ExtensionRelayManager()
        return cls._instance

    async def register(self, websocket: WebSocket) -> None:
        """Register a newly connected Chrome Extension client."""
        self.active_connections.append(websocket)
        self.last_heartbeat_time = time.monotonic()
        logger.info(f"[ExtensionRelay] Chrome Extension connected! Total clients: {len(self.active_connections)}")

    async def unregister(self, websocket: WebSocket) -> None:
        """Unregister a disconnected Chrome Extension client."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[ExtensionRelay] Chrome Extension disconnected. Remaining clients: {len(self.active_connections)}")

    def is_connected(self) -> bool:
        """Returns true if at least one Chrome Extension client is actively connected."""
        return len(self.active_connections) > 0

    def get_status(self) -> Dict[str, Any]:
        """Returns JSON-serializable status report of the extension relay."""
        return {
            "connected": self.is_connected(),
            "clients_count": len(self.active_connections),
            "target_tab": self.last_known_target_tab,
            "last_heartbeat_seconds_ago": round(time.monotonic() - self.last_heartbeat_time, 1) if self.last_heartbeat_time else None
        }

    async def handle_incoming_message(self, data_str: str) -> None:
        """Process messages received from the Chrome Extension over WebSocket."""
        try:
            msg = json.loads(data_str)
            msg_type = msg.get("type")

            if msg_type == "HANDSHAKE" or msg_type == "HEARTBEAT":
                self.last_heartbeat_time = time.monotonic()
                if "active_tab" in msg and msg["active_tab"]:
                    self.last_known_target_tab = msg["active_tab"]

            elif msg_type == "PROBE_RESPONSE":
                attempt_id = msg.get("attempt_id")
                if attempt_id and attempt_id in self._pending_probes:
                    future = self._pending_probes[attempt_id]
                    if not future.done():
                        future.set_result(msg)

        except Exception as err:
            logger.error(f"[ExtensionRelay] Error handling message from extension: {err}")

    async def dispatch_probe(
        self, attempt_id: str, round_id: int, payload: str, timeout_seconds: float = 60.0
    ) -> Dict[str, Any]:
        """Dispatch a probe prompt to the connected Chrome Extension and await result."""
        if not self.is_connected():
            raise RuntimeError(
                "No Chrome Extension connected. Please open Chrome, make sure the Kitsune Extension is loaded, "
                "and ensure a tab with claude.ai or chatgpt.com is open."
            )

        ws = self.active_connections[-1] # Use latest active connection
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_probes[attempt_id] = future

        request_data = {
            "type": "PROBE_REQUEST",
            "attempt_id": attempt_id,
            "round_id": round_id,
            "payload": payload,
        }

        try:
            logger.info(f"[ExtensionRelay] Sending probe [{attempt_id}] to Chrome Extension over WebSocket...")
            await ws.send_text(json.dumps(request_data))

            result = await asyncio.wait_for(future, timeout=timeout_seconds)
            return result

        except asyncio.TimeoutError:
            logger.error(f"[ExtensionRelay] Probe [{attempt_id}] timed out waiting for response from Chrome Extension.")
            return {
                "attempt_id": attempt_id,
                "round_id": round_id,
                "raw_response": "",
                "latency_ms": timeout_seconds * 1000.0,
                "refused": False,
                "status_code": 504,
                "error_message": f"Timeout waiting for Chrome tab response ({timeout_seconds}s)."
            }
        finally:
            self._pending_probes.pop(attempt_id, None)


# Global singleton instance
relay_manager = ExtensionRelayManager.get_instance()
