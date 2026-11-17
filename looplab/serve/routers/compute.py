"""Launch routing to operator-configured LoopLab instances behind SSH loopback tunnels."""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

from looplab.core.pathsafe import run_child_name_defect
from looplab.core.config import DEVELOPER_BACKENDS
from looplab.serve.principal import require_owner

_ENV = "LOOPLAB_COMPUTE_TARGETS"
_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
_TOKEN_ENV = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RESPONSE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Target:
    alias: str
    port: int
    token_env: str = ""

    @property
    def key(self) -> str:
        return f"{self.alias}:{self.port}"

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def configured_targets(raw: str) -> dict[str, Target]:
    """Parse a server-owned alias-to-tunnel mapping. Browser requests can only name these keys."""
    try:
        profiles = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"{_ENV} must be a JSON object") from exc
    if not isinstance(profiles, dict) or len(profiles) > 32:
        raise ValueError(f"{_ENV} must be an object with up to 32 SSH aliases")
    targets = {}
    ports = set()
    for alias, config in profiles.items():
        if not _ALIAS.fullmatch(alias) or alias == "local":
            raise ValueError(f"{_ENV} has an invalid SSH alias")
        if isinstance(config, int):
            config = {"port": config}
        if not isinstance(config, dict) or config.keys() - {"port", "token_env"}:
            raise ValueError(f"{_ENV} entries need a port and may specify token_env")
        port, token_env = config.get("port"), config.get("token_env", "")
        if type(port) is not int or not 1 <= port <= 65535 or port in ports:
            raise ValueError(f"{_ENV} entries need distinct ports between 1 and 65535")
        if not isinstance(token_env, str) or (token_env and not _TOKEN_ENV.fullmatch(token_env)):
            raise ValueError(f"{_ENV} has an invalid token_env name")
        target = Target(alias, port, token_env)
        targets[target.key] = target
        ports.add(port)
    return targets


async def forward(target: Target, method: str, path: str, **kwargs) -> JSONResponse:
    headers = kwargs.pop("headers", {})
    if target.token_env:
        token = os.environ.get(target.token_env)
        if not token:
            raise HTTPException(409, f"UI token for {target.alias} is missing on this server")
        headers["X-LoopLab-Token"] = token
    try:
        timeout = 10.0 if method == "POST" else 5.0
        async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
            async with client.stream(method, target.origin + path, headers=headers, **kwargs) as reply:
                if reply.status_code == 401:
                    raise HTTPException(403, f"UI credentials for {target.alias} were rejected")
                if not 200 <= reply.status_code < 300 and not 400 <= reply.status_code <= 599:
                    raise HTTPException(502, f"{target.alias} returned an unexpected HTTP response")
                content = bytearray()
                async for chunk in reply.aiter_bytes():
                    if len(content) + len(chunk) > _RESPONSE_BYTES:
                        raise HTTPException(502, f"{target.alias} returned too much data")
                    content.extend(chunk)
                return JSONResponse(json.loads(content), status_code=reply.status_code,
                                    headers={"Cache-Control": "no-store"})
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise HTTPException(409, f"Could not connect to {target.alias}. Check its SSH tunnel.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"{target.alias} did not return a usable response. "
                                 "Check its SSH tunnel and LoopLab UI.") from exc


def build_router(srv) -> APIRouter:
    router = APIRouter()
    targets = configured_targets(os.environ.get(_ENV, "{}"))

    def resolve(request: Request, target: str) -> Target:
        require_owner(request, "use SSH compute targets")
        if target not in targets:
            raise HTTPException(409, "This SSH compute target is no longer configured")
        return targets[target]

    @router.get("/api/compute")
    def compute_targets(request: Request):
        """List the SSH compute targets configured for this installation."""
        require_owner(request, "list SSH compute targets")
        return {"targets": [{"id": target.key, "label": target.alias} for target in targets.values()]}

    @router.get("/api/compute/{target}/gpu")
    async def compute_gpu(request: Request, target: str):
        """Test a configured SSH tunnel and read GPU telemetry from its LoopLab instance."""
        return await forward(resolve(request, target), "GET", "/api/gpu")

    @router.get("/api/compute/connections")
    def connections(request: Request):
        """List saved LLM profiles and check CLI availability on this LoopLab host."""
        require_owner(request, "inspect model connections")
        settings = srv.settings.resolve_settings(srv.settings.load_ui_settings())
        return {
            "profiles": sorted(settings.llm_profiles),
            "developer_backend": settings.developer_backend,
            "opencode_model": settings.opencode_model,
            "agents": {
                name: shutil.which("cn" if name == "continue" else name) is not None
                for name in DEVELOPER_BACKENDS if name != "default"
            },
        }

    @router.get("/api/compute/{target}/connections")
    async def remote_connections(request: Request, target: str):
        """List saved profiles and check CLI availability on a configured SSH host."""
        return await forward(resolve(request, target), "GET", "/api/compute/connections")

    @router.post("/api/compute/{target}/start/{phase}")
    async def compute_start(request: Request, target: str, phase: str):
        """Validate or submit a run on the selected SSH compute target."""
        destination = resolve(request, target)
        if phase not in ("preflight", "submit"):
            raise HTTPException(404, "Unknown launch phase")
        path = "/api/start/preflight" if phase == "preflight" else "/api/start"
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, "Start body must be valid JSON") from exc
        return await forward(destination, "POST", path, json=body)

    @router.get("/api/compute/{target}/start/{run_id}/status")
    async def compute_start_status(request: Request, target: str, run_id: str):
        """Read the exact startup receipt from the selected SSH compute target."""
        destination = resolve(request, target)
        if run_child_name_defect(run_id, strict=True):
            raise HTTPException(400, "run_id must be a plain name")
        key = request.headers.get("Idempotency-Key")
        if not key:
            raise HTTPException(400, "Idempotency-Key header is required")
        return await forward(destination, "GET", f"/api/start/{quote(run_id, safe='')}/status",
                             headers={"Idempotency-Key": key})

    return router
