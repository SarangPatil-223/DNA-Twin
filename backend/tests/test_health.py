def test_health(api):
    r = api.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["core_ok"] and body["label"] == "Simulation Result"
    assert api.get("/api/health").status_code == 200
