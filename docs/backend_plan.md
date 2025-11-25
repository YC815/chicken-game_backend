# Backend Plan（FastAPI + PostgreSQL）

---

## 1. 目標定位

Backend 的職責：

- 提供 **乾淨、可擴充的遊戲邏輯**
- 提供 REST API（主要負責 CRUD + 狀態查詢）
- WebSocket **只負責廣播事件（不傳大量資料）**
- 管理：

  - 房間（Room）
  - 玩家（Player）
  - 回合（Round）
  - 配對（Pair）
  - 策略選擇（Action）
  - 留言（Message：Round 5–6）
  - 指示物（Indicator：Round 6 後）

- 不再管理 team vs team、team payoff
- 遊戲結果僅以「個人 payoff 累計」呈現

---

## 2. 技術選型

- **FastAPI**
- Python 3.11+
- DB：**PostgreSQL**
- ORM：SQLAlchemy or SQLModel
- Migration：Alembic
- WebSocket：FastAPI websocket router
- Deployment：Railway / Render / Zeabur
- 設計原則：

  - Server 為「事實的來源」
  - WebSocket event 僅告知「狀態變更」
  - 前端自行 GET 最新資料

---

## 3. 資料模型（Domain Models）— _精簡後版本_

### 3.1 `Room`

| 欄位            | 說明                               |
| --------------- | ---------------------------------- |
| `id`            | UUID                               |
| `code`          | 房號（4–6 字母）                   |
| `status`        | `waiting` / `playing` / `finished` |
| `current_round` | int                                |
| `created_at`    | timestamp                          |
| `updated_at`    | timestamp                          |

---

### 3.2 `Player`

| 欄位           | 說明                     |
| -------------- | ------------------------ |
| `id`           | UUID                     |
| `room_id`      | FK                       |
| `nickname`     | 玩家輸入的名字           |
| `display_name` | 例如系統分配的「狐貍 3」 |
| `joined_at`    | timestamp                |
| `is_host`      | bool                     |

---

### 3.3 `Round`

| 欄位           | 說明                                            |
| -------------- | ----------------------------------------------- |
| `id`           | UUID                                            |
| `room_id`      | FK                                              |
| `round_number` | 1–10                                            |
| `phase`        | `normal` / `message` / `indicator`              |
| `status`       | `waiting_actions` / `calculating` / `completed` |
| `started_at`   | timestamp                                       |
| `ended_at`     | timestamp                                       |

> ⚠️ 已移除 team vs team / 協作 phase
> Round 7–10 的協作是線下討論，不由 server 控制

---

### 3.4 `Pair`（每輪配對）

| 欄位         | 說明 |
| ------------ | ---- |
| `id`         | UUID |
| `room_id`    | FK   |
| `round_id`   | FK   |
| `player1_id` | UUID |
| `player2_id` | UUID |

> ⚠️ 移除 team1_id, team2_id（不再需要 team vs team 結構）

---

### 3.5 `Action`（玩家選擇）

| 欄位         | 說明                       |
| ------------ | -------------------------- |
| `id`         | UUID                       |
| `room_id`    | FK                         |
| `round_id`   | FK                         |
| `player_id`  | FK                         |
| `choice`     | `"accelerate"` or `"turn"` |
| `payoff`     | int（計算完成後寫入）      |
| `created_at` | timestamp                  |

---

### 3.6 `Message`（Round 5–6）

| 欄位          | 說明      |
| ------------- | --------- |
| `id`          | UUID      |
| `room_id`     | FK        |
| `round_id`    | FK        |
| `sender_id`   | FK        |
| `receiver_id` | FK        |
| `content`     | str       |
| `created_at`  | timestamp |

---

### 3.7 `Indicator`（Round 6 後，用來找隊友）

| 欄位        | 說明                                  |
| ----------- | ------------------------------------- |
| `id`        | UUID                                  |
| `room_id`   | FK                                    |
| `player_id` | FK                                    |
| `symbol`    | emoji / 顏色碼 / 圖示代號（如「🍋」） |

> ⚠️ 這是唯一與 Round 7–10 協作相關的資料。
> Server 不需要知道他們在線下如何分組，也不用產生 team。

---

## 4. 系統事件（Server → Client WebSocket）

WebSocket 事件僅傳「狀態變化」，資料由前端 GET。

| event type            | 時機            |
| --------------------- | --------------- |
| `ROOM_STARTED`        | Host 開始遊戲   |
| `ROUND_STARTED`       | Host 啟動下一輪 |
| `ROUND_ENDED`         | 後端完成計算    |
| `MESSAGE_PHASE`       | Round 5–6       |
| `INDICATORS_ASSIGNED` | Round 6 結束後  |
| `GAME_ENDED`          | Host 結束遊戲   |

> ⚠️ 移除：`TEAMS_REVEALED`
> 因為協作階段不需要任何後端 team 結構

---

## 5. API 設計（REST）

> 所有 API 前綴 `/api`.

以下為最重要的端口（清爽、沒有 team 結構）。

---

### 5.1 房間相關

#### `POST /api/rooms`

建立房間（Host 使用）

Response:

```json
{
  "room_id": "uuid",
  "code": "ABCD",
  "host_player_id": "uuid"
}
```

---

### 5.2 玩家相關

#### `POST /api/rooms/{code}/join`

加入房間

Request:

```json
{ "nickname": "小明" }
```

Response:

```json
{
  "player_id": "uuid",
  "room_id": "uuid",
  "display_name": "狐狸 3"
}
```

---

### 5.3 遊戲流程控制（Host）

#### `POST /api/rooms/{room_id}/start`

開始遊戲 → 廣播 `ROOM_STARTED`

#### `POST /api/rooms/{room_id}/rounds/next`

產生下一輪配對 → 廣播 `ROUND_STARTED`

#### `POST /api/rooms/{room_id}/end`

結束遊戲 → 廣播 `GAME_ENDED`

---

### 5.4 回合資訊

#### `GET /api/rooms/{room_id}/rounds/current`

回傳目前 round 狀態

Example response:

```json
{
  "round_number": 6,
  "phase": "message",
  "status": "waiting_actions"
}
```

---

### 5.5 配對查詢（Player）

#### `GET /api/rooms/{room_id}/rounds/{round_number}/pair?player_id=...`

Response:

```json
{
  "opponent_id": "uuid",
  "opponent_display_name": "虎 5"
}
```

---

### 5.6 玩家出招（Action）

#### `POST /api/rooms/{room_id}/rounds/{round_number}/action`

Request:

```json
{
  "player_id": "uuid",
  "choice": "accelerate"
}
```

Response（成功）:

```json
{ "status": "ok" }
```

---

### 5.7 取得本輪結果（個人視角）

#### `GET /api/rooms/{room_id}/rounds/{round_number}/result?player_id=...`

Response:

```json
{
  "opponent_display_name": "熊 8",
  "your_choice": "turn",
  "opponent_choice": "accelerate",
  "your_payoff": -3,
  "opponent_payoff": 10
}
```

---

### 5.8 留言（Round 5–6）

#### `POST /api/rooms/{room_id}/rounds/{round}/message`

Request:

```json
{
  "sender_id": "uuid",
  "content": "下一輪我們合作吧？"
}
```

Server 自動比對 pair 找 receiver。

#### `GET /api/rooms/{room_id}/rounds/{round}/message?player_id=...`

取得「別人留給你的訊息」

---

### 5.9 指示物（Round 6 後）

#### `POST /api/rooms/{room_id}/indicators/assign`

Host 觸發 → Server 為所有玩家分配 indicator
（例如四種 emoji 等量隨機分配）

→ 廣播 `INDICATORS_ASSIGNED`

#### `GET /api/rooms/{room_id}/indicator?player_id=...`

Response:

```json
{ "symbol": "🍋" }
```

---

### 5.10 Summary

#### `GET /api/rooms/{room_id}/summary`

Response:

```json
{
  "players": [
    {
      "display_name": "狐狸 3",
      "total_payoff": 21
    },
    {
      "display_name": "老鷹 1",
      "total_payoff": -5
    }
  ],
  "stats": {
    "accelerate_ratio": 0.62,
    "turn_ratio": 0.38
  }
}
```

> 沒有 team payoff，只有「個人」＋「全局統計」

---

## 6. 伺服器核心邏輯（Game Logic）

### 6.1 配對邏輯 Pairing

只在 Round 1 隨機配一次，之後各回合都沿用 Round 1 的對手組合：

1. 取得所有 players
2. Round 1 打亂後兩兩成對並存入 pairs 表
3. 後續回合建立新 pairs 記錄，但直接複製 Round 1 的配對

### 6.2 payoff 計算

使用固定矩陣：

| you / other    | turn     | accelerate |
| -------------- | -------- | ---------- |
| **turn**       | (3, 3)   | (-3, 10)   |
| **accelerate** | (10, -3) | (-10, -10) |

### 6.3 留言邏輯（Round 5–6）

- 當 round.phase = `message` 時才允許存入 message
- 每 player 只可送出 1 則（可選）

### 6.4 指示物邏輯

- 在 Round 6 completed 後，host 執行指示物分配
- Server 將（symbol → players）均勻隨機分群
- 只存 symbol，不存 team 結構

### 6.5 協作階段（Round 7–10）

> 完全由線下進行，後端不管理
> 這是本系統的最大簡化！

- 前端 UI 顯示提示即可
- Server 在 Round 7–10 時使用和 Round 1–4 **完全同樣的流程**
- 無 team payoff、無討論紀錄、無同步限制

---

## 7. WebSocket 事件流程（簡化後）

1. Host → `POST /start`
   → 全房間廣播 `ROOM_STARTED`

2. Host → `POST /rounds/next`
   → Server 產生配對
   → 廣播 `ROUND_STARTED`

3. 所有選擇送出後
   → Server 計算 payoff
   → 廣播 `ROUND_ENDED`

4. Round 5–6
   → 廣播 `MESSAGE_PHASE`

5. Round 6 結束後
   → Host 触發指示物
   → 廣播 `INDICATORS_ASSIGNED`

6. Host → `POST /end`
   → 廣播 `GAME_ENDED`

---

## 8. 資安與防濫用

- player_id 綁定 WebSocket，避免 impersonation
- 每輪僅允許送一次 action
- message 長度限制 100 chars
- 房號 code 需使用 4–6 random uppercase letters
- indicator symbol 白名單（避免前端 injection）

---

## 9. 未來擴充（Roadmap）

- 增加其他賽局模式：囚徒困境、公地悲劇
- 教師後台（歷史記錄、匯出 CSV）
- 自動產生學術分析圖（平均策略、dominant strategy 變化）
- 遊戲調整工具：允許教師自訂 payoff 矩陣
- 兼容多個賽局並行

---
