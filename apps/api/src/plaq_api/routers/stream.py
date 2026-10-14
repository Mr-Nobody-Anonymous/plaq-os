"""Real-time WebSocket and SSE event streaming endpoints for Plaq-OS API."""

from __future__ import annotations

import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

from plaq_api.deps import get_broadcaster
from plaq_api.events import EventBroadcaster

router = APIRouter(tags=["Streaming"])


@router.get("/api/v1/events/stream")
async def stream_events_sse(
    task_id: Optional[str] = Query(default=None, description="Optional task ID filter"),
    broadcaster: EventBroadcaster = Depends(get_broadcaster),
):
    """Server-Sent Events (SSE) streaming endpoint."""
    async def sse_generator():
        queue = broadcaster.subscribe()
        try:
            # Yield initial connection heartbeat
            connect_msg = {"event_type": "connected", "message": "Plaq-OS Event Stream connected"}
            yield f"data: {json.dumps(connect_msg)}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if task_id and event.get("task_id") != task_id:
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive heartbeat ping
                    yield "data: {\"event_type\": \"ping\"}\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/stream")
@router.websocket("/api/v1/ws")
async def websocket_stream(
    websocket: WebSocket,
    broadcaster: EventBroadcaster = Depends(get_broadcaster),
):
    """Bidirectional WebSocket connection for live telemetry and task interaction."""
    await websocket.accept()
    broadcaster.register_ws(websocket)
    try:
        await websocket.send_json({
            "event_type": "welcome",
            "message": "Plaq-OS Workbench WebSocket connected",
            "status": "connected",
        })
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                # Echo or handle incoming messages (e.g. ping/pong or client subscription)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "time": msg.get("time")})
            except Exception:
                pass
    except WebSocketDisconnect:
        broadcaster.unregister_ws(websocket)
    except Exception:
        broadcaster.unregister_ws(websocket)
