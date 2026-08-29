import asyncio
import json
from typing import Optional

from fastapi import WebSocket

from .config import get_settings

settings = get_settings()

REDIS_CHANNEL = "aquaalert:zone_updates"


class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self._redis = None
        self._redis_task: Optional[asyncio.Task] = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active_connections.discard(ws)

    async def _local_broadcast(self, message: dict):
        dead = []
        payload = json.dumps(message)
        for conn in self.active_connections:
            try:
                await conn.send_text(payload)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

    async def broadcast(self, message: dict):
        
        await self._local_broadcast(message)
        if settings.use_redis:
            await self._ensure_redis()
            if self._redis:
                await self._redis.publish(REDIS_CHANNEL, json.dumps(message))

    async def _ensure_redis(self):
        if self._redis is not None:
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            if self._redis_task is None:
                self._redis_task = asyncio.create_task(self._redis_listener())
        except Exception:
            self._redis = None

    async def _redis_listener(self):
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(REDIS_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
            except Exception:
                continue
    
            await self._local_broadcast(data)


manager = ConnectionManager()
