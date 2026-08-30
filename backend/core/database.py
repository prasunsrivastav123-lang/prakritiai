import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

client = AsyncIOMotorClient(
    MONGO_URL,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
)
db = client[DB_NAME]