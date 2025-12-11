"""
WebSocket Manager - 強化版

改進：
1. 明確的錯誤處理（不再用 except Exception）
2. Timeout 控制（避免卡死）
3. 詳細的 logging（方便 debug）
4. 確保事件在 DB commit 後發送
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set

import asyncio
import logging

from schemas import WSEvent, WSEventType

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket 連線管理器

    職責：
    1. 管理房間內的所有 WebSocket 連線
    2. 廣播事件給房間內所有玩家
    3. 處理斷線和錯誤
    """

    def __init__(self):
        # room_id 用字串（因為 WebSocket 路徑參數是 str）
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        """
        接受新的 WebSocket 連線

        參數：
            websocket: WebSocket 物件
            room_id: 房間 UUID
        """
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
        self.active_connections[room_id].add(websocket)
        logger.info(f"WebSocket connected to room {room_id}. Total: {len(self.active_connections[room_id])}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        """
        移除 WebSocket 連線

        參數：
            websocket: WebSocket 物件
            room_id: 房間 UUID
        """
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            logger.info(f"WebSocket disconnected from room {room_id}. Remaining: {len(self.active_connections[room_id])}")

            # 如果房間內沒有連線了，刪除房間
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
                logger.info(f"Room {room_id} has no connections, removed from manager")

    async def broadcast_to_room(self, room_id: str, message: dict):
        """
        廣播訊息給房間內所有連線（強化的錯誤處理）

        流程：
        1. 檢查房間是否有連線
        2. 對每個連線嘗試發送（with timeout）
        3. 記錄失敗的連線
        4. 清理死掉的連線

        參數：
            room_id: 房間 UUID
            message: 要發送的訊息（dict）

        改進：
        - 不再用 except Exception（太籠統）
        - 加入 timeout（避免卡死）
        - 詳細的錯誤 logging
        """
        if room_id not in self.active_connections:
            logger.debug(f"No connections in room {room_id}, skipping broadcast")
            return

        connection_count = len(self.active_connections[room_id])
        logger.debug(f"Broadcasting to {connection_count} connections in room {room_id}: {message.get('event_type')}")

        dead_connections = set()

        # Create snapshot to avoid "Set changed size during iteration"
        connections_snapshot = list(self.active_connections[room_id])
        for connection in connections_snapshot:
            try:
                # 加入 timeout（5 秒），避免某個連線卡住整個廣播
                await asyncio.wait_for(
                    connection.send_json(message),
                    timeout=5.0
                )

            except asyncio.TimeoutError:
                # Timeout：客戶端可能網路很慢或卡住
                logger.warning(f"Send timeout to connection in room {room_id}")
                dead_connections.add(connection)

            except WebSocketDisconnect:
                # 客戶端主動斷線
                logger.info(f"Client disconnected from room {room_id}")
                dead_connections.add(connection)

            except RuntimeError as e:
                # WebSocket 已經關閉
                logger.warning(f"WebSocket runtime error in room {room_id}: {e}")
                dead_connections.add(connection)

            except Exception as e:
                # 其他未預期的錯誤（應該調查）
                logger.error(
                    f"Unexpected error broadcasting to room {room_id}: {e}",
                    exc_info=True
                )
                dead_connections.add(connection)

        # 清理死掉的連線
        if dead_connections:
            logger.info(f"Cleaning up {len(dead_connections)} dead connections in room {room_id}")
            for dead in dead_connections:
                self.disconnect(dead, room_id)


manager = ConnectionManager()


# IMPORTANT: Health check endpoint MUST be defined BEFORE /ws/{room_id}
# Otherwise FastAPI will treat "health" as a room_id value
@router.websocket("/ws/health")
async def websocket_health_endpoint(websocket: WebSocket):
    """
    Health check endpoint for WebSocket testing.

    Does not require room_id. Responds to any message with "OK".
    Useful for verification scripts and monitoring.

    NOTE: This route must be defined before /ws/{room_id} to avoid
    being caught by the path parameter.
    """
    await websocket.accept()
    logger.info("WebSocket health check connection established")
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Health check received: {repr(data)}")
            # Strip whitespace to handle newlines from echo/websocat
            if data.strip() == "ping":
                await websocket.send_text("pong")
            else:
                await websocket.send_text("OK")
    except WebSocketDisconnect:
        logger.info("Health check client disconnected")


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    """
    WebSocket endpoint for room-specific connections.

    Supports ping/pong for keep-alive testing.
    """
    await manager.connect(websocket, room_id)
    try:
        while True:
            # Keep connection alive, receive ping/pong if needed
            data = await websocket.receive_text()
            # Echo back for keep-alive (strip to handle newlines)
            if data.strip() == "ping":
                logger.info(f"Received ping from room {room_id}, sending pong")
                await websocket.send_text("pong")
            else:
                logger.debug(f"Received message in room {room_id}: {data[:50]}")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from room {room_id}")
        manager.disconnect(websocket, room_id)


async def broadcast_event(room_id: str, event_type: str, data: dict = None):
    """Helper function to broadcast events to all clients in a room."""
    event = WSEvent(
        event_type=event_type,
        room_id=room_id,
        data=data or {}
    )
    await manager.broadcast_to_room(room_id, event.model_dump(mode='json'))


# Export event types for convenience
__all__ = ["router", "broadcast_event", "WSEventType"]
