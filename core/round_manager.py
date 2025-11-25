"""
Round Manager：管理 Round 的完整生命週期

職責：
1. 建立新回合（含配對）
2. 接收玩家動作（冪等性設計）
3. 嘗試結算回合（安全的並發控制）
4. 查詢回合資訊

Linus 原則：
- 消除特殊情況：「最後一個人觸發結算」變成「任何人都可以嘗試結算」
- 並發安全：使用 DB lock 確保不會重複計算
- 冪等性：同一個動作提交多次，只會生效一次
"""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from uuid import UUID
from typing import Optional
import logging

from models import (
    Room, Round, Action, Choice, RoundStatus, RoundPhase, EventLog
)
from core.state_machine import RoundStateMachine
from core.locks import with_room_lock, with_round_lock
from core.exceptions import (
    RoomNotFound,
    RoundNotFound,
    MaxRoundsReached,
    ActionAlreadySubmitted,
    InvalidPlayerCount
)
from services.pairing_service import (
    create_pairs_for_round,
    copy_pairs_from_round
)
from services.payoff_service import (
    calculate_round_payoffs,
    all_actions_submitted
)
from services.round_phase_service import get_round_phase
from database import transactional

logger = logging.getLogger(__name__)


class RoundManager:
    """Round 生命週期管理器"""

    @staticmethod
    @transactional
    def create_round(db: Session, room_id: UUID) -> Round:
        """
        建立新回合（含配對）

        前置條件：
        1. Room 必須存在
        2. 當前回合數 < 10
        3. Room 狀態必須是 PLAYING

        流程：
        1. 鎖定 Room
        2. 檢查前置條件
        3. Room.current_round += 1
        4. 建立 Round
        5. 建立配對（Pairs）
        6. 記錄事件

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID

        返回：
            新建立的 Round

        異常：
            RoomNotFound: Room 不存在
            MaxRoundsReached: 已達 10 回合上限
        """
        # 1. 鎖定 Room（防止並發建立多個回合）
        room = with_room_lock(room_id, db).first()
        if not room:
            raise RoomNotFound(room_id)

        # 2. 檢查回合數上限
        if room.current_round >= 10:
            raise MaxRoundsReached(
                f"Room {room_id} has reached maximum rounds (10)"
            )

        # 3. 遞增回合數
        room.current_round += 1
        round_number = room.current_round

        # 4. 決定回合階段
        phase = get_round_phase(round_number)

        logger.info(
            f"Creating round {round_number} for room {room_id}, phase={phase.value}"
        )

        # 5. 建立 Round
        new_round = Round(
            room_id=room_id,
            round_number=round_number,
            phase=phase,
            status=RoundStatus.WAITING_ACTIONS
        )
        db.add(new_round)
        db.flush()  # 取得 round ID

        # 6. 建立配對（Round 1 隨機、之後沿用 Round 1 配對）
        try:
            if round_number == 1:
                pairs = create_pairs_for_round(room_id, new_round.id, db)
            else:
                # 使用 Round 1 的配對固定對手
                first_round = db.query(Round).filter(
                    Round.room_id == room_id,
                    Round.round_number == 1
                ).first()
                if not first_round:
                    raise ValueError("Round 1 not found to reuse pairs from")

                pairs = copy_pairs_from_round(
                    room_id=room_id,
                    source_round_id=first_round.id,
                    target_round_id=new_round.id,
                    db=db
                )
            logger.info(f"Created {len(pairs)} pairs for round {new_round.id}")
        except ValueError as e:
            # 玩家數量不是偶數
            raise InvalidPlayerCount(str(e))

        # 7. 記錄事件
        event = EventLog(
            room_id=room_id,
            event_type="ROUND_CREATED",
            data={
                "round_id": str(new_round.id),
                "round_number": round_number,
                "phase": phase.value
            }
        )
        db.add(event)

        return new_round

    @staticmethod
    @transactional
    def submit_action(
        db: Session,
        round_id: UUID,
        player_id: UUID,
        choice: Choice
    ) -> Action:
        """
        提交玩家動作（冪等性設計）

        重要：
        - 如果玩家已經提交過，返回既有的 Action（而不是報錯）
        - 使用 DB unique constraint 確保不會重複插入

        流程：
        1. 檢查 Round 是否存在
        2. 嘗試插入 Action
        3. 如果違反 unique constraint，查詢並返回既有 Action

        參數：
            db: SQLAlchemy Session
            round_id: Round UUID
            player_id: Player UUID
            choice: 玩家選擇（TURN 或 ACCELERATE）

        返回：
            Action object（新建立或既有的）

        注意：
            - 此函式是冪等的（Idempotent）
            - 多次呼叫同樣參數，效果相同
            - 不會拋出 ActionAlreadySubmitted 異常
        """
        # 1. 檢查 Round 是否存在
        round_obj = db.query(Round).filter(Round.id == round_id).first()
        if not round_obj:
            raise RoundNotFound(round_id)

        logger.info(
            f"Submitting action for player {player_id} in round {round_id}: {choice.value}"
        )

        # 2. 嘗試建立 Action
        action = Action(
            room_id=round_obj.room_id,
            round_id=round_id,
            player_id=player_id,
            choice=choice
        )
        db.add(action)

        try:
            db.flush()  # 觸發 unique constraint 檢查
            logger.info(f"Action created for player {player_id}")
            return action

        except IntegrityError:
            # 違反 unique constraint：玩家已經提交過
            logger.info(f"Action already exists for player {player_id}, returning existing")
            db.rollback()

            # 查詢既有的 Action
            existing_action = db.query(Action).filter(
                Action.round_id == round_id,
                Action.player_id == player_id
            ).first()

            if not existing_action:
                # 理論上不應該發生（IntegrityError 表示有重複）
                logger.error(
                    f"IntegrityError but no existing action found: "
                    f"round={round_id}, player={player_id}"
                )
                raise

            return existing_action

    @staticmethod
    @transactional
    def try_finalize_round(db: Session, round_id: UUID) -> bool:
        """
        計算回合結果（但不公布）

        重要：
        - 此函式是冪等的（可以被多次呼叫）
        - 使用 DB lock + result_calculated 欄位防止重複計算
        - 結果計算完成後停在 READY_TO_PUBLISH 狀態

        流程：
        1. 鎖定 Round
        2. 檢查是否已結算（idempotency check）
        3. 檢查是否所有玩家都提交了動作
        4. 狀態轉換 WAITING_ACTIONS -> CALCULATING
        5. 計算 Payoff
        6. 標記 result_calculated = True
        7. 狀態轉換 CALCULATING -> READY_TO_PUBLISH（停在這裡，等待管理員公布）
        8. 記錄事件

        參數：
            db: SQLAlchemy Session
            round_id: Round UUID

        返回：
            True 如果結算成功（或已結算），False 如果還有玩家未提交

        設計理念（Linus 的「好品味」）：
        - 消除特殊情況：任何人都可以呼叫此函式，不用管「誰是最後一個」
        - 分離關注點：計算（finalize）與公布（publish）是兩件事
        - DB lock 確保不會重複計算
        - 冪等性：多次呼叫效果相同
        """
        # 1. 鎖定 Round（防止並發結算）
        round_obj = with_round_lock(round_id, db).first()
        if not round_obj:
            logger.warning(f"Round {round_id} not found")
            return False

        # 2. Idempotency check：已經結算過了？
        if round_obj.result_calculated:
            logger.info(f"Round {round_id} already finalized")
            return True

        # 3. 檢查是否所有玩家都提交了動作
        if not all_actions_submitted(round_id, db):
            logger.info(f"Round {round_id} not all actions submitted yet")
            return False

        logger.info(f"Calculating round {round_id} results (room={round_obj.room_id}, round_number={round_obj.round_number})")

        # 4. 狀態轉換：WAITING_ACTIONS -> CALCULATING
        round_obj = RoundStateMachine.transition(
            round_id,
            RoundStatus.CALCULATING,
            db
        )

        # 5. 計算 Payoff
        calculate_round_payoffs(round_id, db)

        # 6. 標記為已計算（防止重複計算的關鍵！）
        round_obj.result_calculated = True

        # 7. 狀態轉換：CALCULATING -> READY_TO_PUBLISH（停在這裡，等待管理員公布）
        round_obj = RoundStateMachine.transition(
            round_id,
            RoundStatus.READY_TO_PUBLISH,
            db
        )

        # 8. 記錄事件
        event = EventLog(
            room_id=round_obj.room_id,
            event_type="ROUND_CALCULATED",
            data={
                "round_id": str(round_id),
                "round_number": round_obj.round_number
            }
        )
        db.add(event)

        logger.info(f"Round {round_id} calculated, waiting for publish")
        return True

    @staticmethod
    @transactional
    def publish_round(db: Session, round_id: UUID) -> Round:
        """
        公布回合結果

        前置條件：
        - Round 狀態必須是 READY_TO_PUBLISH
        - result_calculated 必須為 True

        流程：
        1. 鎖定 Round
        2. 檢查狀態
        3. 狀態轉換 READY_TO_PUBLISH -> COMPLETED
        4. 記錄事件

        參數：
            db: SQLAlchemy Session
            round_id: Round UUID

        返回：
            更新後的 Round

        設計理念：
        - 冪等性：如果已經是 COMPLETED，直接返回
        - 簡單明確：只做狀態轉換，不做計算
        """
        # 1. 鎖定 Round
        round_obj = with_round_lock(round_id, db).first()
        if not round_obj:
            raise RoundNotFound(round_id)

        # 2. Idempotency check：已經公布了？
        if round_obj.status == RoundStatus.COMPLETED:
            logger.info(f"Round {round_id} already published")
            return round_obj

        # 3. 檢查狀態
        if round_obj.status != RoundStatus.READY_TO_PUBLISH:
            raise InvalidStateTransition(
                f"Cannot publish round in status {round_obj.status.value}"
            )

        logger.info(f"Publishing round {round_id} (room={round_obj.room_id}, round_number={round_obj.round_number})")

        # 4. 狀態轉換：READY_TO_PUBLISH -> COMPLETED
        round_obj = RoundStateMachine.transition(
            round_id,
            RoundStatus.COMPLETED,
            db
        )

        # 5. 記錄事件
        event = EventLog(
            room_id=round_obj.room_id,
            event_type="ROUND_PUBLISHED",
            data={
                "round_id": str(round_id),
                "round_number": round_obj.round_number
            }
        )
        db.add(event)

        logger.info(f"Round {round_id} published successfully")
        return round_obj

    @staticmethod
    def get_round_by_number(
        db: Session,
        room_id: UUID,
        round_number: int
    ) -> Optional[Round]:
        """
        根據回合數取得 Round

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID
            round_number: 回合數（1-10）

        返回：
            Round object 或 None
        """
        return db.query(Round).filter(
            Round.room_id == room_id,
            Round.round_number == round_number
        ).first()

    @staticmethod
    def get_current_round(db: Session, room_id: UUID) -> Optional[Round]:
        """
        取得房間當前回合

        參數：
            db: SQLAlchemy Session
            room_id: Room UUID

        返回：
            Round object 或 None（如果遊戲尚未開始）
        """
        room = db.query(Room).filter(Room.id == room_id).first()
        if not room or room.current_round == 0:
            return None

        return RoundManager.get_round_by_number(db, room_id, room.current_round)
