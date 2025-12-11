"""
Room Cleanup Utility

職責：
- 定期清理過期的房間
- 避免資料庫無限累積舊資料
- 保持系統效能
"""
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session

from models import Room

logger = logging.getLogger(__name__)


def cleanup_old_rooms(db: Session, hours: int = 24, status_filter: str = "FINISHED") -> int:
    """
    刪除過期的房間

    參數：
        db: 資料庫 session
        hours: 保留時間（小時），超過此時間的房間會被刪除
        status_filter: 房間狀態過濾（預設只刪除已結束的房間）

    返回：
        被刪除的房間數量

    範例：
        # 刪除 24 小時前建立且已結束的房間
        cleanup_old_rooms(db, hours=24, status_filter="FINISHED")

        # 刪除 1 小時前的所有房間（不管狀態）
        cleanup_old_rooms(db, hours=1, status_filter=None)
    """
    try:
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        # 建立查詢
        query = db.query(Room).filter(Room.updated_at < cutoff)

        # 如果有狀態過濾，加上條件
        if status_filter:
            query = query.filter(Room.status == status_filter)

        # 取得要刪除的房間列表（用於記錄）
        rooms_to_delete = query.all()
        room_count = len(rooms_to_delete)

        if room_count == 0:
            logger.info(f"No rooms to cleanup (cutoff: {cutoff}, status: {status_filter or 'any'})")
            return 0

        # 記錄要刪除的房間
        logger.info(f"Cleaning up {room_count} rooms older than {hours}h (status: {status_filter or 'any'})")
        for room in rooms_to_delete:
            logger.debug(f"  - Room {room.id} (code: {room.code}, status: {room.status}, updated: {room.updated_at})")

        # 刪除房間（級聯刪除會自動清理所有相關資料）
        for room in rooms_to_delete:
            db.delete(room)

        db.commit()
        logger.info(f"Successfully cleaned up {room_count} rooms")

        return room_count

    except Exception as e:
        logger.error(f"Failed to cleanup old rooms: {e}", exc_info=True)
        db.rollback()
        return 0


def cleanup_inactive_rooms(db: Session, hours: int = 2) -> int:
    """
    刪除長時間沒有更新的 WAITING 狀態房間

    用途：
    - 清理已建立但沒人加入的房間
    - 清理開始遊戲後但卡住的房間

    參數：
        db: 資料庫 session
        hours: 閒置時間（小時）

    返回：
        被刪除的房間數量
    """
    try:
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        inactive_rooms = db.query(Room).filter(
            Room.updated_at < cutoff,
            Room.status.in_(["WAITING", "PLAYING"])
        ).all()

        if not inactive_rooms:
            logger.info(f"No inactive rooms to cleanup (cutoff: {cutoff})")
            return 0

        room_count = len(inactive_rooms)
        logger.info(f"Cleaning up {room_count} inactive rooms (idle > {hours}h)")

        for room in inactive_rooms:
            logger.debug(f"  - Room {room.id} (code: {room.code}, status: {room.status}, updated: {room.updated_at})")
            db.delete(room)

        db.commit()
        logger.info(f"Successfully cleaned up {room_count} inactive rooms")

        return room_count

    except Exception as e:
        logger.error(f"Failed to cleanup inactive rooms: {e}", exc_info=True)
        db.rollback()
        return 0
