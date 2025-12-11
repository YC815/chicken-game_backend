# Chicken Game Backend - API Integration Guide

**Purpose:** This document provides a complete, no-nonsense guide to integrate with the Chicken Game backend. It now uses pure REST + short polling with `state_version` (WebSocket removed; legacy notes kept at the bottom for reference).

**Target Audience:** Frontend developers, mobile developers, or anyone building a client for this game.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core Concepts](#core-concepts)
3. [Game Flow](#game-flow)
4. [REST API Reference](#rest-api-reference)
5. [Short Polling Guide](#short-polling-guide)
6. [Legacy WebSocket Notes](#legacy-websocket-notes)
7. [Error Handling](#error-handling)
8. [Special Rules](#special-rules)

---

## Quick Start

**Goal:** Run through the entire game flow in 5 minutes using curl.

### Prerequisites

```bash
# Start the backend
python main.py
# Server runs at http://localhost:8000
```

### Step 1: Host Creates Room

```bash
curl -X POST http://localhost:8000/api/rooms \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "ABC123",
  "host_player_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

**Save these values:**
- `code`: Players use this to join
- `room_id`: Used in all subsequent API calls
- `host_player_id`: The host's player ID (host is also a player, but with `is_host=true`)

### Step 2: Players Join Room

```bash
curl -X POST http://localhost:8000/api/rooms/ABC123/join \
  -H "Content-Type: application/json" \
  -d '{"nickname": "Alice"}'
```

**Response:**
```json
{
  "player_id": "770e8400-e29b-41d4-a716-446655440001",
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "display_name": "Alice"
}
```

**Note:**
- Players cannot join once the game has started (status != WAITING)
- You need at least 2 players (even number) to start

### Step 3: Check Room Status

```bash
curl http://localhost:8000/api/rooms/ABC123
```

**Response:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "ABC123",
  "status": "WAITING",
  "current_round": 0,
  "player_count": 2
}
```

### Step 4: Host Starts Game

```bash
curl -X POST http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/start
```

**Response:**
```json
{"status": "ok"}
```

**What happens:**
1. Room status changes from `WAITING` → `PLAYING`
2. Round 1 is automatically created
3. Players are paired up randomly
4. `state_version` increments so polling `/api/rooms/{room_id}/state` now returns `status=PLAYING` and `current_round=1`

### Step 5: Get Current Round

```bash
curl http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/rounds/current
```

**Response:**
```json
{
  "round_number": 1,
  "phase": "NORMAL",
  "status": "waiting_actions"
}
```

### Step 6: Get Opponent Info

```bash
curl "http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/rounds/1/pair?player_id=770e8400-e29b-41d4-a716-446655440001"
```

**Response:**
```json
{
  "opponent_id": "880e8400-e29b-41d4-a716-446655440002",
  "opponent_display_name": "Bob"
}
```

### Step 7: Submit Action

```bash
curl -X POST http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/rounds/1/action \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "770e8400-e29b-41d4-a716-446655440001",
    "choice": "ACCELERATE"
  }'
```

**Response:**
```json
{"status": "ok"}
```

**Choices:**
- `ACCELERATE`: Don't turn, keep going
- `TURN`: Turn away

**What happens:**
1. Action is saved to database (idempotent)
2. `state_version` increments so `/state` shows updated progress (`submitted_actions`)
3. When all players submit, round status changes to `READY_TO_PUBLISH` and `state_version` bumps again

### Step 8: Host Publishes Results

```bash
curl -X POST http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/rounds/1/publish
```

**Response:**
```json
{"status": "ok"}
```

**What happens:**
1. Round status changes from `READY_TO_PUBLISH` → `COMPLETED`
2. `state_version` increments; polling `/state` will show `status=COMPLETED` so clients know to call `/result`

### Step 9: Get Round Result

```bash
curl "http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/rounds/1/result?player_id=770e8400-e29b-41d4-a716-446655440001"
```

**Response:**
```json
{
  "opponent_display_name": "Bob",
  "your_choice": "ACCELERATE",
  "opponent_choice": "TURN",
  "your_payoff": 10,
  "opponent_payoff": -3
}
```

**Payoff Matrix (Chicken Game):**
```
                Player 2
                TURN    ACCELERATE
Player 1  TURN  (3,3)   (-3,10)
          ACC   (10,-3) (-10,-10)
```

### Step 10: Next Round (Repeat 2-10 times)

```bash
curl -X POST http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/rounds/next
```

**Response:**
```json
{
  "status": "ok",
  "round_number": 2
}
```

**Note:** Game supports up to 10 rounds.

### Step 11: End Game

```bash
curl -X POST http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/end
```

**Response:**
```json
{"status": "ok"}
```

### Step 12: Get Final Summary

```bash
curl http://localhost:8000/api/rooms/550e8400-e29b-41d4-a716-446655440000/summary
```

**Response:**
```json
{
  "players": [
    {"display_name": "Alice", "total_payoff": 25},
    {"display_name": "Bob", "total_payoff": 18}
  ],
  "stats": {
    "accelerate_ratio": 0.65,
    "turn_ratio": 0.35
  }
}
```

---

## Core Concepts

### Data Model Hierarchy

```
Room (房間)
 ├─ Players (玩家)
 │   ├─ Host (1 player, is_host=true)
 │   └─ Regular Players (N players, is_host=false)
 │
 └─ Rounds (回合, up to 10)
     ├─ Pairs (配對, N/2 pairs per round)
     │   └─ player1_id, player2_id
     │
     ├─ Actions (動作, N actions per round)
     │   └─ player_id, choice, payoff
     │
     ├─ Messages (訊息, Round 5-6 only)
     │   └─ sender_id, receiver_id, content
     │
     └─ Indicators (指標, assigned after Round 6)
         └─ player_id, symbol
```

### Room States

```
WAITING  ──start_game()──> PLAYING  ──end_game()──> FINISHED
```

- **WAITING**: Players can join
- **PLAYING**: Game in progress, no new players allowed
- **FINISHED**: Game ended, can view summary

### Round States

```
WAITING_ACTIONS ──all_submitted──> READY_TO_PUBLISH ──publish()──> COMPLETED
                                           │
                                      (calculated,
                                   waiting for host)
```

- **WAITING_ACTIONS**: Waiting for players to submit choices
- **READY_TO_PUBLISH**: All players submitted, results calculated, waiting for host to publish
- **COMPLETED**: Results published, players can view

### Round Phases

```
NORMAL (Rounds 1-4, 7-10)
MESSAGE (Rounds 5-6, players can send messages)
INDICATOR (Round 7+, after indicators assigned)
```

### Key Concepts

**1. Idempotency**

All critical operations are idempotent:
- Submitting the same action twice → returns existing action, no error
- Calling `try_finalize_round()` multiple times → only calculates once
- Publishing results twice → no effect if already published

**2. Concurrency Safety**

- Database locks prevent race conditions
- No "last person triggers calculation" logic - anyone can trigger, DB ensures it runs once

**3. Short polling + REST (no WebSocket)**

- **REST API**: All reads/writes
- **Short polling**: `/api/rooms/{room_id}/state?version=x` every 1–1.5s
- **state_version**: increments on any change; if version matches, backend returns `has_update=false`

**4. Host vs Player**

- Host is a special player (`is_host=true`)
- Host controls game flow (start, next round, publish results, end)
- Host does NOT participate in rounds (no actions, no pairing)

---

## Game Flow

### Complete State Machine (ASCII)

```
[1] Host creates room
     │
     v
[2] Players join (room.status = WAITING)
     │
     v
[3] Host starts game (room.status = PLAYING)
     │
     ├──> Round 1 created automatically
     │    room.current_round = 1
     │
     v
[4] For each round (1-10):
     │
     ├──> [4a] Players get paired
     │         GET /rounds/{n}/pair
     │
     ├──> [4b] Players submit actions
     │         POST /rounds/{n}/action
     │         │
     │         ├──> [Progress] state_version bump (X/N submitted shown in /state)
     │         │
     │         └──> [All submitted] Round status → READY_TO_PUBLISH (seen via /state)
     │
     ├──> [4c] Host publishes results
     │         POST /rounds/{n}/publish
     │         │
     │         └──> Round status → COMPLETED (reflected in /state)
     │
     ├──> [4d] Players view results
     │         GET /rounds/{n}/result
     │
     ├──> [Special: Round 5-6]
     │    │
     │    ├──> Players send messages (optional)
     │    │    POST /rounds/{n}/message
     │    │
     │    └──> Players read messages (optional)
     │         GET /rounds/{n}/message
     │
     ├──> [Special: After Round 6]
     │    │
     │    ├──> Host assigns indicators (once)
     │    │    POST /indicators/assign
     │    │
     │    └──> Players view indicators
     │         GET /indicator?player_id=X
     │
     └──> [4e] Host triggers next round
          POST /rounds/next
          │
          └──> Repeat [4a-4e] for rounds 2-10

[5] Host ends game (room.status = FINISHED)
    POST /end
     │
     v
[6] View final summary
    GET /summary
```

---

## REST API Reference

**Base URL:** `http://localhost:8000`

### Room Management

#### `POST /api/rooms`
**Purpose:** Create a new room (host endpoint)

**Request Body:**
```json
{}
```

**Response:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "ABC123",
  "host_player_id": "660e8400-e29b-41d4-a716-446655440000"
}
```

**Notes:**
- Room code is 6 characters, uppercase letters and numbers
- Host player is automatically created

---

#### `GET /api/rooms/{code}`
**Purpose:** Get room status by room code

**Response:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "ABC123",
  "status": "WAITING",
  "current_round": 0,
  "player_count": 2
}
```

**Notes:**
- `player_count` does NOT include the host
- Use this to check if room exists before joining

---

#### `POST /api/rooms/{room_id}/start`
**Purpose:** Start the game (host endpoint)

**Preconditions:**
- Room status must be `WAITING`
- Player count must be ≥ 2 and even

**Response:**
```json
{"status": "ok"}
```

**Side Effects:**
1. Room status → `PLAYING`
2. Round 1 created automatically
3. Players paired randomly for Round 1
4. `state_version` increments so `/state` shows `status=PLAYING` and `current_round=1`

**Errors:**
- `400 Invalid player count`: Not enough players or odd number
- `400 Invalid state transition`: Room already started
- `404 Room not found`: Invalid room_id

---

#### `POST /api/rooms/{room_id}/rounds/next`
**Purpose:** Create next round (host endpoint)

**Preconditions:**
- Room status must be `PLAYING`
- Current round < 10

**Response:**
```json
{
  "status": "ok",
  "round_number": 2
}
```

**Side Effects:**
1. New round created
2. Room.current_round incremented
3. Pairs copied from Round 1 (same opponents for the rest of the game)
4. `state_version` increments so `/state` shows the new round

**Errors:**
- `400 All rounds completed`: Already played 10 rounds
- `400 Invalid player count`: Player count changed (should not happen)

---

#### `POST /api/rooms/{room_id}/end`
**Purpose:** End the game (host endpoint)

**Preconditions:**
- Room status must be `PLAYING`

**Response:**
```json
{"status": "ok"}
```

**Side Effects:**
1. Room status → `FINISHED`
2. `state_version` increments so `/state` shows `status=FINISHED`

---

#### `GET /api/rooms/{room_id}/summary`
**Purpose:** Get game summary (leaderboard + stats)

**Response:**
```json
{
  "players": [
    {"display_name": "Alice", "total_payoff": 25},
    {"display_name": "Bob", "total_payoff": 18}
  ],
  "stats": {
    "accelerate_ratio": 0.65,
    "turn_ratio": 0.35
  }
}
```

**Notes:**
- `players` are sorted by `total_payoff` (descending)
- `accelerate_ratio + turn_ratio = 1.0`
- Can be called anytime (not restricted to FINISHED status)

---

#### `GET /api/rooms/{room_id}/events/since/{last_event_id}`
**Purpose:** Fetch events after a given event ID (for reconnection)

**Response:**
```json
{
  "events": [
    {
      "event_id": 101,
      "event_type": "ROUND_STARTED",
      "data": {"round_number": 2, "phase": "NORMAL"},
      "created_at": "2024-01-15T10:30:00"
    }
  ]
}
```

**Notes:**
- Returns up to 100 events
- Used when WebSocket reconnects to catch up on missed events
- Events are ordered by event_id (ascending)

---

#### `DELETE /api/rooms/{room_id}`
**Purpose:** Delete a room and all related data (host/admin endpoint)

**Response:**
```json
{
  "status": "deleted",
  "room_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Side Effects:**
- Room is permanently deleted
- All related data is cascade deleted:
  - Players
  - Rounds
  - Actions
  - Messages
  - Indicators
  - Event logs

**Notes:**
- This operation is irreversible
- Use with caution
- Automatically happens via background cleanup task (see Background Cleanup section)

**Errors:**
- `404 Room not found`: Invalid room_id

---

#### `GET /api/rooms` (Admin)
**Purpose:** List all rooms (for debugging/admin)

**Query Parameters:**
- `status` (optional): Filter by status (WAITING/PLAYING/FINISHED)
- `limit` (optional): Max results (default: 50, max: 200)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "rooms": [
    {
      "room_id": "550e8400-e29b-41d4-a716-446655440000",
      "code": "ABC123",
      "status": "WAITING",
      "current_round": 0,
      "player_count": 2,
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:35:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Notes:**
- Use for debugging or admin dashboard
- Returns rooms sorted by `updated_at` (descending, newest first)

---

### Background Cleanup

The backend automatically cleans up old rooms to prevent database bloat:

- **Interval**: Every 6 hours
- **FINISHED rooms**: Deleted after 24 hours of inactivity (`updated_at` < 24h ago)
- **WAITING/PLAYING rooms**: Deleted after 2 hours of inactivity (`updated_at` < 2h ago)

This ensures that abandoned rooms don't accumulate indefinitely.

---

### Player Management

#### `POST /api/rooms/{code}/join`
**Purpose:** Join a room (player endpoint)

**Request Body:**
```json
{
  "nickname": "Alice"
}
```

**Response:**
```json
{
  "player_id": "770e8400-e29b-41d4-a716-446655440001",
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "display_name": "Alice"
}
```

**Notes:**
- `nickname`: Player's chosen name (1-50 chars)
- `display_name`: Same string as `nickname`, returned for convenience/UI rendering
- Can only join if room status is `WAITING`

**Errors:**
- `404 Room not found`: Invalid code
- `400 Room not accepting players`: Game already started

---

### Round Management

#### `GET /api/rooms/{room_id}/rounds/current`
**Purpose:** Get current round info

**Response:**
```json
{
  "round_number": 1,
  "phase": "NORMAL",
  "status": "waiting_actions"
}
```

**Notes:**
- `phase`: `NORMAL`, `MESSAGE`, or `INDICATOR`
- `status`: `waiting_actions`, `ready_to_publish`, or `completed`

---

#### `GET /api/rooms/{room_id}/rounds/{round_number}/pair`
**Purpose:** Get opponent info for a specific round

**Query Parameters:**
- `player_id` (required): Player's UUID

**Example:**
```bash
curl "http://localhost:8000/api/rooms/{room_id}/rounds/1/pair?player_id=770e8400-e29b-41d4-a716-446655440001"
```

**Response:**
```json
{
  "opponent_id": "880e8400-e29b-41d4-a716-446655440002",
  "opponent_display_name": "Bob"
}
```

**Errors:**
- `404 Round not found`: Invalid round_number
- `404 Opponent not found`: Player not paired (should not happen)

---

#### `POST /api/rooms/{room_id}/rounds/{round_number}/action`
**Purpose:** Submit player's choice (player endpoint)

**Request Body:**
```json
{
  "player_id": "770e8400-e29b-41d4-a716-446655440001",
  "choice": "ACCELERATE"
}
```

**Choices:**
- `ACCELERATE`: Don't turn
- `TURN`: Turn away

**Response:**
```json
{"status": "ok"}
```

**Side Effects:**
1. Action saved to database
2. `state_version` bumps so `/state` shows updated `submitted_actions`
3. If all submitted:
   - Round status → `READY_TO_PUBLISH`
   - Payoffs calculated automatically
   - `state_version` bumps again (clients see `status=ready_to_publish`)

**Notes:**
- **Idempotent**: Submitting twice with same choice → OK (returns existing action)
- **Non-blocking**: Doesn't wait for others, returns immediately

---

#### `POST /api/rooms/{room_id}/rounds/{round_number}/publish`
**Purpose:** Publish round results (host endpoint)

**Preconditions:**
- Round status must be `READY_TO_PUBLISH`

**Response:**
```json
{"status": "ok"}
```

**Side Effects:**
1. Round status → `COMPLETED`
2. `state_version` bumps so `/state` shows `status=COMPLETED`
3. Players can now fetch results

**Notes:**
- Host controls when results are revealed
- Payoffs are already calculated, just changing visibility

---

#### `POST /api/rooms/{room_id}/rounds/{round_number}/skip`
**Purpose:** Skip a round (host endpoint, emergency use)

**Use Cases:**
- Player disconnected and won't submit
- Testing or administrative override

**Response:**
```json
{"status": "ok"}
```

**Side Effects:**
1. For players who haven't submitted: auto-submit `TURN`
2. Calculate payoffs
3. Immediately publish results (skip READY_TO_PUBLISH state)
4. `state_version` bumps so `/state` shows the completed round

---

#### `GET /api/rooms/{room_id}/rounds/{round_number}/result`
**Purpose:** Get round result for a player

**Query Parameters:**
- `player_id` (required): Player's UUID

**Response:**
```json
{
  "opponent_display_name": "Bob",
  "your_choice": "ACCELERATE",
  "opponent_choice": "TURN",
  "your_payoff": 10,
  "opponent_payoff": -3
}
```

**Preconditions:**
- Round status must be `COMPLETED`

**Errors:**
- `404 Result not available yet`: Round not completed
- `404 Round not found`: Invalid round_number

---

### Messages (Round 5-6 Only)

#### `POST /api/rooms/{room_id}/rounds/{round_number}/message`
**Purpose:** Send message to opponent (Round 5-6 only)

**Request Body:**
```json
{
  "sender_id": "770e8400-e29b-41d4-a716-446655440001",
  "content": "Let's both turn!"
}
```

**Response:**
```json
{"status": "ok"}
```

**Constraints:**
- Only allowed in Round 5 and Round 6
- Each player can send only ONE message per round
- Message length: 1-100 characters
- Message is sent to current opponent (based on pairing)

**Side Effects:**
- `state_version` bumps; receiver sees message via `/state` or GET `/message`

**Errors:**
- `400 Messages are only allowed in Round 5-6`: Wrong round
- `400 You have already sent a message`: Already sent

---

#### `GET /api/rooms/{room_id}/rounds/{round_number}/message`
**Purpose:** Get message from opponent

**Query Parameters:**
- `player_id` (required): Player's UUID (receiver)

**Response:**
```json
{
  "content": "Let's both turn!",
  "from_opponent": true
}
```

**Errors:**
- `404 No message found`: Opponent hasn't sent a message yet

---

### Indicators (After Round 6)

#### `POST /api/rooms/{room_id}/indicators/assign`
**Purpose:** Assign indicators to players (host endpoint, once per game)

**Preconditions:**
- Current round >= 6
- Indicators not already assigned

**Response:**
```json
{"status": "ok"}
```

**Side Effects:**
1. Each player gets a unique emoji indicator (e.g., 🍋, 🍎, 🍊)
2. `state_version` bumps; `/state` shows `indicators_assigned=true` and per-player `indicator_symbol`

**Notes:**
- Can only be done once per game
- Used for reputation tracking in later rounds

**Errors:**
- `400 Indicators can only be assigned after Round 6`: Too early
- `400 Indicators already assigned`: Already done

---

#### `GET /api/rooms/{room_id}/indicator`
**Purpose:** Get player's indicator symbol

**Query Parameters:**
- `player_id` (required): Player's UUID

**Response:**
```json
{
  "symbol": "🍋"
}
```

**Errors:**
- `404 Indicator not found`: Indicators not assigned yet

---

## Short Polling Guide

- **Endpoint:** `GET /api/rooms/{room_id}/state?version=<client_version>&player_id=<optional>`
- **Interval:** 1000–1500ms (classroom-friendly, no WebSocket needed)
- **Version rule:** If `client_version >= server_version` → `{ "has_update": false, "version": <same> }`

**No update response**
```json
{
  "version": 12,
  "has_update": false
}
```

**Update response (example)**
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
      {"player_id": "p1", "display_name": "Alice", "is_host": false}
    ],
    "round": {
      "round_number": 2,
      "phase": "NORMAL",
      "status": "ready_to_publish",
      "submitted_actions": 6,
      "total_players": 6,
      "your_choice": "ACCELERATE",
      "opponent_choice": "TURN",
      "opponent_display_name": "Bob",
      "your_payoff": 10,
      "opponent_payoff": -3
    },
    "indicators_assigned": false,
    "indicator_symbol": null,
    "message": null
  }
}
```

**Client tips**
- Keep `version` in memory; send it with every `/state` call.
- UI can optimistically disable buttons after submit, and rely on `/state` for confirmation/progress.
- Stop polling once room status is `FINISHED`.

## Legacy WebSocket Notes

WebSocket support has been removed in favor of short polling + versioning for maximal stability on unreliable networks. Legacy WebSocket examples were removed from this guide; if you must reference them, check git history prior to this revision.

## Error Handling

### HTTP Status Codes

- **200 OK**: Success
- **400 Bad Request**: Invalid input or precondition failed
- **404 Not Found**: Resource not found (room, player, round, etc.)
- **500 Internal Server Error**: Server error (should not happen)

### Common Errors

#### Room Errors

| Error | Status | Cause |
|-------|--------|-------|
| `Room not found` | 404 | Invalid room code or room_id |
| `Room not accepting players` | 400 | Game already started or finished |
| `Invalid player count` | 400 | Not enough players or odd number |
| `Invalid state transition` | 400 | Trying to start/end game in wrong state |

#### Round Errors

| Error | Status | Cause |
|-------|--------|-------|
| `Round not found` | 404 | Invalid round_number |
| `All rounds completed` | 400 | Trying to create Round 11 |
| `Result not available yet` | 404 | Round not completed |
| `Cannot skip round in status X` | 400 | Can only skip WAITING_ACTIONS or READY_TO_PUBLISH |

#### Message Errors

| Error | Status | Cause |
|-------|--------|-------|
| `Messages are only allowed in Round 5-6` | 400 | Wrong round number |
| `You have already sent a message` | 400 | Already sent one message this round |
| `No message found` | 404 | Opponent hasn't sent message yet |

#### Indicator Errors

| Error | Status | Cause |
|-------|--------|-------|
| `Indicators can only be assigned after Round 6` | 400 | Current round < 6 |
| `Indicators already assigned` | 400 | Already assigned once |
| `Indicator not found` | 404 | Not assigned yet |

### Error Response Format

All errors follow this format:
```json
{
  "detail": "Error message"
}
```

**Example:**
```json
{
  "detail": "Room not found"
}
```

---

## Special Rules

### 1. Round 5-6: Message Phase

**What:** Players can send one message to their opponent in Round 5 and Round 6.

**How:**
1. Round 5 or 6 starts
2. Before or after submitting action, player can send message:
   ```bash
   POST /rounds/{n}/message
   ```
3. Opponent sees message in `/state` (or fetches directly):
   ```bash
   GET /rounds/{n}/message?player_id=X
   ```

**Constraints:**
- One message per player per round
- Max 100 characters
- Message is sent to current opponent (based on this round's pairing)

**UI Suggestion:**
- Show message input field in Round 5-6
- Show opponent's message when received
- Messages should NOT be visible to other players

---

### 2. Round 6+: Indicator Assignment

**What:** After Round 6, host assigns each player a unique emoji indicator (e.g., 🍋, 🍎, 🍊).

**Purpose:** Track reputation across rounds. Players can see which indicator they're facing.

**How:**
1. Host clicks "Assign Indicators" (after Round 6 completed)
   ```bash
   POST /indicators/assign
   ```
2. All players see `indicators_assigned=true` and `indicator_symbol` in `/state`
3. Players can also fetch their indicator directly:
   ```bash
   GET /indicator?player_id=X
   ```

**Notes:**
- Can only be done once per game
- Indicators are random and unique per player
- Used in Rounds 7-10 to identify repeat opponents

**UI Suggestion:**
- Display your indicator prominently
- When viewing opponent info, also show their indicator (if assigned)
- Use this for "reputation tracking" features

---

### 3. Host Controls

**What:** The host has special privileges:

| Action | Endpoint | Description |
|--------|----------|-------------|
| Start game | `POST /start` | Begin Round 1 |
| Next round | `POST /rounds/next` | Create next round |
| Publish results | `POST /rounds/{n}/publish` | Reveal results to players |
| Skip round | `POST /rounds/{n}/skip` | Force-complete round |
| Assign indicators | `POST /indicators/assign` | Assign emoji indicators |
| End game | `POST /end` | Finish game, show summary |

**Important:**
- Host is a player (`is_host=true`) but does NOT participate in rounds
- Host does not get paired, does not submit actions, does not get payoffs
- Host's role is purely administrative

---

### 4. Pairing Algorithm

**How it works:**
- When a round starts, all non-host players are randomly shuffled and paired
- Player 1 ↔ Player 2
- Player 3 ↔ Player 4
- etc.

**Example:**
- Game has 6 players: Alice, Bob, Carol, Dave, Eve, Frank
- Round 1 pairing:
  - Alice ↔ Bob
  - Carol ↔ Dave
  - Eve ↔ Frank
- Round 2 pairing (random shuffle):
  - Alice ↔ Carol
  - Bob ↔ Eve
  - Dave ↔ Frank

**Note:** Pairings are stored in the `Pair` table, so they're deterministic once created.

---

### 5. Payoff Matrix (Game Theory)

The Chicken Game is a classic game theory problem. Here's how payoffs work:

```
                Player 2
                TURN        ACCELERATE
Player 1
  TURN          (+3, +3)    (-3, +10)
  ACCELERATE    (+10, -3)   (-10, -10)
```

**Interpretation:**
- **Both Turn (3, 3):** Both "chicken out" → modest payoff
- **One Accelerates, One Turns (-3, 10):** Accelerator wins big, turner loses
- **Both Accelerate (-10, -10):** Collision → both lose big

**Nash Equilibria:**
- (TURN, ACCELERATE): -3, 10
- (ACCELERATE, TURN): 10, -3

**Strategic Insight:**
- No dominant strategy (best choice depends on opponent's choice)
- Risk vs. reward trade-off
- Communication (Round 5-6 messages) and reputation (indicators) add social dynamics

---

## Appendix: Quick Reference

### Host Workflow

```
1. POST /api/rooms → Get room_id, code
2. (wait for players to join)
3. POST /api/rooms/{room_id}/start
4. For each round:
   a. (wait for players to submit actions)
   b. POST /api/rooms/{room_id}/rounds/{n}/publish
   c. (optional: POST /indicators/assign after Round 6)
   d. POST /api/rooms/{room_id}/rounds/next
5. POST /api/rooms/{room_id}/end
6. GET /api/rooms/{room_id}/summary
```

### Player Workflow

```
1. POST /api/rooms/{code}/join → Get player_id, room_id
2. Poll /api/rooms/{room_id}/state?version=<last_version>&player_id=<you> every 1-1.5s
3. For each round:
   a. When /state shows a new round → show opponent (from /state.round.opponent_display_name or GET /rounds/{n}/pair)
   b. Submit action: POST /api/rooms/{room_id}/rounds/{n}/action
   c. When /state.round.status == \"completed\" → GET /api/rooms/{room_id}/rounds/{n}/result?player_id=X
   d. Round 5-6: send message once (POST /message), read via /state.message or GET /message
   e. Round 7+: indicator available via /state.indicator_symbol or GET /indicator
4. When /state.room.status == \"FINISHED\" → GET /api/rooms/{room_id}/summary
```

### State Signals to Watch (via /state)

| Signal | Meaning | Client action |
|--------|---------|---------------|
| `room.status == \"PLAYING\"` | Game started | Show round UI |
| `round.status == \"waiting_actions\"` | Round open | Enable action buttons |
| `round.status == \"ready_to_publish\"` | All actions submitted | Host: show publish button |
| `round.status == \"completed\"` | Results published | Players: call `/result` |
| `message` not null | Opponent message arrived | Display message |
| `indicators_assigned == true` | Indicators ready | Show indicator_symbol |

---

## Troubleshooting

### Polling looks stale (has_update=false but UI not updating)

- Ensure you send the latest `version` from the previous `/state` call.
- Verify the backend bumped `state_version` (check server logs around the action).
- Include `player_id` so personalized fields (opponent, message, indicator) are returned.

### "Room not accepting players" error

**Cause:** Game already started

**Solution:**
- Check room status first: `GET /api/rooms/{code}`
- If `status != "WAITING"`, cannot join

### "Round not found" error

**Cause:** Trying to access a round that doesn't exist

**Solution:**
- Check current round: `GET /api/rooms/{room_id}/rounds/current`
- Use `round_number` from response

### "Result not available yet" error

**Cause:** Round not completed

**Solution:**
- Poll `/state` until `round.status == "completed"`
- Or check round status: `GET /api/rooms/{room_id}/rounds/current`
- Only fetch result when `status == "completed"`

### Actions not being accepted

**Possible causes:**
1. Wrong round_id or round_number
2. Player already submitted
3. Round already completed

**Solution:**
- Check current round first
- Use `GET /api/rooms/{room_id}/rounds/{n}/result` to see if already submitted

---

## Changelog

- **v1.0.0** (2024-01-15): Initial release
  - REST API complete
  - WebSocket notifications
  - Round 5-6 messaging
  - Indicator system
  - Game summary

---

## Support

**Issues:** Report bugs at https://github.com/your-repo/chicken-game/issues

**Documentation:** This guide + inline code comments

**API Docs:** http://localhost:8000/docs (Swagger UI)

---

**That's it. No more, no less. Go build something.**
