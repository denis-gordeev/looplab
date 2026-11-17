import httpx
import pytest
from fastapi.testclient import TestClient

from looplab.serve.routers import compute
from looplab.serve.server import make_app


def test_compute_routes_forward_only_to_configured_tunnel(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPLAB_UI_TOKEN", "local-owner")
    monkeypatch.setenv("WOWSEARCH_UI_TOKEN", "remote-owner")
    monkeypatch.setenv("LOOPLAB_COMPUTE_TARGETS",
                       '{"wowsearch":{"port":18765,"token_env":"WOWSEARCH_UI_TOKEN"}}')
    headers = {"X-LoopLab-Token": "local-owner"}
    seen = []

    def remote(request):
        seen.append((request.method, request.url.path))
        assert request.url.host == "127.0.0.1" and request.url.port == 18765
        assert request.headers["X-LoopLab-Token"] == "remote-owner"
        if request.url.path.endswith("/status"):
            assert request.headers["Idempotency-Key"] == "same-startup"
        return httpx.Response(200, json={"ok": True, "path": request.url.path})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(compute.httpx, "AsyncClient",
                        lambda **kw: async_client(transport=httpx.MockTransport(remote), **kw))
    client = TestClient(make_app(tmp_path))
    assert client.get("/api/compute").status_code == 401
    assert client.get("/api/compute", headers=headers).json() == {
        "targets": [{"id": "wowsearch:18765", "label": "wowsearch"}],
    }
    path = "/api/compute/wowsearch%3A18765"
    assert client.get("/api/compute/arbitrary:1111/gpu", headers=headers).status_code == 409
    assert client.post(path + "/start/other", json={}, headers=headers).status_code == 404
    assert client.get(path + "/gpu", headers=headers).json()["path"] == "/api/gpu"
    for phase in ("preflight", "submit"):
        assert client.post(path + f"/start/{phase}", json={}, headers=headers).status_code == 200
    response = client.get(path + "/start/test-run/status",
                          headers={**headers, "Idempotency-Key": "same-startup"})
    assert response.json()["path"] == "/api/start/test-run/status"
    assert seen == [("GET", "/api/gpu"), ("POST", "/api/start/preflight"),
                    ("POST", "/api/start"), ("GET", "/api/start/test-run/status")]


@pytest.mark.parametrize("profiles", [
    '[]', '{"localhost":{"port":true}}', '{"a":18765,"b":18765}', '{"bad/alias":18765}',
])
def test_invalid_compute_targets_fail_at_startup(profiles):
    with pytest.raises(ValueError, match="LOOPLAB_COMPUTE_TARGETS"):
        compute.configured_targets(profiles)


def test_model_connections_follow_the_compute_host(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOPLAB_COMPUTE_TARGETS", '{"wowsearch":18765}')
    monkeypatch.setattr(compute.shutil, "which", lambda name: "/bin/codex" if name == "codex" else None)

    async def forward(target, method, path):
        assert (target.alias, method, path) == ("wowsearch", "GET", "/api/compute/connections")
        return {"profiles": ["remote-model"]}

    monkeypatch.setattr(compute, "forward", forward)
    client = TestClient(make_app(tmp_path))
    assert client.put("/api/settings", json={"settings": {"llm_profiles": {
        "local-model": {"model": "test-model", "base_url": "http://127.0.0.1:11434/v1"},
    }}}).status_code == 200
    local = client.get("/api/compute/connections").json()
    assert local["profiles"] == ["local-model"]
    assert local["agents"]["codex"] is True and local["agents"]["opencode"] is False
    remote = client.get("/api/compute/wowsearch%3A18765/connections")
    assert remote.json() == {"profiles": ["remote-model"]}
