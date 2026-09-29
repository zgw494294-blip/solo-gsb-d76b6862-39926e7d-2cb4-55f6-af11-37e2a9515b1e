"""FastAPI service for offline e-paper refresh planning."""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .planner import ValidationError, plan_payload

app = FastAPI(
    title="E-Paper Refresh Planner API",
    version="1.0.0",
    description="Plans minimum-cost full/partial refresh sequences for "
    "1..20 target frames on a 0/1 grid of up to 4x4 cells.",
)


@app.get("/")
async def root():
    return {"service": "epaper-refresh-planner", "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/plan")
async def plan(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=422, content={"detail": "request body must be valid JSON"}
        )
    try:
        result = plan_payload(payload)
    except ValidationError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    return result
