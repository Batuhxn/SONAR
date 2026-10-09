from __future__ import annotations

import asyncio
import copy
import logging
import os
import secrets
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sonar_a0.transport import FetchError
from .bom import MAX_CELL, import_components, read_table, validate
from .procurement import export_csv, procurement
from .suppliers import SupplierService

logger = logging.getLogger("sonar")
STATIC = Path(__file__).parent / "static"


@dataclass
class Settings:
    max_upload: int = 8 * 1024 * 1024
    session_ttl: int = 7200
    max_sessions: int = 100
    secure_cookie: bool = False
    allowed_hosts: tuple = ("localhost", "127.0.0.1", "testserver")
    origins: tuple = ("http://localhost:8000", "http://127.0.0.1:8000")

    @classmethod
    def from_env(cls):
        return cls(max_upload=int(os.getenv("SONAR_MAX_UPLOAD_MB", "8")) * 1024 * 1024,
                   session_ttl=int(os.getenv("SONAR_SESSION_TTL_SECONDS", "7200")),
                   max_sessions=int(os.getenv("SONAR_MAX_SESSIONS", "100")),
                   secure_cookie=os.getenv("SONAR_SECURE_COOKIE", "false").lower() == "true",
                   allowed_hosts=tuple(os.getenv("SONAR_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")),
                   origins=tuple(os.getenv("SONAR_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")))


@dataclass
class Session:
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    touched: float = field(default_factory=time.monotonic)
    boms: dict = field(default_factory=dict)
    previews: dict = field(default_factory=dict)
    jobs: dict = field(default_factory=dict)
    rates: deque = field(default_factory=deque)
    lock: threading.RLock = field(default_factory=threading.RLock)


class Store:
    def __init__(self, settings):
        self.settings = settings
        self.sessions = {}
        self.lock = threading.RLock()

    def get(self, token: str | None):
        with self.lock:
            now = time.monotonic()
            for key in list(self.sessions):
                if now - self.sessions[key].touched > self.settings.session_ttl:
                    del self.sessions[key]
            session = self.sessions.get(token)
            if session:
                session.touched = now
            return session

    def create(self):
        with self.lock:
            self.get(None)
            if len(self.sessions) >= self.settings.max_sessions:
                raise HTTPException(503, "Session capacity reached; try later")
            token = secrets.token_urlsafe(32)
            session = Session()
            self.sessions[token] = session
            return token, session


class BodyLimit:
    """Bound actual request bytes, including chunked requests, before JSON parsing."""
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH", "PUT", "DELETE"}:
            return await self.app(scope, receive, send)
        maximum = self.maximum if scope["path"] == "/api/import/preview" else 256 * 1024
        data = bytearray()
        try:
            async with asyncio.timeout(30):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    data.extend(message.get("body", b""))
                    if len(data) > maximum:
                        return await JSONResponse({"detail": "Request exceeds size limit"}, status_code=413)(scope, receive, send)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse({"detail": "Upload timed out"}, status_code=408)(scope, receive, send)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ImportInput(Input):
    preview_id: str
    mapping: dict[str, int]
    name: str = Field(min_length=1, max_length=150)


class BoardsInput(Input):
    boards: int = Field(ge=1, le=100000)


class ComponentInput(Input):
    name: str | None = Field(default=None, max_length=MAX_CELL)
    mpn: str | None = Field(default=None, max_length=MAX_CELL)
    quantity: str | None = Field(default=None, max_length=MAX_CELL)
    references: str | None = Field(default=None, max_length=MAX_CELL)
    dnp: bool | None = None
    selected: bool | None = None


class SearchInput(Input):
    bom_id: str
    component_ids: list[str] = Field(min_length=1, max_length=10)
    supplier: Literal["ozdisan", "direnc"]
    url: str | None = Field(default=None, max_length=2000)


class SelectionInput(Input):
    component_ids: list[str] = Field(min_length=1, max_length=5000)
    selected: bool


class ChoiceInput(Input):
    supplier: Literal["ozdisan", "direnc"]
    offer: int = Field(ge=0)
    tier: int = Field(ge=-1)
    acknowledge_uncertain: bool = False


def create_app(settings: Settings | None = None, supplier_service=None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.max_upload <= 0 or settings.session_ttl <= 0 or settings.max_sessions <= 0:
        raise ValueError("Upload, session TTL and capacity must be positive")
    store = Store(settings)
    service = supplier_service or SupplierService()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sonar-suppliers")
    pending = threading.BoundedSemaphore(20)
    ip_rates = {}
    rate_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="SONAR A1", version="0.2.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.store = store
    app.state.suppliers = service
    app.add_middleware(BodyLimit, maximum=settings.max_upload)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    @app.middleware("http")
    async def protections(request, call_next):
        if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
            origin = request.headers.get("origin")
            if origin and origin not in settings.origins:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
            token = request.cookies.get("sonar_session")
            if request.url.path != "/api/session" and token and store.get(token):
                response.set_cookie("sonar_session", token, httponly=True, secure=settings.secure_cookie,
                                    samesite="strict", max_age=settings.session_ttl)
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(FetchError)
    async def fetch_invalid(request, error):
        return JSONResponse({"detail": str(error), "status": str(error.status)}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request, error):
        # Do not log request contents, BoMs, supplier URL queries or session cookies.
        logger.error("Request failed: %s", type(error).__name__)
        return JSONResponse({"detail": "Request failed; retry or contact the administrator"}, status_code=500)

    def session_for(request: Request):
        session = store.get(request.cookies.get("sonar_session"))
        if not session:
            raise HTTPException(401, "Session expired; reload to start a new session")
        if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(request.headers.get("x-sonar-csrf", ""), session.csrf):
            raise HTTPException(403, "Missing or invalid CSRF token")
        return session

    def find_bom(session, bom_id):
        if bom_id not in session.boms:
            raise HTTPException(404, "BoM not found in this session")
        return session.boms[bom_id]

    def find_component(bom, component_id):
        for c in bom["components"]:
            if c.id == component_id:
                return c
        raise HTTPException(404, "Component not found")

    def serialize_bom(b):
        return {**{k: v for k, v in b.items() if k != "components"}, "components": [c.to_dict() for c in b["components"]]}

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": "0.2.0", "storage": "temporary session memory"}

    @app.get("/api/session")
    def bootstrap(request: Request, response: Response):
        token = request.cookies.get("sonar_session")
        session = store.get(token)
        if not session:
            token, session = store.create()
        response.set_cookie("sonar_session", token, httponly=True, secure=settings.secure_cookie, samesite="strict", max_age=settings.session_ttl)
        with session.lock:
            return {"csrf": session.csrf, "ttl_seconds": settings.session_ttl, "max_upload": settings.max_upload,
                    "boms": [serialize_bom(b) for b in session.boms.values()], "jobs": copy.deepcopy(list(session.jobs.values()))}

    @app.post("/api/import/preview")
    async def preview(request: Request, session=Depends(session_for)):
        filename = unquote(request.headers.get("x-filename", ""))
        if not filename or len(filename) > 200:
            raise HTTPException(400, "Provide a filename of at most 200 characters")
        data = await request.body()
        table = await run_in_threadpool(read_table, data, filename, request.query_params.get("sheet"))
        preview_id = uuid.uuid4().hex
        with session.lock:
            session.previews[preview_id] = {"table": table, "filename": filename}
            while len(session.previews) > 2:
                del session.previews[next(iter(session.previews))]
        return {"preview_id": preview_id, "filename": filename, **{k: v for k, v in table.items() if k not in {"rows", "preamble"}},
                "sample": table["rows"][:5], "row_count": len(table["rows"]), "preamble": table["preamble"]}

    @app.post("/api/boms", status_code=201)
    def import_bom(body: ImportInput, session=Depends(session_for)):
        with session.lock:
            if not body.name.strip():
                raise HTTPException(422, "BoM name cannot be blank")
            preview = session.previews.get(body.preview_id)
            if not preview:
                raise HTTPException(404, "Import preview expired; upload again")
            if len(session.boms) >= 10:
                raise HTTPException(400, "Maximum 10 BoMs per session; remove one first")
            components = import_components(preview["table"], body.mapping)
            bom_id = uuid.uuid4().hex
            bom = {"id": bom_id, "name": body.name.strip(), "filename": preview["filename"], "boards": 1,
                   "sheet": preview["table"]["sheet"], "preamble": preview["table"]["preamble"], "components": components}
            session.boms[bom_id] = bom
            del session.previews[body.preview_id]
            logger.info("BoM imported: %d rows", len(components))
            return serialize_bom(bom)

    @app.patch("/api/boms/{bom_id}")
    def boards(bom_id: str, body: BoardsInput, session=Depends(session_for)):
        with session.lock:
            bom = find_bom(session, bom_id)
            bom["boards"] = body.boards
            validate(bom["components"], body.boards)
            return serialize_bom(bom)

    @app.delete("/api/boms/{bom_id}", status_code=204)
    def delete_bom(bom_id: str, session=Depends(session_for)):
        with session.lock:
            find_bom(session, bom_id)
            del session.boms[bom_id]

    @app.patch("/api/boms/{bom_id}/components/{component_id}")
    def edit(bom_id: str, component_id: str, body: ComponentInput, session=Depends(session_for)):
        with session.lock:
            bom = find_bom(session, bom_id)
            c = find_component(bom, component_id)
            updates = body.model_dump(exclude_unset=True)
            if any(v is None for v in updates.values()):
                raise HTTPException(422, "Edits cannot set fields to null")
            changed = any(getattr(c, k) != v for k, v in updates.items() if k != "selected")
            for key, value in updates.items():
                setattr(c, key, value.strip().upper() if key == "mpn" else value)
            if changed:
                c.revision += 1
                c.results = {}
                c.choice = None
            if c.dnp:
                c.selected = False
            validate(bom["components"], bom["boards"])
            return serialize_bom(bom)

    @app.post("/api/boms/{bom_id}/selection")
    def select_components(bom_id: str, body: SelectionInput, session=Depends(session_for)):
        with session.lock:
            bom = find_bom(session, bom_id)
            components = [find_component(bom, cid) for cid in body.component_ids]
            for c in components:
                c.selected = body.selected if c.dnp is False else False
            return serialize_bom(bom)

    def execute_job(session, job_id, bom_id, snapshots, supplier, url):
        try:
            with session.lock:
                session.jobs[job_id]["state"] = "running"
            for cid, mpn, revision in snapshots:
                try:
                    result = service.retrieve(supplier, mpn, url)
                except Exception as error:
                    logger.warning("Supplier retrieval failed: %s", type(error).__name__)
                    result = {"supplier": supplier, "status": "network_error", "offers": [],
                              "message": "Retrieval failed; no price or stock inferred", "evidence": []}
                with session.lock:
                    bom = session.boms.get(bom_id)
                    c = next((c for c in bom["components"] if c.id == cid), None) if bom else None
                    if c and c.revision == revision:
                        c.results[supplier] = result
                        if c.choice and c.choice["supplier"] == supplier:
                            c.choice = None
                    session.jobs[job_id]["completed"] += 1
                    session.jobs[job_id]["results"].append({"component_id": cid, "status": result["status"], "applied": bool(c and c.revision == revision)})
                if result["status"] in {"blocked", "rate_limited", "robots_unavailable", "network_error"} or any(e.get("http_status") in {401, 403, 429} for e in result.get("evidence", [])):
                    with session.lock:
                        session.jobs[job_id]["message"] = "Remaining requests stopped after supplier access / network failure"
                    break
            with session.lock:
                session.jobs[job_id]["state"] = "done"
        finally:
            pending.release()

    @app.post("/api/supplier-jobs", status_code=202)
    def search(body: SearchInput, request: Request, session=Depends(session_for)):
        with session.lock:
            bom = find_bom(session, body.bom_id)
            if len(set(body.component_ids)) != len(body.component_ids):
                raise HTTPException(422, "Duplicate component IDs")
            if body.url and len(body.component_ids) != 1:
                raise HTTPException(422, "Manual URL retrieval requires exactly one component")
            if body.url:
                service.validate_url(body.supplier, body.url)
            components = [find_component(bom, cid) for cid in body.component_ids]
            if any(c.dnp is not False or c.required is None or not c.selected for c in components):
                raise HTTPException(422, "Choose populated, selected components with valid quantities")
            if not body.url and any(not c.mpn for c in components):
                raise HTTPException(422, "Automatic search requires an MPN; use a manual supplier URL")
            if any(len(c.mpn) > 150 for c in components):
                raise HTTPException(422, "Supplier query MPN exceeds 150 characters")
            now = time.monotonic()
            while session.rates and now - session.rates[0] > 60:
                session.rates.popleft()
            ip = request.client.host if request.client else "local"
            with rate_lock:
                for key in list(ip_rates):
                    if not ip_rates[key] or now - ip_rates[key][-1] > 60:
                        del ip_rates[key]
                rate = ip_rates.setdefault(ip, deque())
                while rate and now - rate[0] > 60:
                    rate.popleft()
                if len(session.rates) + len(components) > 10 or len(rate) + len(components) > 20:
                    raise HTTPException(429, "Supplier request limit reached; wait one minute", headers={"Retry-After": "60"})
                if not pending.acquire(blocking=False):
                    raise HTTPException(429, "Supplier queue full; retry later")
                session.rates.extend([now] * len(components))
                rate.extend([now] * len(components))
            job_id = uuid.uuid4().hex
            session.jobs[job_id] = {"id": job_id, "state": "queued", "completed": 0, "total": len(components), "results": [], "message": ""}
            for old in list(session.jobs):
                if len(session.jobs) > 30 and session.jobs[old]["state"] == "done":
                    del session.jobs[old]
            executor.submit(execute_job, session, job_id, body.bom_id, [(c.id, c.mpn, c.revision) for c in components], body.supplier, body.url)
            return copy.deepcopy(session.jobs[job_id])

    @app.get("/api/supplier-jobs/{job_id}")
    def job(job_id: str, session=Depends(session_for)):
        with session.lock:
            if job_id not in session.jobs:
                raise HTTPException(404, "Job not found in this session")
            return copy.deepcopy(session.jobs[job_id])

    @app.put("/api/boms/{bom_id}/components/{component_id}/choice")
    def choice(bom_id: str, component_id: str, body: ChoiceInput, session=Depends(session_for)):
        with session.lock:
            c = find_component(find_bom(session, bom_id), component_id)
            offers = c.results.get(body.supplier, {}).get("offers", [])
            if body.offer >= len(offers):
                raise HTTPException(422, "Supplier offer not found")
            offer = offers[body.offer]
            if body.tier >= len(offer.get("prices", [])) or (offer.get("prices") and body.tier < 0):
                raise HTTPException(422, "Choose a reported price tier")
            if offer.get("match") != "exact_mpn" and not body.acknowledge_uncertain:
                raise HTTPException(422, "Acknowledge the uncertain product match before selecting it")
            if c.dnp is not False or c.required is None or not c.selected:
                raise HTTPException(422, "Component is excluded or has invalid quantity / DNP")
            c.choice = body.model_dump(exclude={"acknowledge_uncertain"})
            return c.to_dict()

    @app.delete("/api/boms/{bom_id}/components/{component_id}/choice", status_code=204)
    def clear_choice(bom_id: str, component_id: str, session=Depends(session_for)):
        with session.lock:
            find_component(find_bom(session, bom_id), component_id).choice = None

    @app.get("/api/procurement")
    def purchasing(session=Depends(session_for)):
        with session.lock:
            return procurement(session.boms)

    @app.get("/api/procurement.csv")
    def export(session=Depends(session_for)):
        with session.lock:
            report = procurement(session.boms)
            content = export_csv(report["lines"])
        return Response(content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="sonar-procurement.csv"'})

    @app.get("/api/boms/{bom_id}/source.csv")
    def export_source(bom_id: str, session=Depends(session_for)):
        with session.lock:
            bom = find_bom(session, bom_id)
            import csv
            import io
            from .procurement import csv_safe
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            for row in bom["preamble"]:
                writer.writerow([csv_safe(c) for c in row])
            writer.writerow(list(bom["components"][0].raw))
            for c in bom["components"]:
                writer.writerow([csv_safe(v) for v in c.raw.values()])
        return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="sonar-source.csv"'})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
