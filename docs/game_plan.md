# Game Plan：多人賽局教學遊戲系統（全局規劃）

## 1. 專案目標與定位

本專案是一個 **「玩遊戲學經濟」用的多人互動賽局系統**，主要在教室環境使用：

- 學生使用手機進入遊戲（Player 端）
- 老師使用教室大螢幕控制遊戲流程（Host 端）
- 遊戲內容以「膽小鬼賽局（Chicken Game）」為核心，分多輪進行，逐步加入社會互動與協作元素
- 目標是讓學生「親身體驗賽局理論，而不是只聽講」

系統設計原則：

1. **回合制（Turn-based）**，不做 heavy realtime（FPS 那種）
2. **Pseudo-realtime + 輕量 WebSocket event**，穩定、好維護
3. **前後端分離**：Next.js（前端）＋ FastAPI（後端）＋ PostgreSQL（DB）
4. 遊戲規則可持續擴充（未來可以加囚徒困境、公地悲劇等）

---

## 2. 使用情境（User Stories）

### 2.1 Host（老師）

- 在大螢幕打開 Host 頁面，點擊「建立房間」
- 系統產生房間代碼與 QR Code，顯示當前玩家人數
- 等學生加入，確認人數為偶數後，按「開始遊戲」
- 控制每一輪開始 / 下一輪 / 特殊階段（顯示指示物、分組）
- 遊戲過程中即時看到：策略比例、總收益、排名
- 遊戲結束後顯示全局統計，作為課程討論材料

### 2.2 Player（學生）

- 用手機掃描 QR Code 或輸入房號與暱稱加入
- 在「等待開始」畫面等待 Host 啟動遊戲
- 每輪看到對手代號，選擇：加速 / 轉彎
- 看到本輪結果（自己 vs 對手、雙方 payoff）
- 第 5–6 輪可對對手留下匿名短訊
- 第 6 輪後收到「指示物」，線下尋找同組隊友
- 第 7–10 輪與隊友面對面討論策略後一起作出選擇
- 最後看到自己與隊伍的累積成績

---

## 3. 遊戲規則與階段設計

### 3.1 基本膽小鬼賽局 payoff

以你提供的 payoff 為基準（Player 1, Player 2）：

|              | 對方：轉彎 | 對方：加速 |
| ------------ | ---------- | ---------- |
| **你：轉彎** | 3, 3       | -3, 10     |
| **你：加速** | 10, -3     | -10, -10   |

此 payoff 由後端統一計算，前端不自行算分。

---

### 3.2 回合設計（10 輪）

- **Round 1–4：Baseline**

  - 純配對 + 選擇 + 看結果
  - 所有人匿名、隨機配對
  - 用來蒐集「初始策略分佈」

- **Round 5–6：留言階段**

  - 每輪結束後，玩家可對本輪對手留一句匿名訊息（可選）
  - 下一輪開始前顯示給對方
  - 用來讓學生體驗「信號（signaling）」對策略的影響

- **Round 6 結束後：指示物發放**

  - 系統對每位玩家發一個「指示物」（顏色/圖案/emoji…）
  - 玩家要在教室中找到與自己相同指示物的人，組成隊伍
  - 後端建立 team 關係

- **Round 7–10：隊伍協作階段**
  - 玩家以隊伍為單位討論策略
  - 遊戲配對改為「隊伍 vs 隊伍」
  - payoff 以隊伍總和計算
  - 觀察協商、承諾、聲譽對策略的影響

---

## 4. 技術架構

### 4.1 系統構成

- **Frontend**

  - Framework：Next.js
  - UI：Tailwind CSS
  - Views：
    - Host View（大螢幕 / 老師）
    - Player View（手機 / 學生）
  - 通訊：
    - REST API（POST 行為、GET 狀態）
    - WebSocket Client（收 event）

- **Backend**

  - Framework：FastAPI
  - 職責：
    - 房間管理（Room）
    - 玩家管理（Player）
    - 回合管理（Round）
    - 配對邏輯（Matching）
    - payoff 計算
    - 留言訊息儲存與提供
    - 指示物與隊伍分配
    - WebSocket event broadcast
    - REST API 實作

- **Database**
  - PostgreSQL
  - 表結構：`rooms`, `players`, `rounds`, `pairs`, `actions`, `messages`, `teams`, `indicators` 等

---

## 5. 通訊模式（Data Flow / Realtime 策略）

### 5.1 核心模式

1. **Player → Backend：POST 行為**

   - 加入房間、提交策略、送出留言、隊伍決策

2. **Backend → Player：WebSocket 事件（只傳「有事發生」，不傳大量資料）**

   - `ROUND_STARTED`, `ROUND_ENDED`, `SHOW_INDICATORS`, `SHOW_TEAMS`, etc.

3. **Player → Backend：GET 拉資料（根據事件更新 UI）**
   - GET `/state`, `/current_round`, `/results`, `/messages`, `/team_info`, etc.

### 5.2 類 Kahoot 的實作模式

- Host 端控制遊戲流程，作為「主時鐘（game loop driver）」
- 每次 Host 操作（開始遊戲 / 下一輪 / 特殊階段）會：
  1. 呼叫 REST API 更新 server 狀態
  2. Backend 透過 WebSocket broadcast event 給該房間所有玩家
  3. Player 與 Host 端收到 event 後透過 GET API 拉最新 game state

---

## 6. 系統需求與限制

- 支援 **20–60 人** 同時參與單一 Room
- 每輪時間約 30–60 秒
- 標準教室 Wi-Fi 環境
- 手機瀏覽器 Chrome / Safari 即可（不需安裝 App）
- 要求穩定優先於極致低延遲

---

## 7. 開發拆工與優先順序

### 7.1 MLP（Minimum Lovable Product）第一階段

1. Room 建立 / 加入
2. 玩家列表 & 玩家數顯示
3. 配對 + 選擇策略 + payoff 計算
4. Round 1–4 流程（無留言、無隊伍）
5. Host 控制面板（開始 / 下一輪）
6. 基本統計（每輪策略比例）

### 7.2 第二階段（擴充）

1. Round 5–6 留言功能
2. Round 6 結束後指示物派發
3. Team 分組與隊伍對戰邏輯（Round 7–10）
4. 結算畫面（個人 & 隊伍排名）
5. 匿名代碼與 UI 美術強化

### 7.3 第三階段（未來 Roadmap）

- 複數賽局類型支援（囚徒困境、公共財遊戲等）
- 遊戲記錄下載 / 匯出為教學報告
- 教師後台（歷史房間 / 成績紀錄）

---
