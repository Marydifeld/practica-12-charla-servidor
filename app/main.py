"""Charla: el servidor de UNA sala de chat, la tuya. Corre en tu computadora."""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app import invitacion, sala, solicitudes
from .routers import imagenes

from .services import almacen

@asynccontextmanager
async def lifespan(_: FastAPI):
    almacen.preparar()    

    yield

app = FastAPI(title="Conversacion", lifespan=lifespan)
app.include_router(sala.router)
app.include_router(solicitudes.router)
app.include_router(invitacion.router)
app.include_router(imagenes.router)

@app.get("/salud")
def salud():
    return {"ok": True}