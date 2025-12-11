# Chicken Game Backend

FastAPI backend for multiplayer game theory teaching platform.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure database

Copy `.env.example` to `.env` and update the database URL:

```bash
cp .env.example .env
```

Edit `.env`:
```
DATABASE_URL=postgresql://user:password@localhost:5432/chicken_game
```

### 3. Run migrations (optional, using Alembic)

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

Or let the app auto-create tables on startup (development only).

### 4. Start the server

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── main.py              # FastAPI app entry
├── database.py          # DB connection
├── models.py            # SQLAlchemy models
├── schemas.py           # Pydantic schemas
├── game_logic.py        # Core game algorithms
├── api/
│   ├── rooms.py         # Room endpoints
│   ├── players.py       # Player endpoints
│   └── rounds.py        # Round endpoints
├── services/            # Shared services (pairing, state, indicators, etc.)
├── alembic/             # Migrations
└── requirements.txt
```

## API Endpoints

### Room Management
- `GET /api/rooms` - List all rooms (admin/debug)
- `POST /api/rooms` - Create room
- `GET /api/rooms/{code}` - Get room status
- `GET /api/rooms/{room_id}/state?version=x&player_id=y` - Short-poll room state (versioned)
- `POST /api/rooms/{room_id}/start` - Start game
- `POST /api/rooms/{room_id}/rounds/next` - Next round
- `POST /api/rooms/{room_id}/end` - End game
- `GET /api/rooms/{room_id}/summary` - Game summary
- `DELETE /api/rooms/{room_id}` - Delete room (and all related data)

### Players
- `POST /api/rooms/{code}/join` - Join room

### Rounds
- `GET /api/rooms/{room_id}/rounds/current` - Current round
- `GET /api/rooms/{room_id}/rounds/{round_number}/pair` - Get opponent
- `POST /api/rooms/{room_id}/rounds/{round_number}/action` - Submit action
- `GET /api/rooms/{room_id}/rounds/{round_number}/result` - Get result
- `POST /api/rooms/{room_id}/rounds/{round_number}/message` - Send message (Round 5-6)
- `GET /api/rooms/{room_id}/rounds/{round_number}/message` - Get message
- `POST /api/rooms/{room_id}/indicators/assign` - Assign indicators
- `GET /api/rooms/{room_id}/indicator` - Get player indicator

## Game Flow

1. Host creates room → receives room code and host player id
2. Players join with code + nickname
3. Host starts game (when player count is even) — Round 1 created automatically
4. For rounds 1-10:
   - Host triggers next round
   - Players poll `/api/rooms/{room_id}/state` for round status/opponent
   - Players submit choices
   - Server calculates payoffs
   - Host publishes results
   - Players view results
   - Rounds 5-6: optional messages
   - After Round 6: assign indicators
5. Host ends game
6. View final summary

## State Versioning (Short Polling)

- Call `GET /api/rooms/{room_id}/state?version=<current>&player_id=<optional>` every 1–1.5s.
- If `has_update=false`, keep your cached UI.
- When `has_update=true`, update UI with the returned snapshot and store the new `version`.

## Room Cleanup

The backend automatically cleans up old rooms to prevent database bloat:

- **Every 6 hours**: Background task runs to clean up rooms
- **FINISHED rooms**: Deleted after 24 hours of inactivity
- **WAITING/PLAYING rooms**: Deleted after 2 hours of inactivity
- **Manual deletion**: Use `DELETE /api/rooms/{room_id}` to immediately delete a room

All related data (players, rounds, actions, messages, indicators, events) are automatically deleted via cascade.

