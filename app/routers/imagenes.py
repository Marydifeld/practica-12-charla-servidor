import re
import uuid

from ..services import almacen

from ..errors import ApiError
from ..config import settings

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

router = APIRouter(prefix="/imagenes", tags=["imagenes"])

CLAVE_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")

@dataclass
class HealthCheck:
    title: str
    msg: str

@router.get("/checador")
def checar_estatus(req: Request) -> HealthCheck: 
    return {
        "msg": "Hello, API!"
    }

def tipo_de(inicio: bytes) -> tuple[str, str] | None:
    """El tipo real, por los primeros bytes del archivo ("número mágico").

    No por el nombre ni por el Content-Type que manda el cliente: esos los
    escribe quien sube, y un .exe renombrado a foto.jpg sigue siendo un .exe.
    """
    if inicio.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None

class ImagenOut(BaseModel):
    """Lo que devuelve POST /imagenes: la clave para mandarla en el aviso."""
    id: str
    tipo: str
    bytes: int

@router.post("", response_model=ImagenOut, status_code=201)
def subir(archivo: UploadFile) -> ImagenOut:
    """Recibe una imagen (multipart, campo `archivo`), la guarda en el almacén y devuelve su clave.

    Todavía no pertenece a ningún aviso: la clave se manda después en `POST /avisos`.
    """
    # Se lee un byte de más: si llega, el archivo se pasó del límite.
    datos = archivo.file.read(settings.imagen_max_bytes + 1)
    if len(datos) > settings.imagen_max_bytes:
        raise ApiError(
            413,
            "La imagen es demasiado grande",
            "imagen_grande",
            f"El máximo es {settings.imagen_max_bytes // 1024} KB. Redúcela en el teléfono antes de subirla.",
        )
    tipo = tipo_de(datos[:12])
    if tipo is None:
        raise ApiError(415, "El archivo no es una imagen", "no_es_imagen", "Se aceptan JPEG, PNG y WebP.")
    mime, extension = tipo
    clave = f"{uuid.uuid4().hex}.{extension}"
    almacen.guardar(clave, datos, mime)
    return ImagenOut(id=clave, tipo=mime, bytes=len(datos))


@router.get("/{clave}")
def descargar(clave: str, request: Request) -> Response:
    if not CLAVE_RE.match(clave):
        raise ApiError(404, "No existe esa imagen")
    
    objeto = almacen.abrir(clave)
    if objeto is None:
        raise ApiError(404, "No existe esa imagen")
    
    etag = objeto["ETag"]
    # Una clave nunca cambia de contenido: puede guardarse para siempre en el teléfono.
    cache = {"ETag": etag, "Cache-Control": "private, max-age=31536000, immutable"}
    if request.headers.get("If-None-Match") == etag:
        objeto["Body"].close()
        return Response(status_code=304, headers=cache)
    return StreamingResponse(
        objeto["Body"].iter_chunks(64 * 1024),
        media_type=objeto["ContentType"],
        headers={**cache, "Content-Length": str(objeto["ContentLength"])},
    )
