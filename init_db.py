#!/usr/bin/env python3
"""
一次性 script：重建資料庫所有表
執行後可刪除此檔案
"""
from database import Base, engine
import models  # 必須 import models 讓 Base.metadata 知道有哪些 table

if __name__ == "__main__":
    print("Creating all tables from models.py...")
    Base.metadata.create_all(bind=engine)
    print("✓ All tables created successfully")
