"""
狀態機：集中管理所有狀態轉換

Linus 原則：
1. 「好品味」- 所有狀態轉換在一個地方，消除特殊情況
2. 「單一職責」- 狀態機只負責狀態轉換，不負責業務邏輯
3. 「資料結構優先」- 用字典定義所有合法轉換，一目了然

這個模組確保：
- 所有狀態變更必須經過這裡（集中控制）
- 非法的狀態轉換會立刻報錯（fail fast）
- 所有狀態變更都會被記錄到 Event Log（可追蹤）
"""
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
import logging

from models import Room, Round, RoomStatus, RoundStatus, EventLog
from core.locks import with_room_lock, with_round_lock
from core.exceptions import (
    RoomNotFound,
    RoundNotFound,
    InvalidStateTransition
)

logger = logging.getLogger(__name__)


class RoomStateMachine:
    """
    Room 狀態機

    狀態流程：
        WAITING (等待玩家) → PLAYING (遊戲中) → FINISHED (結束)

    規則：
    - WAITING 只能轉到 PLAYING
    - PLAYING 只能轉到 FINISHED
    - FINISHED 是終點（不能再轉換）
    """

    # 定義所有合法的狀態轉換（資料結構優先！）
    VALID_TRANSITIONS = {
        RoomStatus.WAITING: [RoomStatus.PLAYING],
        RoomStatus.PLAYING: [RoomStatus.FINISHED],
        RoomStatus.FINISHED: []  # 終點：無法再轉換
    }

    @staticmethod
    def can_transition(from_status: RoomStatus, to_status: RoomStatus) -> bool:
        """
        檢查是否可以進行狀態轉換（不實際執行）

        用途：
        - API 層可以先檢查是否可以轉換，再決定是否執行
        - 前端可以呼叫此邏輯來判斷按鈕是否該顯示

        參數：
            from_status: 當前狀態
            to_status: 目標狀態

        返回：
            True 如果可以轉換，False 否則
        """
        return to_status in RoomStateMachine.VALID_TRANSITIONS.get(from_status, [])

    @staticmethod
    def transition(room_id: UUID, to_status: RoomStatus, db: Session) -> Room:
        """
        執行狀態轉換（唯一修改 Room.status 的地方）

        流程：
        1. 鎖定 Room（防止並發修改）
        2. 檢查當前狀態是否可以轉換到目標狀態
        3. 執行轉換
        4. 記錄 Event Log
        5. Commit（由外層 transaction 處理）

        參數：
            room_id: Room 的 UUID
            to_status: 目標狀態
            db: SQLAlchemy Session

        返回：
            更新後的 Room object

        異常：
            RoomNotFound: Room 不存在
            InvalidStateTransition: 非法的狀態轉換
        """
        # 1. 鎖定 Room（使用悲觀鎖，防止並發）
        room = with_room_lock(room_id, db).first()
        if not room:
            raise RoomNotFound(room_id)

        from_status = room.status

        # 2. 檢查是否為合法轉換
        if not RoomStateMachine.can_transition(from_status, to_status):
            raise InvalidStateTransition(
                f"Cannot transition Room {room_id} from {from_status.value} to {to_status.value}. "
                f"Valid transitions from {from_status.value}: "
                f"{[s.value for s in RoomStateMachine.VALID_TRANSITIONS[from_status]]}"
            )

        # 3. 執行轉換
        logger.info(f"Room {room_id} state transition: {from_status.value} -> {to_status.value}")
        room.status = to_status
        room.updated_at = datetime.utcnow()

        # 4. 記錄 Event Log（用於 audit trail 和事件補發）
        event = EventLog(
            room_id=room_id,
            event_type="ROOM_STATE_CHANGED",
            data={
                "from": from_status.value,
                "to": to_status.value,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        db.add(event)

        # 5. 不要在這裡 commit，讓外層的 transaction 處理
        return room


class RoundStateMachine:
    """
    Round 狀態機

    狀態流程：
        WAITING_ACTIONS (等待玩家提交動作)
        → CALCULATING (計算結果中)
        → READY_TO_PUBLISH (結果已計算，等待管理員公布)
        → COMPLETED (完成)

    規則：
    - WAITING_ACTIONS 只能轉到 CALCULATING
    - CALCULATING 只能轉到 READY_TO_PUBLISH
    - READY_TO_PUBLISH 只能轉到 COMPLETED
    - COMPLETED 是終點（不能再轉換）

    注意：
    - 從 WAITING_ACTIONS 到 CALCULATING 必須確保所有玩家都提交了動作
    - 從 CALCULATING 到 READY_TO_PUBLISH 必須確保結果已經計算完畢
    - 從 READY_TO_PUBLISH 到 COMPLETED 由管理員手動觸發
    - 這些檢查由 RoundManager 負責，狀態機只負責轉換
    """

    # 定義所有合法的狀態轉換
    VALID_TRANSITIONS = {
        RoundStatus.WAITING_ACTIONS: [RoundStatus.CALCULATING],
        RoundStatus.CALCULATING: [RoundStatus.READY_TO_PUBLISH],
        RoundStatus.READY_TO_PUBLISH: [RoundStatus.COMPLETED],
        RoundStatus.COMPLETED: []  # 終點
    }

    @staticmethod
    def can_transition(from_status: RoundStatus, to_status: RoundStatus) -> bool:
        """
        檢查是否可以進行狀態轉換（不實際執行）
        """
        return to_status in RoundStateMachine.VALID_TRANSITIONS.get(from_status, [])

    @staticmethod
    def transition(round_id: UUID, to_status: RoundStatus, db: Session) -> Round:
        """
        執行狀態轉換（唯一修改 Round.status 的地方）

        流程：
        1. 鎖定 Round（防止並發修改）
        2. 檢查當前狀態是否可以轉換到目標狀態
        3. 執行轉換
        4. 更新版本號（樂觀鎖）
        5. 記錄 Event Log

        參數：
            round_id: Round 的 UUID
            to_status: 目標狀態
            db: SQLAlchemy Session

        返回：
            更新後的 Round object

        異常：
            RoundNotFound: Round 不存在
            InvalidStateTransition: 非法的狀態轉換
        """
        # 1. 鎖定 Round
        round_obj = with_round_lock(round_id, db).first()
        if not round_obj:
            raise RoundNotFound(round_id)

        from_status = round_obj.status

        # 2. 檢查是否為合法轉換
        if not RoundStateMachine.can_transition(from_status, to_status):
            raise InvalidStateTransition(
                f"Cannot transition Round {round_id} from {from_status.value} to {to_status.value}. "
                f"Valid transitions from {from_status.value}: "
                f"{[s.value for s in RoundStateMachine.VALID_TRANSITIONS[from_status]]}"
            )

        # 3. 執行轉換
        logger.info(
            f"Round {round_id} (room={round_obj.room_id}, round_number={round_obj.round_number}) "
            f"state transition: {from_status.value} -> {to_status.value}"
        )
        round_obj.status = to_status

        # 4. 更新版本號（用於樂觀鎖，雖然我們用的是悲觀鎖）
        round_obj.version += 1

        # 5. 記錄結束時間（如果轉換到 COMPLETED）
        if to_status == RoundStatus.COMPLETED:
            round_obj.ended_at = datetime.utcnow()

        # 6. 記錄 Event Log
        event = EventLog(
            room_id=round_obj.room_id,
            event_type="ROUND_STATE_CHANGED",
            data={
                "round_id": str(round_id),
                "round_number": round_obj.round_number,
                "from": from_status.value,
                "to": to_status.value,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        db.add(event)

        return round_obj
