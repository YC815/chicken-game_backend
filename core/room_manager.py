"""
Room Manager：管理 Room 的完整生命週期

職責：
1. 建立 Room（含 Host player）
2. 開始遊戲（狀態轉換 + 驗證）
3. 結束遊戲
4. 查詢 Room 資訊

Linus 原則：
- 單一職責：只管 Room，不管 Round
- 消除特殊情況：所有狀態變更經過 StateMachine
- 資料結構優先：先檢查資料是否符合要求，再執行操作
"""
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Tuple
import logging

from models import Room, Player, RoomStatus, EventLog
from core.state_machine import RoomStateMachine
from core.locks import with_room_lock
from core.exceptions import (
    RoomNotFound,
    InvalidPlayerCount,
    InvalidStateTransition
)
from services.naming_service import generate_room_code
from database import transactional

logger = logging.getLogger(__name__)


class RoomManager:
    """Room 生命週期管理器"""

    @staticmethod
    @transactional
    def create_room(db: Session) -> Tuple[Room, Player]:
        """
        建立新房間（含 Host 玩家）

        流程：
        1. 生成唯一的房間代碼
        2. 建立 Room
        3. 建立 Host Player
        4. 記錄事件

        參數：
            db: SQLAlchemy Session

        返回：
            (Room, Host Player) tuple

        注意：
            - 使用 @transactional，自動處理 commit/rollback
            - Room code 碰撞機率極低（26^6），但仍會檢查唯一性
        """
        # 1. 生成唯一的房間代碼
        code = generate_room_code()
        while db.query(Room).filter(Room.code == code).first():
            code = generate_room_code()
            logger.warning(f"Room code collision detected, regenerating: {code}")

        # 2. 建立 Room
        room = Room(code=code, status=RoomStatus.WAITING)
        db.add(room)
        db.flush()  # 取得 room.id

        logger.info(f"Created room {room.id} with code {code}")

        # 3. 建立 Host Player
        host = Player(
            room_id=room.id,
            nickname="Host",
            display_name="Host",
            is_host=True
        )
        db.add(host)

        # 4. 記錄事件
        event = EventLog(
            room_id=room.id,
            event_type="ROOM_CREATED",
            data={"code": code}
        )
        db.add(event)

        # transactional decorator 會自動 commit
        return room, host

    @staticmethod
    @transactional
    def start_game(db: Session, room_id: UUID) -> Room:
        """
        開始遊戲（狀態轉換 WAITING -> PLAYING）

        前置條件：
        1. Room 必須存在
        2. Room 狀態必須是 WAITING
        3. 玩家數量必須 >= 2 且為偶數

        流程：
        1. 驗證前置條件
        2. 透過 StateMachine 轉換狀態
        3. 記錄事件

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID

        返回：
            更新後的 Room

        異常：
            RoomNotFound: Room 不存在
            InvalidPlayerCount: 玩家數量不符合要求
            InvalidStateTransition: Room 狀態不是 WAITING
        """
        # 1. 取得並鎖定 Room
        room = with_room_lock(room_id, db).first()
        if not room:
            raise RoomNotFound(room_id)

        # 2. 驗證玩家數量
        player_count = db.query(Player).filter(
            Player.room_id == room_id,
            Player.is_host == False
        ).count()

        if player_count < 2:
            raise InvalidPlayerCount(
                f"Need at least 2 players to start game, got {player_count}"
            )

        if player_count % 2 != 0:
            raise InvalidPlayerCount(
                f"Player count must be even, got {player_count}"
            )

        logger.info(f"Starting game for room {room_id} with {player_count} players")

        # 3. 狀態轉換（會自動記錄 ROOM_STATE_CHANGED 事件）
        room = RoomStateMachine.transition(room_id, RoomStatus.PLAYING, db)

        # 4. 記錄遊戲開始事件
        event = EventLog(
            room_id=room_id,
            event_type="GAME_STARTED",
            data={"player_count": player_count}
        )
        db.add(event)

        return room

    @staticmethod
    @transactional
    def start_game_with_first_round(db: Session, room_id: UUID) -> Tuple[Room, 'Round']:
        """
        開始遊戲並立即建立第一輪（組合函式）

        這個函式解決了「遊戲開始但 current_round=0」的中間狀態問題。
        透過在單一 transaction 中完成兩個操作：
        1. Room 狀態轉換 WAITING -> PLAYING
        2. 建立 Round 1

        前置條件：
        1. Room 必須存在
        2. Room 狀態必須是 WAITING
        3. 玩家數量必須 >= 2 且為偶數

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID

        返回：
            (Room, Round) tuple

        異常：
            RoomNotFound: Room 不存在
            InvalidPlayerCount: 玩家數量不符合要求
            InvalidStateTransition: Room 狀態不是 WAITING

        注意：
            - 此函式內嵌了 start_game 和 create_round 的邏輯
            - 避免使用兩個 @transactional 函式導致雙重 commit
        """
        from models import Round, RoundStatus
        from services.round_phase_service import get_round_phase
        from services.pairing_service import create_pairs_for_round

        # === start_game 的邏輯 ===

        # 1. 取得並鎖定 Room
        room = with_room_lock(room_id, db).first()
        if not room:
            raise RoomNotFound(room_id)

        # 2. 驗證玩家數量
        player_count = db.query(Player).filter(
            Player.room_id == room_id,
            Player.is_host == False
        ).count()

        if player_count < 2:
            raise InvalidPlayerCount(
                f"Need at least 2 players to start game, got {player_count}"
            )

        if player_count % 2 != 0:
            raise InvalidPlayerCount(
                f"Player count must be even, got {player_count}"
            )

        logger.info(f"Starting game for room {room_id} with {player_count} players")

        # 3. 狀態轉換 WAITING -> PLAYING
        room = RoomStateMachine.transition(room_id, RoomStatus.PLAYING, db)

        # 4. 記錄遊戲開始事件
        event = EventLog(
            room_id=room_id,
            event_type="GAME_STARTED",
            data={"player_count": player_count}
        )
        db.add(event)

        # === create_round 的邏輯 ===

        # 5. 遞增回合數
        room.current_round += 1
        round_number = room.current_round

        # 6. 決定回合階段
        phase = get_round_phase(round_number)

        logger.info(
            f"Creating round {round_number} for room {room_id}, phase={phase.value}"
        )

        # 7. 建立 Round
        new_round = Round(
            room_id=room_id,
            round_number=round_number,
            phase=phase,
            status=RoundStatus.WAITING_ACTIONS
        )
        db.add(new_round)
        db.flush()  # 取得 round ID

        # 8. 建立配對
        try:
            pairs = create_pairs_for_round(room_id, new_round.id, db)
            logger.info(f"Created {len(pairs)} pairs for round {new_round.id}")
        except ValueError as e:
            raise InvalidPlayerCount(str(e))

        # 9. 記錄回合建立事件
        round_event = EventLog(
            room_id=room_id,
            event_type="ROUND_CREATED",
            data={
                "round_id": str(new_round.id),
                "round_number": round_number,
                "phase": phase.value
            }
        )
        db.add(round_event)

        # @transactional decorator 會自動 commit
        return room, new_round

    @staticmethod
    @transactional
    def end_game(db: Session, room_id: UUID) -> Room:
        """
        結束遊戲（狀態轉換 PLAYING -> FINISHED）

        前置條件：
        1. Room 必須存在
        2. Room 狀態必須是 PLAYING

        流程：
        1. 透過 StateMachine 轉換狀態
        2. 記錄事件

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID

        返回：
            更新後的 Room

        異常：
            RoomNotFound: Room 不存在
            InvalidStateTransition: Room 狀態不是 PLAYING
        """
        # 1. 狀態轉換（會自動檢查 Room 是否存在和狀態是否合法）
        room = RoomStateMachine.transition(room_id, RoomStatus.FINISHED, db)

        logger.info(f"Game ended for room {room_id}")

        # 2. 記錄遊戲結束事件
        event = EventLog(
            room_id=room_id,
            event_type="GAME_ENDED",
            data={}
        )
        db.add(event)

        return room

    @staticmethod
    def get_room_by_code(db: Session, code: str) -> Room:
        """
        透過房間代碼取得 Room

        參數：
            db: SQLAlchemy Session
            code: 6 位房間代碼

        返回：
            Room object

        異常：
            RoomNotFound: Room 不存在
        """
        room = db.query(Room).filter(Room.code == code).first()
        if not room:
            raise RoomNotFound(f"Room with code {code}")
        return room

    @staticmethod
    def get_room_by_id(db: Session, room_id: UUID) -> Room:
        """
        透過 UUID 取得 Room

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID

        返回：
            Room object

        異常：
            RoomNotFound: Room 不存在
        """
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room:
            raise RoomNotFound(room_id)
        return room

    @staticmethod
    def get_player_count(db: Session, room_id: UUID) -> int:
        """
        取得房間內玩家數量（不含 Host）

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID

        返回：
            玩家數量
        """
        return db.query(Player).filter(
            Player.room_id == room_id,
            Player.is_host == False
        ).count()
