"""
配對服務：玩家配對邏輯

純計算邏輯，負責：
1. 隨機配對玩家
2. 確保配對數量正確
3. 不負責驗證（由 Manager 負責）
"""
import random
from uuid import UUID
from sqlalchemy.orm import Session
from typing import List

from models import Player, Pair


def create_pairs_for_round(room_id: UUID, round_id: UUID, db: Session) -> List[Pair]:
    """
    為一個回合建立隨機配對

    演算法：
    1. 取得房間內所有非 Host 玩家
    2. 隨機洗牌
    3. 兩兩配對（第 0-1, 2-3, 4-5, ...）

    參數：
        room_id: 房間 ID
        round_id: 回合 ID
        db: SQLAlchemy Session

    返回：
        Pair 物件列表

    異常：
        ValueError: 如果玩家數量不是偶數

    範例：
        玩家: [A, B, C, D, E, F]
        洗牌後: [D, A, F, B, E, C]
        配對: (D-A), (F-B), (E-C)
    """
    # 1. 取得所有非 Host 玩家
    players = db.query(Player).filter(
        Player.room_id == room_id,
        Player.is_host == False
    ).all()

    # 2. 檢查玩家數量（必須是偶數）
    if len(players) % 2 != 0:
        raise ValueError(
            f"Player count must be even for pairing, got {len(players)} players"
        )

    # 3. 隨機洗牌（確保每回合配對都不同）
    random.shuffle(players)

    # 4. 兩兩配對
    pairs = []
    for i in range(0, len(players), 2):
        pair = Pair(
            room_id=room_id,
            round_id=round_id,
            player1_id=players[i].id,
            player2_id=players[i + 1].id
        )
        db.add(pair)
        pairs.append(pair)

    # 5. Flush 但不 commit（讓外層 transaction 處理）
    db.flush()

    return pairs


def copy_pairs_from_round(
    room_id: UUID,
    source_round_id: UUID,
    target_round_id: UUID,
    db: Session
) -> List[Pair]:
    """
    將既有回合的配對複製到新回合（維持固定對手）

    參數：
        room_id: 房間 ID
        source_round_id: 來源回合 ID（通常是 Round 1）
        target_round_id: 目標回合 ID
        db: SQLAlchemy Session

    返回：
        新建立的 Pair 物件列表

    異常：
        ValueError: 如果來源回合沒有任何配對
    """
    source_pairs = db.query(Pair).filter(Pair.round_id == source_round_id).all()

    if not source_pairs:
        raise ValueError(f"No pairs found in source round {source_round_id}")

    new_pairs: List[Pair] = []
    for pair in source_pairs:
        cloned = Pair(
            room_id=room_id,
            round_id=target_round_id,
            player1_id=pair.player1_id,
            player2_id=pair.player2_id
        )
        db.add(cloned)
        new_pairs.append(cloned)

    db.flush()
    return new_pairs


def get_pairs_in_round(round_id: UUID, db: Session) -> List[Pair]:
    """
    取得某回合的所有配對

    參數：
        round_id: 回合 ID
        db: SQLAlchemy Session

    返回：
        Pair 物件列表
    """
    return db.query(Pair).filter(Pair.round_id == round_id).all()


def get_opponent_id(round_id: UUID, player_id: UUID, db: Session) -> UUID:
    """
    找出玩家在某回合的對手 ID

    參數：
        round_id: 回合 ID
        player_id: 玩家 ID
        db: SQLAlchemy Session

    返回：
        對手的 UUID

    異常：
        ValueError: 如果找不到配對

    範例：
        如果 Pair(player1=A, player2=B)
        get_opponent_id(round_id, A, db) -> B
        get_opponent_id(round_id, B, db) -> A
    """
    pair = db.query(Pair).filter(
        Pair.round_id == round_id,
        ((Pair.player1_id == player_id) | (Pair.player2_id == player_id))
    ).first()

    if not pair:
        raise ValueError(f"No pair found for player {player_id} in round {round_id}")

    # 返回對手的 ID
    return pair.player2_id if pair.player1_id == player_id else pair.player1_id
