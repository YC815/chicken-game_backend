"""
Room API Endpoints

職責：
1. HTTP 請求/回應處理
2. 參數驗證
3. 呼叫 RoomManager
4. 錯誤轉換（業務異常 -> HTTP 異常）
5. 觸發 WebSocket 通知

不負責：
- 業務邏輯（由 RoomManager 負責）
- 狀態轉換（由 StateMachine 負責）
- 資料驗證（由 Manager 負責）
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import asyncio
import logging

from database import get_db
from models import EventLog
from schemas import (
    RoomCreate,
    RoomResponse,
    RoomStatusResponse,
    GameSummaryResponse,
    PlayerSummary,
    GameStats
)
from core.room_manager import RoomManager
from core.round_manager import RoundManager
from core.exceptions import (
    RoomNotFound,
    InvalidPlayerCount,
    InvalidStateTransition,
    MaxRoundsReached
)
from services.payoff_service import calculate_total_payoff
from api.websocket import broadcast_event, WSEventType

router = APIRouter(prefix="/api/rooms", tags=["rooms"])
logger = logging.getLogger(__name__)


@router.post("", response_model=RoomResponse)
def create_room(room_create: RoomCreate, db: Session = Depends(get_db)):
    """
    建立新房間（Host endpoint）

    流程：
    1. 呼叫 RoomManager.create_room()
    2. 返回房間資訊（含 room_id, code, host_player_id）

    返回：
        - room_id: 房間 UUID
        - code: 6 位房間代碼（用於其他玩家加入）
        - host_player_id: Host 玩家的 UUID
    """
    try:
        room, host = RoomManager.create_room(db)

        return RoomResponse(
            room_id=room.id,
            code=room.code,
            host_player_id=host.id
        )

    except Exception as e:
        logger.error(f"Failed to create room: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create room")


@router.get("/{code}", response_model=RoomStatusResponse)
def get_room_status(code: str, db: Session = Depends(get_db)):
    """
    取得房間狀態（透過房間代碼）

    用途：
    - 前端顯示房間資訊
    - 檢查房間是否存在
    - 查詢玩家數量

    參數：
        code: 6 位房間代碼

    返回：
        - room_id: 房間 UUID
        - code: 房間代碼
        - status: 房間狀態（waiting/playing/finished）
        - current_round: 當前回合數（0-10）
        - player_count: 玩家數量（不含 Host）
    """
    try:
        room = RoomManager.get_room_by_code(db, code)
        player_count = RoomManager.get_player_count(db, room.id)

        return RoomStatusResponse(
            room_id=room.id,
            code=room.code,
            status=room.status,
            current_round=room.current_round,
            player_count=player_count
        )

    except RoomNotFound:
        raise HTTPException(status_code=404, detail="Room not found")
    except Exception as e:
        logger.error(f"Failed to get room status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{room_id}/start")
async def start_game(room_id: UUID, db: Session = Depends(get_db)):
    """
    開始遊戲（Host endpoint）

    前置條件：
    - 房間狀態必須是 WAITING
    - 玩家數量必須 >= 2 且為偶數

    流程：
    1. 呼叫 RoomManager.start_game()
    2. 自動建立第一輪（Round 1）
    3. 非同步發送 WebSocket 通知（ROOM_STARTED + ROUND_STARTED）
    4. 返回成功

    注意：
    - WebSocket 通知是非阻塞的（使用 asyncio.create_task）
    - 確保 DB commit 完成後才發送通知
    - 自動建立第一輪，消除 current_round=0 的中間狀態
    """
    try:
        # 1. 開始遊戲（業務邏輯）
        RoomManager.start_game(db, room_id)

        # 2. 立即建立第一輪（消除 current_round=0 的中間狀態）
        first_round = RoundManager.create_round(db, room_id)

        # 3. 發送 WebSocket 通知（非阻塞）
        asyncio.create_task(
            _notify_room_started(room_id)
        )
        asyncio.create_task(
            _notify_round_started(room_id, first_round.round_number, first_round.phase.value)
        )

        return {"status": "ok"}

    except RoomNotFound:
        raise HTTPException(status_code=404, detail="Room not found")
    except InvalidPlayerCount as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MaxRoundsReached as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start game: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{room_id}/rounds/next")
async def next_round(room_id: UUID, db: Session = Depends(get_db)):
    """
    開始下一回合（Host endpoint）

    前置條件：
    - 房間狀態必須是 PLAYING
    - 當前回合數 < 10

    流程：
    1. 呼叫 RoundManager.create_round()
    2. 非同步發送 WebSocket 通知（ROUND_STARTED）
    3. 返回回合資訊

    返回：
        - status: "ok"
        - round_number: 新回合的回合數
    """
    try:
        # 1. 建立新回合（含配對）
        new_round = RoundManager.create_round(db, room_id)

        # 2. 發送 WebSocket 通知（非阻塞）
        asyncio.create_task(
            _notify_round_started(room_id, new_round.round_number, new_round.phase.value)
        )

        return {
            "status": "ok",
            "round_number": new_round.round_number
        }

    except RoomNotFound:
        raise HTTPException(status_code=404, detail="Room not found")
    except MaxRoundsReached:
        raise HTTPException(status_code=400, detail="All rounds completed")
    except InvalidPlayerCount as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create next round: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{room_id}/end")
async def end_game(room_id: UUID, db: Session = Depends(get_db)):
    """
    結束遊戲（Host endpoint）

    前置條件：
    - 房間狀態必須是 PLAYING

    流程：
    1. 呼叫 RoomManager.end_game()
    2. 非同步發送 WebSocket 通知（GAME_ENDED）
    3. 返回成功
    """
    try:
        # 1. 結束遊戲（業務邏輯）
        RoomManager.end_game(db, room_id)

        # 2. 發送 WebSocket 通知（非阻塞）
        asyncio.create_task(
            _notify_game_ended(room_id)
        )

        return {"status": "ok"}

    except RoomNotFound:
        raise HTTPException(status_code=404, detail="Room not found")
    except InvalidStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to end game: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{room_id}/summary", response_model=GameSummaryResponse)
def get_game_summary(room_id: UUID, db: Session = Depends(get_db)):
    """
    取得遊戲摘要（排名和統計）

    用途：
    - 遊戲結束後顯示最終結果
    - 顯示玩家排名
    - 顯示整體策略統計

    返回：
        - players: 玩家列表（按總分排序）
            - display_name: 顯示名稱
            - total_payoff: 總分
        - stats: 整體統計
            - accelerate_ratio: 加速比例
            - turn_ratio: 轉向比例
    """
    from models import Player, Action, Choice

    try:
        # 1. 檢查房間是否存在
        room = RoomManager.get_room_by_id(db, room_id)

        # 2. 取得所有玩家
        players = db.query(Player).filter(
            Player.room_id == room_id,
            Player.is_host == False
        ).all()

        # 3. 計算每個玩家的總分
        player_summaries = []
        for player in players:
            total_payoff = calculate_total_payoff(player.id, db)
            player_summaries.append(PlayerSummary(
                display_name=player.display_name,
                total_payoff=total_payoff
            ))

        # 4. 排序（總分由高到低）
        player_summaries.sort(key=lambda x: x.total_payoff, reverse=True)

        # 5. 計算策略統計
        total_actions = db.query(Action).filter(Action.room_id == room_id).count()
        accelerate_count = db.query(Action).filter(
            Action.room_id == room_id,
            Action.choice == Choice.ACCELERATE
        ).count()

        accelerate_ratio = accelerate_count / total_actions if total_actions > 0 else 0
        turn_ratio = 1 - accelerate_ratio

        stats = GameStats(
            accelerate_ratio=round(accelerate_ratio, 2),
            turn_ratio=round(turn_ratio, 2)
        )

        return GameSummaryResponse(players=player_summaries, stats=stats)

    except RoomNotFound:
        raise HTTPException(status_code=404, detail="Room not found")
    except Exception as e:
        logger.error(f"Failed to get game summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/{room_id}/events/since/{last_event_id}")
def get_events_since(
    room_id: UUID,
    last_event_id: int,
    db: Session = Depends(get_db)
):
    """
    取得指定事件 ID 之後的所有事件

    用途：
    - WebSocket 斷線後重連，補發遺漏的事件
    - 前端可以用此 API 確保不會漏掉任何狀態變更

    參數：
        room_id: 房間 UUID
        last_event_id: 最後收到的事件 ID

    返回：
        - events: 事件列表
            - event_id: 事件 ID
            - event_type: 事件類型
            - data: 事件資料
            - created_at: 建立時間

    範例：
        如果客戶端最後收到 event_id=100，
        呼叫 /rooms/{room_id}/events/since/100
        會返回 event_id > 100 的所有事件
    """
    try:
        # 限制返回數量，避免一次返回太多
        MAX_EVENTS = 100

        events = db.query(EventLog).filter(
            EventLog.room_id == room_id,
            EventLog.id > last_event_id
        ).order_by(EventLog.id).limit(MAX_EVENTS).all()

        return {
            "events": [
                {
                    "event_id": e.id,
                    "event_type": e.event_type,
                    "data": e.data,
                    "created_at": e.created_at.isoformat()
                }
                for e in events
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


# ============ WebSocket 通知輔助函式 ============
# 這些函式確保 WebSocket 通知在 DB commit 之後發送

async def _notify_room_started(room_id: UUID):
    """發送「遊戲開始」通知"""
    await asyncio.sleep(0)  # 讓出控制權，確保 DB commit 完成
    await broadcast_event(room_id, WSEventType.ROOM_STARTED, {})


async def _notify_round_started(room_id: UUID, round_number: int, phase: str):
    """發送「回合開始」通知"""
    await asyncio.sleep(0)
    await broadcast_event(room_id, WSEventType.ROUND_STARTED, {
        "round_number": round_number,
        "phase": phase
    })


async def _notify_game_ended(room_id: UUID):
    """發送「遊戲結束」通知"""
    await asyncio.sleep(0)
    await broadcast_event(room_id, WSEventType.GAME_ENDED, {})
