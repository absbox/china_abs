from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from .database import get_db
from .auth import get_current_user
from .models import ItemResponse

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/", response_model=list[ItemResponse])
async def list_items(skip: int = 0, limit: int = 20, _: str = Depends(get_current_user)):
    db = get_db()
    cursor = db.items.find().skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return items


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: str, _: str = Depends(get_current_user)):
    db = get_db()
    doc = await db.items.find_one({"_id": ObjectId(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found")
    doc["_id"] = str(doc["_id"])
    return doc
