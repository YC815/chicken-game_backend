# Changelog: 回合結果延遲公布功能

## 概要

將「計算結果」與「公布結果」分離，讓管理員可以控制何時公布回合結果。

**日期**: 2025-11-25
**版本**: v2.0
**Breaking Changes**: 是（WebSocket 事件和狀態機變更）

---

## 📋 變更摘要

### 核心變更
1. **新增 Round 狀態**: `READY_TO_PUBLISH`
2. **新增 WebSocket 事件**: `ACTION_SUBMITTED`, `ROUND_READY`
3. **新增 API 端點**: `POST /rounds/{n}/publish`, `POST /rounds/{n}/skip`
4. **修改狀態機**: 4 個狀態（原 3 個）
5. **修改提交邏輯**: 廣播進度，不立即公布結果

### 設計原則
- **關注點分離**: 計算 ≠ 公布
- **WebSocket = 通知**: 不傳遞完整資料，只通知事件
- **REST API = 資料**: 客戶端收到通知後主動 GET
- **冪等性**: 所有操作可重複呼叫
- **並發安全**: DB lock + 狀態機

---

## 🔄 狀態流程變更

### Before (v1.0)
```
WAITING_ACTIONS → CALCULATING → COMPLETED
```
**問題**: 計算完立即公布，管理員無法控制

### After (v2.0)
```
WAITING_ACTIONS → CALCULATING → READY_TO_PUBLISH → COMPLETED
```
**改進**: 管理員決定何時公布

---

## 📡 WebSocket 事件變更

### 新增事件

#### 1. ACTION_SUBMITTED（進度通知）
```json
{
  "event_type": "ACTION_SUBMITTED",
  "room_id": "uuid",
  "data": {
    "round_number": 3,
    "submitted": 4,
    "total": 6
  }
}
```
**觸發時機**: 每次玩家提交動作

#### 2. ROUND_READY（等待公布）
```json
{
  "event_type": "ROUND_READY",
  "room_id": "uuid",
  "data": {
    "round_number": 3
  }
}
```
**觸發時機**: 所有玩家都提交動作後

### 修改事件

#### ROUND_ENDED
**Before**: `submit_action` 自動觸發
**After**: 管理員呼叫 `/publish` 或 `/skip` 時觸發

```json
{
  "event_type": "ROUND_ENDED",
  "room_id": "uuid",
  "data": {
    "round_number": 3,
    "skipped": false  // 新增：是否為跳過
  }
}
```

---

## 🔌 API 變更

### 修改的端點

#### POST /rounds/{round_number}/action

**變更**: 不再自動廣播 `ROUND_ENDED`

**新行為**:
1. 提交動作（冪等）
2. 廣播 `ACTION_SUBMITTED`（進度）
3. 計算結果（如果 100%）
4. 廣播 `ROUND_READY`（等待公布）

### 新增的端點

#### POST /rounds/{round_number}/publish

**用途**: 公布回合結果

**前置條件**:
- Round 狀態 = `READY_TO_PUBLISH`

**效果**:
- 狀態轉換 → `COMPLETED`
- 廣播 `ROUND_ENDED`

**Request**:
```http
POST /api/rooms/{room_id}/rounds/3/publish
```

**Response**:
```json
{
  "status": "ok"
}
```

**錯誤**:
- `400`: Round not in READY_TO_PUBLISH status
- `404`: Round not found

---

#### POST /rounds/{round_number}/skip

**用途**: 跳過回合（管理員強制結束）

**前置條件**:
- Round 狀態 = `WAITING_ACTIONS` 或 `READY_TO_PUBLISH`

**效果**:
1. 為未提交的玩家填入預設選擇（TURN）
2. 計算結果
3. 立即公布

**Request**:
```http
POST /api/rooms/{room_id}/rounds/3/skip
```

**Response**:
```json
{
  "status": "ok"
}
```

**WebSocket**:
```json
{
  "event_type": "ROUND_ENDED",
  "data": {
    "round_number": 3,
    "skipped": true  // ← 標記
  }
}
```

---

## 🗄️ 資料庫變更

### Schema 變更

#### models.py
```python
class RoundStatus(str, enum.Enum):
    WAITING_ACTIONS = "waiting_actions"
    CALCULATING = "calculating"
    READY_TO_PUBLISH = "ready_to_publish"  # 新增
    COMPLETED = "completed"
```

### Migration

**文件**: `migrations/001_add_ready_to_publish_status.py`

**SQL**:
```sql
ALTER TYPE roundstatus ADD VALUE IF NOT EXISTS 'ready_to_publish';
```

**執行**:
```bash
source .venv/bin/activate
python migrations/001_add_ready_to_publish_status.py
```

**驗證**:
```sql
SELECT enumlabel
FROM pg_enum
WHERE enumtypid = 'roundstatus'::regtype
ORDER BY enumsortorder;
```

---

## 🔧 程式碼變更

### 1. models.py
- ✅ 新增 `RoundStatus.READY_TO_PUBLISH`

### 2. schemas.py
- ✅ 新增 `WSEventType.ACTION_SUBMITTED`
- ✅ 新增 `WSEventType.ROUND_READY`

### 3. core/round_manager.py
- ✅ 修改 `try_finalize_round()` - 停在 READY_TO_PUBLISH
- ✅ 新增 `publish_round()` - 公布結果

### 4. core/state_machine.py
- ✅ 更新 `VALID_TRANSITIONS` - 支援 4 個狀態

### 5. api/rounds.py
- ✅ 修改 `submit_action()` - 廣播進度和 ROUND_READY
- ✅ 新增 `publish_round_results()` - 公布端點
- ✅ 新增 `skip_round()` - 跳過端點
- ✅ 新增 WebSocket 通知函式

### 6. services/pairing_service.py
- ✅ 新增 `get_pairs_in_round()` - helper 函式

---

## 🧪 測試建議

### 前端測試清單

#### 玩家流程
- [ ] 提交動作後看到進度更新「X/Y 人已選擇」
- [ ] 所有人提交後看到「等待管理員公布結果...」
- [ ] 收到 ROUND_ENDED 後自動取得結果
- [ ] 跳過的回合顯示特殊標記

#### 管理員流程
- [ ] ROUND_READY 時顯示「公布結果」按鈕
- [ ] 點擊「公布結果」後所有人收到通知
- [ ] 「跳過回合」功能正常（確認對話框）
- [ ] 跳過後未提交的玩家顯示為 TURN

#### 邊界情況
- [ ] 重複點擊「公布結果」不會報錯
- [ ] 兩位玩家同時提交動作（並發測試）
- [ ] WebSocket 斷線後重連，補發事件
- [ ] 管理員離線，玩家仍可看到進度

---

## 🚨 Breaking Changes

### 1. WebSocket 事件順序變更

**Before**:
```
提交動作 → ROUND_ENDED
```

**After**:
```
提交動作 → ACTION_SUBMITTED → ROUND_READY → (管理員操作) → ROUND_ENDED
```

**影響**: 前端需要更新 WebSocket 監聽邏輯

### 2. ROUND_ENDED 不再自動觸發

**Before**: submit_action 自動廣播
**After**: 需要呼叫 /publish 或 /skip

**影響**:
- 前端需要新增「公布結果」按鈕
- 測試工具需要更新流程

### 3. Round 狀態多一個

**Before**: 3 個狀態
**After**: 4 個狀態

**影響**:
- 前端狀態判斷邏輯需要更新
- 如果有 status 的顯示 UI 需要新增

---

## 🔄 Migration 指南

### 後端 Migration

1. **拉取程式碼**
   ```bash
   git pull origin main
   ```

2. **執行 Migration**
   ```bash
   source .venv/bin/activate
   python migrations/001_add_ready_to_publish_status.py
   ```

3. **重啟 Server**
   ```bash
   uvicorn main:app --reload
   ```

### 前端 Migration

1. **新增進度顯示 UI**
   ```javascript
   ws.onmessage = (event) => {
     if (event.event_type === 'ACTION_SUBMITTED') {
       updateProgress(event.data.submitted, event.data.total)
     }
   }
   ```

2. **新增等待公布 UI**
   ```javascript
   if (event.event_type === 'ROUND_READY') {
     showWaitingForHost()
   }
   ```

3. **更新結果取得邏輯**
   ```javascript
   if (event.event_type === 'ROUND_ENDED') {
     // 保持不變，仍然 GET /result
     fetchResult()
   }
   ```

4. **新增管理員按鈕**
   ```html
   <button onclick="publishResults()">公布結果</button>
   <button onclick="skipRound()">跳過回合</button>
   ```

---

## 📊 性能影響

### 正面影響
- ✅ 減少前端不必要的輪詢
- ✅ WebSocket payload 更小（只傳通知）
- ✅ 資料由 REST API 提供（可 cache）

### 負面影響
- ⚠️ 多一次 WebSocket 廣播（ACTION_SUBMITTED）
- ⚠️ 管理員需要手動操作（增加延遲）

### 建議
- 未來可新增「自動公布模式」（config 設定）
- 可加入倒數計時（X 秒後自動公布）

---

## 🐛 已知問題

### 1. PostgreSQL Enum 順序
- `ready_to_publish` 被加到最後（不在 calculating 和 completed 之間）
- **影響**: 無（enum 順序不影響邏輯）
- **原因**: PostgreSQL 不支援 `ADD VALUE AFTER`

### 2. Migration 不可回滾
- PostgreSQL 不支援從 enum 移除值
- **解法**: 保留該值（不影響舊邏輯）
- **注意**: 如果真的要回滾，需要重建整個 enum type

---

## 📚 相關文件

- [TEST_GUIDE.md](./TEST_GUIDE.md) - 測試指南（需更新）
- [API 文件](./api/) - OpenAPI schema（需更新）
- [前端整合範例](#) - 前端程式碼範例

---

## 👥 貢獻者

- **Claude (Sonnet 4.5)** - 全部實作
- **Linus Torvalds** - 精神導師（"Good Taste" 設計哲學）

---

## 🙏 特別感謝

> "Good taste is something that requires thought. It requires a willingness to say 'no, this is not the right way to do it, we should do it this way instead.'"
> — Linus Torvalds

這次重構體現了 Linus 的核心原則：
- **消除特殊情況**: 任何人都可以呼叫 publish/skip，不需要判斷「誰是最後一個」
- **分離關注點**: 計算結果 vs 公布結果
- **資料結構優先**: WebSocket 只傳通知，REST API 傳資料
- **簡單明確**: 4 個狀態清楚表達流程

---

**Built with Linus's "Good Taste" 🚀**
