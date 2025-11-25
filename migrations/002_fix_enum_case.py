#!/usr/bin/env python3
"""
Migration: 修復 roundstatus enum 的大小寫不一致問題

問題：
- 資料庫 enum 定義中同時存在大寫和小寫版本
- 實際資料使用大寫
- Python 程式碼期望小寫

解決方案：
1. 將所有資料轉換為小寫
2. 重建 enum type（只包含小寫版本）

執行：
    .venv/bin/python migrations/002_fix_enum_case.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def upgrade():
    """修復 enum 大小寫"""
    print("Running migration: Fix roundstatus enum case")

    with engine.connect() as conn:
        # Step 1: 檢查當前狀態
        print("\n=== Current State ===")
        result = conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            WHERE enumtypid = 'roundstatus'::regtype
            ORDER BY oid
        """))
        labels = [r[0] for r in result]
        print("Enum labels:")
        for label in labels:
            print(f'  - "{label}"')

        result = conn.execute(text("SELECT DISTINCT status FROM rounds"))
        statuses = [r[0] for r in result]
        print("\nActual data:")
        for status in statuses:
            print(f'  - "{status}"')

        # Step 2: 先改為 varchar（才能自由修改值）
        print("\n=== Converting to varchar ===")
        conn.execute(text("""
            ALTER TABLE rounds
            ALTER COLUMN status TYPE varchar(50)
        """))
        print("✓ Converted status column to varchar")

        # Step 3: 更新所有資料為小寫
        print("\n=== Updating Data ===")
        updates = [
            ("WAITING_ACTIONS", "waiting_actions"),
            ("CALCULATING", "calculating"),
            ("COMPLETED", "completed"),
            ("READY_TO_PUBLISH", "ready_to_publish"),
        ]

        for old, new in updates:
            result = conn.execute(
                text(f"UPDATE rounds SET status = '{new}' WHERE status = '{old}'")
            )
            if result.rowcount > 0:
                print(f"✓ Updated {result.rowcount} rows: {old} -> {new}")

        # Step 4: 重建 enum type（只保留小寫）
        print("\n=== Rebuilding Enum Type ===")

        # 刪除舊的 enum type
        conn.execute(text("DROP TYPE IF EXISTS roundstatus"))
        print("✓ Dropped old enum type")

        # 建立新的 enum type（只有小寫）
        conn.execute(text("""
            CREATE TYPE roundstatus AS ENUM (
                'waiting_actions',
                'calculating',
                'ready_to_publish',
                'completed'
            )
        """))
        print("✓ Created new enum type with lowercase values")

        # 改回 enum
        conn.execute(text("""
            ALTER TABLE rounds
            ALTER COLUMN status TYPE roundstatus USING status::roundstatus
        """))
        print("✓ Converted status column back to enum")

        conn.commit()

    print("\n✓ Migration completed successfully")


if __name__ == "__main__":
    upgrade()
