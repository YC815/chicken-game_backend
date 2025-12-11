# 2025-12-11 新版 API 串接手冊（短輪詢、無 WebSocket）

**目的**：讓前端開發者在最短時間完成串接。新版以 REST + 短輪詢為唯一通道，完全去 WebSocket 化。

## 0. 快速重點
- **輪詢入口**：`GET /api/rooms/{room_id}/state?version=<int>&player_id=<uuid>` 每 1~1.5 秒。
- **版本號**：後端用 `state_version` 控制，client 帶上上次的 `version`，相同則回傳 `has_update=false`，不同才回完整快照。
- **Host 只管流程**：Host 不參與對局，僅執行 start / publish / next / end / assign indicators。
- **回合狀態**：`waiting_actions` → `ready_to_publish` → `completed`。
- **特別回合**：第 5-6 回合可互傳訊息；第 7 回合起可顯示指標（emoji）。

## 1. 環境設定
- Base URL：`http://localhost:8000`
- 啟動：`python main.py`
- 所有範例皆假設已啟動在本機 8000 port。

## 2. 短輪詢規則（新版重點）
- Endpoint：`GET /api/rooms/{room_id}/state`
- Query：
  - `version`：int，預設 0；帶上你上次收到的 `version`。
  - `player_id`：可選，帶了才會返回個人化欄位（對手、訊息、indicator）。
- 節奏：每 1000~1500ms 呼叫一次；`has_update=false` 時可延長到 2s。
- 回傳格式：

**無更新**
```json
{
  "version": 12,
  "has_update": false
}
```

**有更新（範例）**
```json
{
  "version": 13,
  "has_update": true,
  "data": {
    "room": {
      "room_id": "550e8400-e29b-41d4-a716-446655440000",
      "code": "ABC123",
      "status": "PLAYING",
      "current_round": 2,
      "player_count": 6
    },
    "players": [
      {"player_id": "p1", "display_name": "狐狸 1", "is_host": false}
    ],
    "round": {
      "round_number": 2,
      "phase": "NORMAL",
      "status": "ready_to_publish",
      "submitted_actions": 6,
      "total_players": 6,
      "your_choice": "ACCELERATE",
      "opponent_choice": "TURN",
      "opponent_display_name": "狐狸 2",
      "your_payoff": 10,
      "opponent_payoff": -3
    },
    "indicators_assigned": false,
    "indicator_symbol": null,
    "message": null
  }
}
```

**前端 UI 觀察點**
- `room.status == "PLAYING"`：顯示回合 UI。
- `round.status == "waiting_actions"`：開放操作按鈕。
- `round.status == "ready_to_publish"`：Host 顯示「發布結果」按鈕。
- `round.status == "completed"`：玩家呼叫 `/result` 顯示結果。
- `message` 不為 null：顯示對手訊息（僅第 5-6 回合）。
- `indicators_assigned == true`：顯示 `indicator_symbol`（第 7 回合起）。

## 2.1 /state 完整 Schema（建議前端建立型別）
```ts
interface RoomStateResponse {
  version: number;
  has_update: boolean;
  data?: {
    room: {
      room_id: string;
      code: string;
      status: "WAITING" | "PLAYING" | "FINISHED";
      current_round: number;
      player_count: number; // 不含 host
    };
    players: Array<{
      player_id: string;
      display_name: string;
      is_host: boolean;
    }>;
    round: {
      round_number: number;
      phase: "NORMAL" | "MESSAGE" | "INDICATOR";
      status: "waiting_actions" | "ready_to_publish" | "completed";
      submitted_actions: number;
      total_players: number;
      // 以下為個人化欄位，需帶 player_id 才會存在
      your_choice?: "TURN" | "ACCELERATE" | null;
      opponent_choice?: "TURN" | "ACCELERATE" | null;
      opponent_display_name?: string | null;
      your_payoff?: number | null;
      opponent_payoff?: number | null;
    };
    message?: string | null;            // 第 5-6 回合才可能有值
    indicator_symbol?: string | null;   // 指標已派發才有值
    indicators_assigned: boolean;
  };
}
```

## 3. 兩種典型流程

### 3.1 Host（房主）
1. 建立房間  
   ```bash
   curl -X POST http://localhost:8000/api/rooms -H "Content-Type: application/json" -d '{}'
   # 取得 room_id, code, host_player_id
   ```
2. 等玩家加入（前端可輪詢 `GET /api/rooms/{code}` 看 player_count）。
3. 開始遊戲（自動生成第 1 回合並配對）  
   ```bash
   curl -X POST http://localhost:8000/api/rooms/{room_id}/start
   ```
4. 每回合循環  
   - 等玩家提交（靠 `/state` 看 `round.status`）。
   - 發布結果：`POST /api/rooms/{room_id}/rounds/{n}/publish`
   - 下一回合：`POST /api/rooms/{room_id}/rounds/next`
   - 若需跳過（緊急）：`POST /api/rooms/{room_id}/rounds/{n}/skip`
   - 第 6 回合後一次性派發指標：`POST /api/rooms/{room_id}/indicators/assign`
5. 結束遊戲  
   ```bash
   curl -X POST http://localhost:8000/api/rooms/{room_id}/end
   ```
6. 查總結  
   ```bash
   curl http://localhost:8000/api/rooms/{room_id}/summary
   ```

### 3.2 Player（玩家）
1. 透過房間代碼加入  
   ```bash
   curl -X POST http://localhost:8000/api/rooms/{code}/join \
     -H "Content-Type: application/json" \
     -d '{"nickname": "Alice"}'
   # 拿到 player_id, room_id, display_name
   ```
2. 開始短輪詢 `/state`（version=0，帶上 player_id）。
3. 每回合：
   - 查看對手：`/state.round.opponent_display_name` 或 `GET /api/rooms/{room_id}/rounds/{n}/pair?player_id=...`
   - 提交動作：  
     ```bash
     curl -X POST http://localhost:8000/api/rooms/{room_id}/rounds/{n}/action \
       -H "Content-Type: application/json" \
       -d '{"player_id": "...", "choice": "ACCELERATE"}'
     ```
   - 結果已發布時取結果：`GET /api/rooms/{room_id}/rounds/{n}/result?player_id=...`
   - 第 5-6 回合：一次訊息  
     ```bash
     curl -X POST http://localhost:8000/api/rooms/{room_id}/rounds/{n}/message \
       -H "Content-Type: application/json" \
       -d '{"sender_id": "...", "content": "Let's both turn!"}'
     ```
   - 指標（第 7 回合起）：`GET /api/rooms/{room_id}/indicator?player_id=...`
4. `room.status == "FINISHED"` 時停止輪詢並顯示 summary。

## 4. 必用端點快速索引

| 功能 | Method & Path | 說明 | 回傳關鍵欄位 |
| ---- | ------------- | ---- | ------------ |
| 建房 | `POST /api/rooms` | 建立房間並自動產生 Host player | room_id, code, host_player_id |
| 查房 | `GET /api/rooms/{code}` | 依代碼查狀態/人數 | room_id, status, current_round, player_count |
| 開始 | `POST /api/rooms/{room_id}/start` | Host 開始遊戲（同時建立第 1 回合） | status=ok |
| 下一回合 | `POST /api/rooms/{room_id}/rounds/next` | Host 建立下一回合 | status, round_number |
| 跳過 | `POST /api/rooms/{room_id}/rounds/{n}/skip` | Host 強制完成當前回合 | status=ok |
| 發布 | `POST /api/rooms/{room_id}/rounds/{n}/publish` | Host 將結果公開 | status=ok |
| 結束 | `POST /api/rooms/{room_id}/end` | Host 結束整場遊戲 | status=ok |
| 總結 | `GET /api/rooms/{room_id}/summary` | 取得排名與統計 | players[], stats |
| 加入 | `POST /api/rooms/{code}/join` | 玩家加入 | player_id, room_id, display_name |
| 配對 | `GET /api/rooms/{room_id}/rounds/{n}/pair` | 查本回合對手 | opponent_id, opponent_display_name |
| 動作 | `POST /api/rooms/{room_id}/rounds/{n}/action` | 提交 TURN / ACCELERATE | status=ok |
| 結果 | `GET /api/rooms/{room_id}/rounds/{n}/result` | 取得個人結果 | your_choice, opponent_choice, payoff |
| 訊息 | `POST /api/rooms/{room_id}/rounds/{n}/message` | 第 5-6 回合一次訊息 | status=ok |
| 收訊息 | `GET /api/rooms/{room_id}/rounds/{n}/message` | 拿到對手訊息 | content |
| 指標 | `POST /api/rooms/{room_id}/indicators/assign` / `GET /api/rooms/{room_id}/indicator` | Host 派發 / 玩家查 emoji | indicator_symbol |
| 短輪詢 | `GET /api/rooms/{room_id}/state` | 回傳 has_update + 快照 | version, has_update, data |

## 5. 狀態與 UI 對應
- 房間：`WAITING`（可加入）→ `PLAYING`（遊戲中）→ `FINISHED`（結束）。
- 回合：`waiting_actions`（開放提交）→ `ready_to_publish`（全員交卷，等 Host）→ `completed`（可看結果）。
- 回合階段：`NORMAL`（1-4, 7-10）、`MESSAGE`（5-6，可傳訊息）、`INDICATOR`（7+，顯示指標）。
- Host 不參與對局；所有玩家交卷後才由 Host 公布結果。

### 5.1 回合狀態時序（Host/玩家對應）
| 觸發者 | 行為 | round.status | UI 提示 |
| ------ | ---- | ------------ | ------- |
| 系統 | 建立新回合 | waiting_actions | 玩家看到對手與回合資訊，按鈕開啟 |
| 玩家 | POST /action | waiting_actions（submitted_actions 累計） | 可顯示「已提交」；仍等待其他人 |
| 系統 | 全員提交完 | ready_to_publish | Host 顯示「發布結果」按鈕 |
| Host | POST /publish | completed | 玩家可呼叫 `/result` 顯示結果 |
| Host | POST /rounds/next | 下一輪 waiting_actions | 流程重複 |

## 6. 錯誤處理速查
- HTTP 400：常見如 `Invalid player count`、`Invalid state transition`、`Messages are only allowed in Round 5-6`。
- HTTP 404：`Room not found`、`Round not found`、`Result not available yet`、`Indicator not found`。
- 錯誤格式：`{"detail": "錯誤訊息"}`，前端可直接顯示或映射成提示。

## 7. 前端實作備忘（建議）
- 保持單一 `stateVersion` 變數，呼叫 `/state` 後更新；`has_update=false` 直接沿用舊 UI。
- 提交動作後即可鎖按鈕，等待 `/state` 告知回合狀態變化。
- Host 頁面用 `/state` 判斷是否顯示「發布結果」、「下一回合」等控制。
- 進入第 5-6 回合時顯示訊息輸入框；第 7 回合起顯示 indicator。
- `FINISHED` 後停止輪詢，跳 summary。

## 8. ENUM 一覽（大小寫統一）
- Room.status：`WAITING` | `PLAYING` | `FINISHED`
- Round.status：`waiting_actions` | `ready_to_publish` | `completed`
- Round.phase：`NORMAL` | `MESSAGE` | `INDICATOR`
- Player.choice：`TURN` | `ACCELERATE`
