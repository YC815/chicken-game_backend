"""
State service: builds versioned room snapshots for short polling
and bumps the state_version counter whenever important changes happen.
"""
from datetime import datetime
import logging
from typing import Optional

from sqlalchemy.orm import Session

from core.exceptions import RoomNotFound
from core.locks import with_room_lock
from models import (
    Room,
    Player,
    Round,
    Action,
    Message,
    EventLog
)
from schemas import (
    RoomStateResponse,
    RoomStatePayload,
    RoundStatePayload,
    PlayerStatePayload,
    MessageStatePayload,
    RoomStatusResponse,
)
from services.indicator_service import (
    get_player_indicator,
    indicators_already_assigned
)
from services.pairing_service import (
    get_opponent_id,
    get_pairs_in_round
)
from services.round_phase_service import is_message_round

logger = logging.getLogger(__name__)


def bump_state_version(db: Session, room_id: str, reason: Optional[str] = None) -> int:
    """
    Increment room.state_version to signal polling clients there is new data.
    Keeps everything inside the existing transaction and optionally logs an event.
    """
    room = with_room_lock(room_id, db).first()
    if not room:
        raise RoomNotFound(room_id)

    room.state_version = (room.state_version or 0) + 1
    room.updated_at = datetime.utcnow()

    if reason:
        db.add(EventLog(
            room_id=room_id,
            event_type="STATE_VERSION_BUMPED",
            data={
                "reason": reason,
                "version": room.state_version
            },
            created_at=datetime.utcnow()
        ))

    logger.debug("Room %s state_version bumped to %s (%s)", room_id, room.state_version, reason or "no reason")
    return room.state_version


def build_room_state(
    db: Session,
    room_id: str,
    client_version: Optional[int] = None,
    player_id: Optional[str] = None
) -> RoomStateResponse:
    """
    Build a snapshot of the room suitable for short polling consumers.
    If the client's version is up-to-date, only returns has_update=False.
    """
    room: Optional[Room] = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise RoomNotFound(room_id)

    current_version = room.state_version or 0
    client_version = client_version or 0

    if client_version >= current_version:
        return RoomStateResponse(version=current_version, has_update=False)

    players = db.query(Player).filter(Player.room_id == room_id).all()
    player_count = len([p for p in players if not p.is_host])
    player_payloads = [
        PlayerStatePayload(
            player_id=p.id,
            display_name=p.display_name,
            is_host=p.is_host
        )
        for p in players
    ]

    round_payload: Optional[RoundStatePayload] = None
    message_payload: Optional[MessageStatePayload] = None
    indicator_symbol: Optional[str] = None
    indicators_ready = indicators_already_assigned(room_id, db)

    current_round: Optional[Round] = None
    if room.current_round > 0:
        current_round = db.query(Round).filter(
            Round.room_id == room_id,
            Round.round_number == room.current_round
        ).first()

    if current_round:
        # Collect all submitted actions with player info
        submitted_actions_data = db.query(Action).filter(
            Action.round_id == current_round.id
        ).all()
        submitted_player_ids = {action.player_id for action in submitted_actions_data}

        # Get all players in this round from pairs
        pairs = get_pairs_in_round(current_round.id, db)
        all_round_player_ids = set()
        for pair in pairs:
            all_round_player_ids.add(pair.player1_id)
            all_round_player_ids.add(pair.player2_id)

        total_players = len(all_round_player_ids)
        submitted_actions = len(submitted_player_ids)

        # Build player submission status list
        from schemas import PlayerSubmissionStatus
        player_submissions = []
        for player in players:
            if player.id in all_round_player_ids and not player.is_host:
                player_submissions.append(PlayerSubmissionStatus(
                    player_id=player.id,
                    display_name=player.display_name,
                    submitted=(player.id in submitted_player_ids)
                ))

        round_payload = RoundStatePayload(
            round_number=current_round.round_number,
            phase=current_round.phase,
            status=current_round.status,
            submitted_actions=submitted_actions,
            total_players=total_players,
            player_submissions=player_submissions
        )

        if player_id:
            player_action = db.query(Action).filter(
                Action.round_id == current_round.id,
                Action.player_id == player_id
            ).first()
            if player_action:
                round_payload.your_choice = player_action.choice
                round_payload.your_payoff = player_action.payoff

            try:
                opponent_id = get_opponent_id(current_round.id, player_id, db)
                opponent = db.query(Player).filter(Player.id == opponent_id).first()
                if opponent:
                    round_payload.opponent_display_name = opponent.display_name

                opponent_action = db.query(Action).filter(
                    Action.round_id == current_round.id,
                    Action.player_id == opponent_id
                ).first()
                if opponent_action:
                    round_payload.opponent_choice = opponent_action.choice
                    round_payload.opponent_payoff = opponent_action.payoff

            except ValueError:
                logger.debug("Opponent not found yet for player %s in round %s", player_id, current_round.id)

            if is_message_round(current_round.round_number):
                message = db.query(Message).filter(
                    Message.round_id == current_round.id,
                    Message.receiver_id == player_id
                ).first()
                if message:
                    sender = next((p for p in players if p.id == message.sender_id), None)
                    message_payload = MessageStatePayload(
                        round_number=current_round.round_number,
                        content=message.content,
                        from_player_id=message.sender_id,
                        from_display_name=sender.display_name if sender else "Unknown"
                    )

            # Only try indicator lookup when one should exist
            try:
                indicator_symbol = get_player_indicator(player_id, db)
            except ValueError:
                indicator_symbol = None

    state_payload = RoomStatePayload(
        room=RoomStatusResponse(
            room_id=room.id,
            code=room.code,
            status=room.status,
            current_round=room.current_round,
            player_count=player_count
        ),
        players=player_payloads,
        round=round_payload,
        indicator_symbol=indicator_symbol,
        indicators_assigned=indicators_ready,
        message=message_payload,
        version=current_version,
    )

    return RoomStateResponse(
        version=current_version,
        has_update=True,
        data=state_payload
    )
