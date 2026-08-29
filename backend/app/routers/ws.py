"""
WebSocket endpoint. Clients connect once and receive a `zone_update` event
every time any zone's score/status changes -- no polling required.

Message shape (see schemas.ZoneUpdateEvent):
    {
      "type": "zone_update",
      "zone_id": "...",
      "code": "WARD-12",
      "name": "Koramangala",
      "score": 72.4,
      "status": "severe",
      "status_changed": true,
      "updated_at": "2026-08-28T10:15:00Z"
    }
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..websocket_manager import manager

router = APIRouter()


@router.websocket("/ws/zones")
async def zones_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect inbound messages, but we still need to await
            # receive to detect disconnects; ping/pong keepalive also lands here.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
