from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from core.database import client
from core.ws import ws_router
from routers import (
    auth, dashboard, escalations, feeds, incidents, notifications,
    predictions, reports, roads, routing, trips, tracking, vehicles,
)
from seed import seed_dashboard, seed_supply_chain, seed_users

# === GIS pipeline routers ===
from ml.pipeline.admin_override import router as admin_override_router
from ml.pipeline.router import router as pipeline_router

logger = logging.getLogger("neris")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="NERIS API")

# Tracking first so /track, /active, /search are not captured by /vehicles/{vehicle_id}
app.include_router(tracking.router, prefix="/api/vehicles")
for module in (auth, dashboard, escalations, feeds, incidents, notifications, predictions, reports, roads, routing, trips, vehicles):
    app.include_router(module.router, prefix="/api")
app.include_router(ws_router, prefix="/api")

# === GIS pipeline endpoints ===
app.include_router(admin_override_router, prefix="/api")
app.include_router(pipeline_router, prefix="/api")


@app.on_event("startup")
async def on_startup():
    await seed_users()
    logger.info("NERIS: users seeded (owner + demo accounts)")
    await seed_dashboard()
    logger.info("NERIS: dashboard demo dataset ready")
    await seed_supply_chain()
    logger.info("NERIS: supply-chain depots, villages, routes, and vehicles ready")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)