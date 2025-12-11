from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from database import Base, engine, get_db
from api import rooms, players, rounds
from utils.cleanup import cleanup_old_rooms, cleanup_inactive_rooms

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: 在應用啟動時建立資料庫表
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # 啟動背景清理任務（使用 asyncio）
    import asyncio
    from functools import partial

    async def run_cleanup_task():
        """定期清理任務"""
        while True:
            try:
                # 每 6 小時執行一次
                await asyncio.sleep(6 * 3600)

                logger.info("Running scheduled cleanup tasks...")

                # 取得資料庫 session
                db = next(get_db())
                try:
                    # 1. 清理 24 小時前的已結束房間
                    finished_count = cleanup_old_rooms(db, hours=24, status_filter="FINISHED")

                    # 2. 清理 2 小時閒置的等待中/進行中房間
                    inactive_count = cleanup_inactive_rooms(db, hours=2)

                    logger.info(f"Cleanup completed: {finished_count} finished rooms, {inactive_count} inactive rooms")

                finally:
                    db.close()

            except Exception as e:
                logger.error(f"Cleanup task failed: {e}", exc_info=True)

    # 啟動背景任務
    cleanup_task = asyncio.create_task(run_cleanup_task())

    yield

    # Shutdown: 取消背景任務
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        logger.info("Cleanup task cancelled")
    logger.info("Application shutdown")


app = FastAPI(
    title="Chicken Game API",
    description="Backend API for multiplayer game theory teaching platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(rooms.router)
app.include_router(players.router)
app.include_router(rounds.router)


@app.get("/")
def root():
    return {"message": "Chicken Game API", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=False  # 關閉 access log，減少輪詢請求的日誌輸出
    )
