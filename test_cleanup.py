#!/usr/bin/env python3
"""
測試房間清理功能
"""
from datetime import datetime, timedelta
from database import SessionLocal
from utils.cleanup import cleanup_old_rooms, cleanup_inactive_rooms
from models import Room

def test_cleanup():
    """測試清理功能"""
    db = SessionLocal()
    try:
        print("=" * 60)
        print("測試房間清理功能")
        print("=" * 60)
        print()

        # 1. 顯示目前所有房間
        all_rooms = db.query(Room).all()
        print(f"1. 當前資料庫中有 {len(all_rooms)} 個房間")
        print()

        if all_rooms:
            print("房間列表:")
            for room in all_rooms:
                age = datetime.utcnow() - room.updated_at
                hours_old = age.total_seconds() / 3600
                print(f"  - {room.code} ({room.status}) - "
                      f"最後更新: {hours_old:.1f} 小時前")
            print()

        # 2. 測試清理已結束的房間（24 小時前）
        print("2. 清理 24 小時前的 FINISHED 房間...")
        finished_count = cleanup_old_rooms(db, hours=24, status_filter="FINISHED")
        print(f"   已清理 {finished_count} 個 FINISHED 房間")
        print()

        # 3. 測試清理閒置房間（2 小時前）
        print("3. 清理 2 小時閒置的 WAITING/PLAYING 房間...")
        inactive_count = cleanup_inactive_rooms(db, hours=2)
        print(f"   已清理 {inactive_count} 個閒置房間")
        print()

        # 4. 顯示清理後的房間數
        remaining_rooms = db.query(Room).all()
        print(f"4. 清理後剩餘 {len(remaining_rooms)} 個房間")
        print()

        if remaining_rooms:
            print("剩餘房間:")
            for room in remaining_rooms:
                age = datetime.utcnow() - room.updated_at
                hours_old = age.total_seconds() / 3600
                print(f"  - {room.code} ({room.status}) - "
                      f"最後更新: {hours_old:.1f} 小時前")
            print()

        # 5. 測試激進清理（刪除所有舊房間，用於開發測試）
        print("5. 要清理所有舊房間嗎？(y/N): ", end="")
        import sys
        response = sys.stdin.readline().strip().lower()

        if response == 'y':
            print("   清理所有 1 小時前的房間...")
            all_old = cleanup_old_rooms(db, hours=1, status_filter=None)
            print(f"   已清理 {all_old} 個房間")

            final_count = db.query(Room).count()
            print(f"   最終剩餘 {final_count} 個房間")
        else:
            print("   跳過")

        print()
        print("=" * 60)
        print("測試完成")
        print("=" * 60)

    finally:
        db.close()

if __name__ == "__main__":
    test_cleanup()
