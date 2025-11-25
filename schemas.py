from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

from models import RoomStatus, RoundPhase, RoundStatus, Choice


# Room schemas
class RoomCreate(BaseModel):
    pass


class RoomResponse(BaseModel):
    room_id: UUID
    code: str
    host_player_id: UUID

    class Config:
        from_attributes = True


class RoomStatusResponse(BaseModel):
    room_id: UUID
    code: str
    status: RoomStatus
    current_round: int
    player_count: int

    class Config:
        from_attributes = True


# Player schemas
class PlayerJoin(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=50)


class PlayerResponse(BaseModel):
    player_id: UUID
    room_id: UUID
    display_name: str

    class Config:
        from_attributes = True


class PlayerSummary(BaseModel):
    display_name: str
    total_payoff: int

    class Config:
        from_attributes = True


# Round schemas
class RoundCurrentResponse(BaseModel):
    round_number: int
    phase: RoundPhase
    status: RoundStatus

    class Config:
        from_attributes = True


# Pair schemas
class PairResponse(BaseModel):
    opponent_id: UUID
    opponent_display_name: str

    class Config:
        from_attributes = True


# Action schemas
class ActionSubmit(BaseModel):
    player_id: UUID
    choice: Choice


class ActionResponse(BaseModel):
    status: str = "ok"


# Result schemas
class RoundResultResponse(BaseModel):
    opponent_display_name: str
    your_choice: Choice
    opponent_choice: Choice
    your_payoff: int
    opponent_payoff: int

    class Config:
        from_attributes = True


# Message schemas
class MessageSubmit(BaseModel):
    sender_id: UUID
    content: str = Field(..., min_length=1, max_length=100)


class MessageResponse(BaseModel):
    content: str
    from_opponent: bool = True

    class Config:
        from_attributes = True


# Indicator schemas
class IndicatorResponse(BaseModel):
    symbol: str

    class Config:
        from_attributes = True


# Summary schemas
class GameStats(BaseModel):
    accelerate_ratio: float
    turn_ratio: float


class GameSummaryResponse(BaseModel):
    players: list[PlayerSummary]
    stats: GameStats

    class Config:
        from_attributes = True


# WebSocket event types
class WSEventType:
    ROOM_STARTED = "ROOM_STARTED"
    ROUND_STARTED = "ROUND_STARTED"
    ACTION_SUBMITTED = "ACTION_SUBMITTED"  # 有玩家提交了動作（進度通知）
    ROUND_READY = "ROUND_READY"            # 所有人都提交了，等待管理員公布
    ROUND_ENDED = "ROUND_ENDED"            # 結果已公布（Client 去 GET /result）
    MESSAGE_PHASE = "MESSAGE_PHASE"
    INDICATORS_ASSIGNED = "INDICATORS_ASSIGNED"
    GAME_ENDED = "GAME_ENDED"


class WSEvent(BaseModel):
    event_type: str
    room_id: UUID
    data: Optional[dict] = None
