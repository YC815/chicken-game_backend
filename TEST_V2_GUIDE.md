# Test Console v2.0 - 快速指南

## 🚀 新功能

### 1. 延遲公布機制
- ✅ 玩家提交動作後**不會立即看到結果**
- ✅ 管理員可以控制何時公布結果
- ✅ 實時顯示進度條（X/Y 人已選擇）

### 2. 新增按鈕
- 📢 **PUBLISH RESULTS** - 公布回合結果
- ⏭️ **SKIP ROUND** - 跳過回合（未提交的玩家自動選擇 TURN）

### 3. 新增 WebSocket 事件
- `ACTION_SUBMITTED` - 進度更新
- `ROUND_READY` - 等待公布
- `ROUND_ENDED` - 結果已公布

---

## 🧪 測試流程（v2.0）

### 1. 準備階段
```
Host Panel:
  1. CREATE ROOM
  2. (記下房間代碼)

Player 1 Panel:
  3. 輸入 Nickname: Alice
  4. JOIN ROOM

Player 2 Panel:
  5. 輸入 Nickname: Bob
  6. JOIN ROOM

Host Panel:
  7. 確認 Player Count = 2
  8. START GAME
```

---

### 2. 測試新功能：正常流程

```
WebSocket Log:
  ✓ ROOM_STARTED
  ✓ ROUND_STARTED (Round 1)

Player 1:
  1. GET ROUND INFO → Round 1, Status: waiting_actions
  2. GET OPPONENT → Bob
  3. ACCELERATE ✅

WebSocket Log:
  📊 ACTION_SUBMITTED: 1/2

Host Panel:
  → Progress Bar 顯示: 50% (1/2)

Player 2:
  4. GET ROUND INFO
  5. GET OPPONENT → Alice
  6. TURN ✅

WebSocket Log:
  📊 ACTION_SUBMITTED: 2/2
  ✅ ROUND_READY (Round 1 ready to publish!)

Host Panel:
  → Progress Bar 顯示: 100% (2/2)
  → "PUBLISH RESULTS" 按鈕啟用（橙色）
  → Round Status 顯示: READY_TO_PUBLISH

Player 1 & 2:
  → 顯示 "⏳ Waiting for host to publish results..."

Host Panel:
  7. 點擊 "PUBLISH RESULTS"

WebSocket Log:
  ✓ ROUND_ENDED

Player 1 & 2:
  → 自動取得結果並顯示
  → Payoff 顯示（綠色/紅色）
```

---

### 3. 測試新功能：跳過回合

```
Host Panel:
  1. NEXT ROUND → Round 2 開始

Player 1:
  2. ACCELERATE ✅

WebSocket Log:
  📊 ACTION_SUBMITTED: 1/2

Host Panel:
  → Progress Bar: 50% (1/2)
  → Player 2 長時間沒反應...

Host Panel:
  3. 點擊 "SKIP ROUND"
  4. 確認對話框 → 點擊 OK

WebSocket Log:
  ✓ ROUND_ENDED (SKIPPED)

Result:
  → Player 1: choice = accelerate
  → Player 2: choice = turn (自動填入)
  → 兩人都看到結果
```

---

### 4. 測試冪等性

```
Host Panel:
  1. NEXT ROUND → Round 3
  2. 兩位玩家都提交動作

WebSocket Log:
  ✅ ROUND_READY

Host Panel:
  3. 連續點擊 "PUBLISH RESULTS" 兩次

Result:
  ✓ 第一次：成功公布
  ✓ 第二次：按鈕自動禁用（不會重複公布）
```

---

## 🎨 UI 變化對照

### Host Panel

**舊版**:
```
2. Game Control
   [START GAME] [NEXT ROUND] [END GAME]

3. Special Actions
   [ASSIGN INDICATORS]
```

**新版**:
```
2. Game Control
   [START GAME] [NEXT ROUND] [END GAME]

3. Round Control (NEW!)
   [📢 PUBLISH RESULTS]  [⏭️ SKIP ROUND]

   Current Round: 3
   Round Status: READY_TO_PUBLISH
   Progress: [████████░░] 2/2

4. Special Actions
   [ASSIGN INDICATORS]
```

### Player Panel

**舊版**:
```
提交動作 → (自動取得結果)
```

**新版**:
```
提交動作 → "⏳ Waiting for host to publish results..."
          → (Host 公布後) 自動取得結果
```

---

## 🐛 除錯檢查點

### 進度條不更新？
- 檢查 WebSocket Events Log 是否收到 `ACTION_SUBMITTED`
- 確認 `state.roundProgress` 是否正確

### "PUBLISH RESULTS" 按鈕無法點擊？
- 檢查 Round Status 是否為 `READY_TO_PUBLISH`
- 確認收到 `ROUND_READY` 事件

### 玩家沒收到結果？
- 檢查是否收到 `ROUND_ENDED` 事件
- 確認自動呼叫 `getResult()` 是否成功
- 查看 Network Tab 的 `/result` API 請求

### "SKIP ROUND" 失敗？
- 檢查 Round Status（只能在 WAITING_ACTIONS 或 READY_TO_PUBLISH 時跳過）
- 確認 Host 的 `currentRoundNumber` 是否正確

---

## 📊 WebSocket Events 時間軸

```
Time  | Event               | 說明
------|---------------------|----------------------------------
00:00 | ROOM_STARTED        | 遊戲開始
00:01 | ROUND_STARTED       | Round 1 開始
00:10 | ACTION_SUBMITTED    | Player 1 提交（1/2）
00:15 | ACTION_SUBMITTED    | Player 2 提交（2/2）
00:15 | ROUND_READY         | 所有人都提交了，等待公布
00:20 | ROUND_ENDED         | Host 公布結果
00:25 | ROUND_STARTED       | Round 2 開始
...
```

---

## 🔥 壓力測試建議

### 並發提交
```
1. 兩位玩家「同時」點擊提交按鈕
2. 觀察進度條是否正確（應該是 2/2）
3. 確認沒有重複計算結果
```

### 快速點擊
```
1. Host 快速連續點擊 "PUBLISH RESULTS"
2. 確認只公布一次（冪等性）
3. 確認不會報錯
```

### 斷線重連
```
1. 關閉 WebSocket 連線（Network Tab → Offline）
2. 重新整理頁面
3. 確認可以補發事件（GET /events/since/{id}）
```

---

## 📝 與舊版的差異

| 項目 | 舊版 | 新版 |
|------|------|------|
| 結果公布 | 自動 | 手動（Host 控制）|
| 進度顯示 | 無 | 實時進度條 |
| WebSocket 事件 | 3 個 | 5 個（新增 2 個）|
| 狀態數量 | 3 個 | 4 個（新增 READY_TO_PUBLISH）|
| 管理員控制 | 無 | PUBLISH / SKIP 按鈕 |

---

## ✅ 測試清單

- [ ] 正常流程：提交 → 等待 → 公布 → 結果
- [ ] 跳過流程：部分提交 → 跳過 → 結果
- [ ] 進度條正確更新（每次提交都更新）
- [ ] 等待提示正確顯示（ROUND_READY 時）
- [ ] 等待提示正確隱藏（ROUND_ENDED 後）
- [ ] 冪等性：重複點擊 PUBLISH 不會錯誤
- [ ] 自動取得結果（ROUND_ENDED 後）
- [ ] 跳過的回合顯示特殊標記

---

## 🚀 開始測試

```bash
# 1. 啟動 Backend
cd backend
source .venv/bin/activate
uvicorn main:app --reload

# 2. 開啟測試頁面
open test_game_v2.html
# 或
python -m http.server 3000
# 然後訪問 http://localhost:3000/test_game_v2.html
```

---

**Built with Linus's "Good Taste" 🚀**
