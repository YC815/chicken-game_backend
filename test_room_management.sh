#!/bin/bash
# 測試房間管理 API

API_BASE="http://localhost:8000/api"

echo "========================================="
echo "測試房間管理 API"
echo "========================================="
echo

# 1. 列出所有房間
echo "1. 列出所有房間 (GET /api/rooms)"
echo "-----------------------------------"
curl -s "${API_BASE}/rooms?limit=10" | python -m json.tool
echo
echo

# 2. 列出 WAITING 狀態的房間
echo "2. 列出 WAITING 狀態的房間"
echo "-----------------------------------"
curl -s "${API_BASE}/rooms?status=WAITING&limit=5" | python -m json.tool
echo
echo

# 3. 建立測試房間
echo "3. 建立新房間"
echo "-----------------------------------"
ROOM_RESPONSE=$(curl -s -X POST "${API_BASE}/rooms" -H "Content-Type: application/json" -d '{}')
echo "$ROOM_RESPONSE" | python -m json.tool

ROOM_ID=$(echo "$ROOM_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['room_id'])")
ROOM_CODE=$(echo "$ROOM_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['code'])")
echo
echo "房間已建立: room_id=$ROOM_ID, code=$ROOM_CODE"
echo
echo

# 4. 查詢房間狀態
echo "4. 查詢房間狀態 (GET /api/rooms/${ROOM_CODE})"
echo "-----------------------------------"
curl -s "${API_BASE}/rooms/${ROOM_CODE}" | python -m json.tool
echo
echo

# 5. 刪除房間
echo "5. 刪除房間 (DELETE /api/rooms/${ROOM_ID})"
echo "-----------------------------------"
curl -s -X DELETE "${API_BASE}/rooms/${ROOM_ID}" | python -m json.tool
echo
echo

# 6. 確認房間已刪除
echo "6. 確認房間已刪除 (應該回傳 404)"
echo "-----------------------------------"
curl -s "${API_BASE}/rooms/${ROOM_CODE}" || echo "(404 Not Found - 符合預期)"
echo
echo

echo "========================================="
echo "測試完成"
echo "========================================="
