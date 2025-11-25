# Chicken Game - Test Console Guide

## 這是什麼？

一個「斯巴達式」的測試網頁，用來測試 Chicken Game 的完整流程。

**特點**：
- 單一 HTML 檔案
- 三欄式佈局（Host + Player1 + Player2）
- 即時 WebSocket 監控
- 零依賴，純 Vanilla JavaScript

---

## 快速開始

### 1. 啟動 Backend Server

```bash
# 確保在 backend 目錄
cd backend

# 啟動 FastAPI server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 開啟測試頁面

```bash
# 使用瀏覽器開啟
open test_game.html

# 或使用任何 HTTP server
python -m http.server 3000
# 然後訪問 http://localhost:3000/test_game.html
```

---

## 完整測試流程

### 階段 0：準備

1. **Host Panel** - 點擊 `CREATE ROOM`
   - 自動連接 WebSocket
   - 取得房間代碼（會自動填入 Player1 和 Player2 的欄位）

2. **Player1 Panel** - 點擊 `JOIN ROOM`
   - 使用預設名稱 "Alice"

3. **Player2 Panel** - 點擊 `JOIN ROOM`
   - 使用預設名稱 "Bob"

4. **Host Panel** - 確認 Player Count = 2

---

### 階段 1：開始遊戲 + Round 1-4（正常對戰）

5. **Host Panel** - 點擊 `START GAME`
   - WebSocket 收到 `ROOM_STARTED`
   - 自動建立 Round 1
   - WebSocket 收到 `ROUND_STARTED`

6. **Player1 & Player2** - 點擊 `GET ROUND INFO`
   - 看到 Round Number = 1
   - Phase = normal
   - Status = waiting_actions

7. **Player1 & Player2** - 點擊 `GET OPPONENT`
   - 確認配對對手

8. **Player1 & Player2** - 選擇策略
   - 點擊 `⚡ ACCELERATE` 或 `🔄 TURN`
   - 兩人都提交後，WebSocket 收到 `ROUND_ENDED`

9. **Player1 & Player2** - 點擊 `GET RESULT`
   - 查看本輪結果（your_choice, opponent_choice, payoff）

10. **Host Panel** - 點擊 `NEXT ROUND`
    - 重複步驟 6-9，完成 Round 2, 3, 4

---

### 階段 2：Round 5-6（訊息階段）

11. **Host Panel** - 點擊 `NEXT ROUND` → Round 5 開始
    - Phase = message

12. **Player1 & Player2** - 查看配對後
    - 在 "Message (Round 5-6)" 區塊輸入訊息
    - 點擊 `SEND MESSAGE`
    - 對方點擊 `GET MESSAGE` 可以看到訊息

13. **Player1 & Player2** - 提交策略（同階段 1）

14. **Host Panel** - 點擊 `NEXT ROUND` → Round 6
    - 重複訊息和策略流程

---

### 階段 3：指標分配（Round 6 後）

15. **Host Panel** - 點擊 `ASSIGN INDICATORS`
    - WebSocket 收到 `INDICATORS_ASSIGNED`

16. **Player1 & Player2** - 點擊 `GET INDICATOR`
    - 看到自己的 symbol（例如：🍋）

---

### 階段 4：Round 7-10（協作階段）

17. **Host Panel** - 點擊 `NEXT ROUND` × 4
    - Round 7, 8, 9, 10
    - 流程與 Round 1-4 相同（配對、出招、結果）

---

### 最終階段：遊戲結束

18. **Host Panel** - 點擊 `END GAME`
    - WebSocket 收到 `GAME_ENDED`
    - 自動顯示 Game Summary

19. **Host Panel** - 查看 "Game Summary"
    - 玩家排名（按總分排序）
    - 策略統計（Accelerate vs Turn 比例）

---

## 資料流監控

### WebSocket Events

Host Panel 的 "WebSocket Events" 區塊會顯示所有即時事件：

```
[14:23:45] ✓ WebSocket connected
[14:23:50] 🎮 Game started!
[14:23:52] 🔄 Round 1 started (Phase: normal)
[14:24:10] ✓ Round 1 ended
[14:24:15] 🔄 Round 2 started (Phase: normal)
...
[14:30:20] 💬 Message phase activated
[14:32:00] 🎯 Indicators assigned
[14:35:00] 🏁 Game ended!
```

### Room Status

即時顯示房間狀態：
- Status: waiting / playing / finished
- Current Round: 0-10
- Player Count: 2

---

## 常見問題

### Q: WebSocket 顯示 DISCONNECTED？
A: 確認 FastAPI server 是否運行在 `localhost:8000`

### Q: 按鈕變成灰色無法點擊？
A: 檢查流程順序，例如 `START GAME` 必須在玩家加入後才能點擊

### Q: 沒有收到 WebSocket 事件？
A: 重新整理頁面，重新建立房間

### Q: GET RESULT 顯示 404？
A: 確認回合已結束（兩位玩家都提交策略後）

---

## Payoff Matrix（參考）

| you / other    | turn     | accelerate |
| -------------- | -------- | ---------- |
| **turn**       | (3, 3)   | (-3, 10)   |
| **accelerate** | (10, -3) | (-10, -10) |

---

## 技術架構

```
test_game.html
├── Host Panel
│   ├── Create Room (POST /api/rooms)
│   ├── Start Game (POST /api/rooms/{id}/start)
│   ├── Next Round (POST /api/rooms/{id}/rounds/next)
│   ├── End Game (POST /api/rooms/{id}/end)
│   └── Assign Indicators (POST /api/rooms/{id}/indicators/assign)
│
├── Player Panels (x2)
│   ├── Join Room (POST /api/rooms/{code}/join)
│   ├── Get Round Info (GET /api/rooms/{id}/rounds/current)
│   ├── Get Opponent (GET /api/rooms/{id}/rounds/{n}/pair)
│   ├── Submit Action (POST /api/rooms/{id}/rounds/{n}/action)
│   ├── Get Result (GET /api/rooms/{id}/rounds/{n}/result)
│   ├── Send Message (POST /api/rooms/{id}/rounds/{n}/message)
│   ├── Get Message (GET /api/rooms/{id}/rounds/{n}/message)
│   └── Get Indicator (GET /api/rooms/{id}/indicator)
│
└── WebSocket (/ws/{room_id})
    ├── ROOM_STARTED
    ├── ROUND_STARTED
    ├── ROUND_ENDED
    ├── MESSAGE_PHASE
    ├── INDICATORS_ASSIGNED
    └── GAME_ENDED
```

---

## Linus 的評語

> "This is good taste. Three columns, no bullshit, no frameworks. Just data structures and WebSocket events. If you can't test your game with this tool, the problem is your backend, not the tool."

**特點**：
- **消除特殊情況**：所有 API 都用同樣的模式呼叫
- **資料結構優先**：先顯示資料，再處理 UI
- **零破壞性**：純測試工具，不會改動任何 backend 程式碼
- **最笨但最清晰**：不用 React/Vue，直接操作 DOM

---

## 授權

MIT License - 用於測試目的，不建議用於生產環境
