from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, DateTime, Enum, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from database import Base


class RoomStatus(str, enum.Enum):
    WAITING = "WAITING"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"


class RoundPhase(str, enum.Enum):
    NORMAL = "NORMAL"
    MESSAGE = "MESSAGE"
    INDICATOR = "INDICATOR"


class RoundStatus(str, enum.Enum):
    WAITING_ACTIONS = "waiting_actions"
    CALCULATING = "calculating"
    READY_TO_PUBLISH = "ready_to_publish"  # 結果已計算，等待管理員公布
    COMPLETED = "completed"


class Choice(str, enum.Enum):
    ACCELERATE = "ACCELERATE"
    TURN = "TURN"


class Room(Base):
    __tablename__ = "rooms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(6), unique=True, nullable=False, index=True)
    status = Column(Enum(RoomStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]), default=RoomStatus.WAITING, nullable=False)
    current_round = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    players = relationship("Player", back_populates="room", cascade="all, delete-orphan")
    rounds = relationship("Round", back_populates="room", cascade="all, delete-orphan")
    pairs = relationship("Pair", back_populates="room", cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="room", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="room", cascade="all, delete-orphan")
    indicators = relationship("Indicator", back_populates="room", cascade="all, delete-orphan")


class Player(Base):
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    nickname = Column(String(50), nullable=False)
    display_name = Column(String(50), nullable=False)
    is_host = Column(Boolean, default=False, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    room = relationship("Room", back_populates="players")
    actions = relationship("Action", back_populates="player", cascade="all, delete-orphan")
    sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender", cascade="all, delete-orphan")
    received_messages = relationship("Message", foreign_keys="Message.receiver_id", back_populates="receiver", cascade="all, delete-orphan")
    indicator = relationship("Indicator", back_populates="player", uselist=False, cascade="all, delete-orphan")


class Round(Base):
    __tablename__ = "rounds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    phase = Column(Enum(RoundPhase, native_enum=True, values_callable=lambda x: [e.value for e in x]), default=RoundPhase.NORMAL, nullable=False)
    status = Column(Enum(RoundStatus, native_enum=True, values_callable=lambda x: [e.value for e in x]), default=RoundStatus.WAITING_ACTIONS, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    # 並發控制欄位：防止重複計算結果
    result_calculated = Column(Boolean, default=False, nullable=False, index=True)
    # 樂觀鎖版本號：用於檢測並發衝突
    version = Column(Integer, default=1, nullable=False)

    room = relationship("Room", back_populates="rounds")
    pairs = relationship("Pair", back_populates="round", cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="round", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="round", cascade="all, delete-orphan")


class Pair(Base):
    __tablename__ = "pairs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(UUID(as_uuid=True), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    player1_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    player2_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)

    room = relationship("Room", back_populates="pairs")
    round = relationship("Round", back_populates="pairs")
    player1 = relationship("Player", foreign_keys=[player1_id])
    player2 = relationship("Player", foreign_keys=[player2_id])


class Action(Base):
    __tablename__ = "actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(UUID(as_uuid=True), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    choice = Column(Enum(Choice, native_enum=True, values_callable=lambda x: [e.value for e in x]), nullable=False)
    payoff = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    room = relationship("Room", back_populates="actions")
    round = relationship("Round", back_populates="actions")
    player = relationship("Player", back_populates="actions")

    # 加入唯一性約束：每個玩家在每個回合只能提交一次動作
    __table_args__ = (
        Index('idx_round_player', 'round_id', 'player_id', unique=True),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(UUID(as_uuid=True), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    content = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    room = relationship("Room", back_populates="messages")
    round = relationship("Round", back_populates="messages")
    sender = relationship("Player", foreign_keys=[sender_id], back_populates="sent_messages")
    receiver = relationship("Player", foreign_keys=[receiver_id], back_populates="received_messages")


class Indicator(Base):
    __tablename__ = "indicators"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False, unique=True)
    symbol = Column(String(10), nullable=False)

    room = relationship("Room", back_populates="indicators")
    player = relationship("Player", back_populates="indicator")


class EventLog(Base):
    """
    事件日誌：記錄所有重要的業務事件

    用途：
    1. 提供事件溯源（Event Sourcing）能力
    2. 讓 WebSocket 斷線的客戶端可以補發事件
    3. 審計追蹤（Audit Trail）
    4. Debug 時可以看到完整的事件序列
    """
    __tablename__ = "event_logs"

    # 使用自增整數 ID，方便客戶端查詢 "給我 event_id > X 的所有事件"
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    data = Column(JSON, nullable=False, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    room = relationship("Room")
