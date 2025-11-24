# Backend Plan（FastAPI + PostgreSQL）

## 1. 目標定位

Backend 的職責是：

- 提供 **純粹的遊戲邏輯與資料服務**
- 透過 REST API + WebSocket 通知
- 管理房間、玩家、回合、配對、策略、留言、隊伍、指示物
- 不處理 UI，只回傳 JSON

---

## 2. 技術選型

- Framework：**FastAPI**
- 語言：Python 3.11+
- Web Server：Uvicorn / Gunicorn
- DB：PostgreSQL（使用 SQLAlchemy 或 SQLModel）
- Migration：Alembic
- WebSocket：FastAPI 的原生 WebSocket 支援
- 部署：Render / Railway / Zeabur（三擇一）

---

## 3. 資料模型（Domain Models）

### 3.1 `Room`

- `id` (UUID / short code)
- `code` (公開房號，例如「ABCD」)
- `status` (`waiting`, `playing`, `finished`)
- `current_round` (int)
- `created_at`
- `updated_at`

### 3.2 `Player`

- `id`
- `room_id`
- `nickname`
- `display_name`（例如系統生成動物名）
- `is_host` (bool)
- `joined_at`

### 3.3 `Round`

- `id`
- `room_id`
- `round_number` (1–10)
- `phase` (`normal`, `message`, `indicator`, `team`)
- `status` (`waiting_actions`, `calculating`, `completed`)
- `started_at`
- `ended_at`

### 3.4 `Pair`（配對）

- `id`
- `room_id`
- `round_id`
- `player1_id`
- `player2_id`
- `team_vs_team` (bool) — Round 7–10 可能是隊伍 vs 隊伍
- `team1_id`（可選）
- `team2_id`（可選）

### 3.5 `Action`

- `id`
- `room_id`
- `round_id`
- `player_id`
- `choice` (`accelerate`, `turn`)
- `payoff` (int) — 計算後寫入
- `created_at`

### 3.6 `Message`（匿名留言）

- `id`
- `room_id`
- `round_id`
- `sender_id`
- `receiver_id`
- `content` (str, 限長)
- `created_at`

### 3.7 `Indicator`（指示物）

- `id`
- `room_id`
- `player_id`
- `symbol` (str；emoji / 顏色 / 圖案代碼)

### 3.8 `Team`

- `id`
- `room_id`
- `name` / `symbol`
- `created_at`

### 3.9 `TeamMember`

- `id`
- `team_id`
- `player_id`

---

## 4. REST API 設計（重點）

> URL prefix 建議統一為 `/api`.

### 4.1 房間相關

#### `POST /api/rooms`

- 功能：建立房間（Host 使用）
- Request：
  - 可選：`host_nickname`
- Response：

```json
{
  "room_id": "uuid",
  "code": "ABCD",
  "host_player_id": "uuid"
}
```
