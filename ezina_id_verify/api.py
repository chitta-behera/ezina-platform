"""Optional HTTP wrapper around extract_name() and match_face(). No logic lives here.

    uvicorn ezina_id_verify.api:app

POST /extract-name (multipart: doc_type + file)       -> NameResult
POST /match-face   (multipart: id_image + selfie_image) -> FaceMatchResult
GET  /health

Only the uploaded bytes are passed on; the upload's content type and file name are ignored (the type is detected from the
bytes: JPEG and PNG only). 200 for every normal result (including "not found" / "no match"); 400 for an unsupported
doc_type / file or a malformed request; 502 when AWS Rekognition fails; 401 for a wrong API key.
Install the extras first (from the repo root): pip install -e ".[api]"
"""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ezina_id_verify import (
    FaceMatchResult,
    NameResult,
    RekognitionServiceError,
    UnsupportedDocType,
    UnsupportedFile,
    extract_name,
    match_face,
)
from ezina_id_verify.config import get_settings, load_documents

log = logging.getLogger("ezina_id_verify.api")


async def _read(upload: UploadFile) -> bytes:
    limit = int(get_settings().max_upload_mb * 1024 * 1024)
    return await upload.read(limit + 1)  # one byte over the limit is enough for the size check to fail


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().id_verify_api_key.get_secret_value()
    if not expected:
        return  # local development only: a warning is logged at startup
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


def create_app() -> FastAPI:
    load_documents()  # a malformed documents.yaml stops the app here, with a clear message

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not get_settings().id_verify_api_key.get_secret_value():
            log.warning("ID_VERIFY_API_KEY is empty: the API is open to anyone who can reach it. Local development only.")
        yield

    app = FastAPI(title="Ezina ID verify", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        where = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())  # field names only, never the input
        return JSONResponse(status_code=400, content={"detail": f"Invalid request: {where}"})

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/extract-name", response_model=NameResult, dependencies=[Depends(require_api_key)])
    async def extract_name_endpoint(doc_type: str = Form(...), file: UploadFile = File(...)) -> NameResult:
        try:
            return await extract_name(doc_type, await _read(file))
        except (UnsupportedDocType, UnsupportedFile) as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except RekognitionServiceError as e:
            raise HTTPException(status_code=502, detail=f"AWS Rekognition request failed ({e.code or 'error'})") from None

    @app.post("/match-face", response_model=FaceMatchResult, dependencies=[Depends(require_api_key)])
    async def match_face_endpoint(id_image: UploadFile = File(...), selfie_image: UploadFile = File(...)) -> FaceMatchResult:
        try:
            return await match_face(await _read(id_image), await _read(selfie_image))
        except UnsupportedFile as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except RekognitionServiceError as e:
            raise HTTPException(status_code=502, detail=f"AWS Rekognition request failed ({e.code or 'error'})") from None

    return app


app = create_app()
