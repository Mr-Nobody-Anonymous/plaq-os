"""Real-time event broadcasting and streaming engine for Plaq-OS."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from starlette.websockets import WebSocket

from plaq_contracts.event import EventType, PlatformEvent


class EventBroadcaster:
    """Async event bus supporting multi-subscriber fanout, WebSocket streaming, and SSE."""

    def __init__(self, max_history: int = 500):
        self.max_history = max_history
        self._history: List[Dict[str, Any]] = []
        self._subscribers: Set[asyncio.Queue] = set()
        self._ws_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def events(self) -> List[Dict[str, Any]]:
        """Return history of recorded events."""
        return list(self._history)

    def record(self, event_data: Dict[str, Any]) -> None:
        """Synchronously record an event into history (for testing or synchronous loggers)."""
        self._history.append(event_data)
        if len(self._history) > self.max_history:
            self._history.pop(0)

    def filter(self, task_id: Optional[str] = None, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Filter recorded events by task_id and/or event_type."""
        filtered = self._history
        if task_id:
            filtered = [e for e in filtered if e.get("task_id") == task_id]
        if event_type:
            filtered = [e for e in filtered if e.get("event_type") == event_type]
        return filtered

    async def broadcast(self, event: PlatformEvent) -> None:
        """Broadcast platform event to all active SSE queues and WebSocket clients."""
        event_dict = event.model_dump(mode="json")
        self.record(event_dict)

        # Dispatch to SSE queues
        for q in list(self._subscribers):
            try:
                q.put_nowait(event_dict)
            except asyncio.QueueFull:
                pass

        # Dispatch to active WebSockets
        dead_ws = set()
        for ws in list(self._ws_connections):
            try:
                await ws.send_json(event_dict)
            except Exception:
                dead_ws.add(ws)

        for ws in dead_ws:
            self._ws_connections.discard(ws)

    def subscribe(self) -> asyncio.Queue:
        """Create a new subscriber queue receiving future broadcast events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        self._subscribers.discard(q)

    def register_ws(self, ws: WebSocket) -> None:
        """Register active WebSocket connection."""
        self._ws_connections.add(ws)

    def unregister_ws(self, ws: WebSocket) -> None:
        """Unregister closed WebSocket connection."""
        self._ws_connections.discard(ws)


# Global singleton instance
broadcaster = EventBroadcaster()
