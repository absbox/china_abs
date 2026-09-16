from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from .database import connect_db, close_db
from .routes import router as items_router
from .auth_routes import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="Digester Service",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

app.include_router(auth_router)
app.include_router(items_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
