"""Pre-seed a user into MongoDB.

Usage:
    python seed_user.py <username> <password>

Requires MONGODB_URI and DATABASE_NAME in .env or environment.
"""

import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

from app.auth import hash_password

load_dotenv()


async def seed(username: str, password: str):
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    db = client[os.getenv("DATABASE_NAME", "mydatabase")]

    existing = await db.users.find_one({"username": username})
    if existing:
        print(f"User '{username}' already exists")
        client.close()
        return

    await db.users.insert_one({
        "username": username,
        "password": hash_password(password),
    })
    print(f"User '{username}' created")
    client.close()


if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <username> <password>")
    sys.exit(1)

asyncio.run(seed(sys.argv[1], sys.argv[2]))
