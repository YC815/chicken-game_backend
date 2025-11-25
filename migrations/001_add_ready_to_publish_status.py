#!/usr/bin/env python3
"""
Migration: 新增 READY_TO_PUBLISH 狀態到 Round

背景：
- 將「計算結果」與「公布結果」分離
- 新增中間狀態 READY_TO_PUBLISH
- 狀態流程：WAITING_ACTIONS → CALCULATING → READY_TO_PUBLISH → COMPLETED

執行：
    python migrations/001_add_ready_to_publish_status.py

回滾：
    python migrations/001_add_ready_to_publish_status.py --rollback
"""
import sys
import os

# Add parent directory to path so we can import from backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def upgrade():
    """新增 READY_TO_PUBLISH 狀態"""
    print("Running migration: Add READY_TO_PUBLISH status to rounds table")

    with engine.connect() as conn:
        # PostgreSQL: ALTER TYPE 新增 enum 值
        # 注意：PostgreSQL 的 ADD VALUE 語法不支援 AFTER，只能添加到最後
        try:
            conn.execute(text("""
                ALTER TYPE roundstatus ADD VALUE IF NOT EXISTS 'ready_to_publish';
            """))
            conn.commit()
            print("✓ Added 'ready_to_publish' to RoundStatus enum")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ 'ready_to_publish' already exists, skipping...")
                conn.rollback()
            else:
                raise

    print("✓ Migration completed successfully")


def downgrade():
    """
    移除 READY_TO_PUBLISH 狀態

    注意：PostgreSQL 不支援從 enum type 中移除值
    需要重建整個 type，這會影響所有使用該 type 的 table

    如果你需要回滾，建議：
    1. 備份資料
    2. Drop & Recreate table
    3. 重新導入資料
    """
    print("WARNING: PostgreSQL does not support removing enum values")
    print("To rollback, you need to:")
    print("1. Backup your data")
    print("2. Drop and recreate the rounds table")
    print("3. Restore your data")
    print("\nAborting rollback...")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        downgrade()
    else:
        upgrade()
