"""Integration: upload -> encode -> validate -> simulate -> retrieve -> compare -> benchmark ->
recommend -> report -> knowledge base, through the HTTP API."""
import pytest

from tests.conftest import SAMPLES, _pdf, _png

TEXT = ("DNA Twin stores files in simulated DNA. The Church code maps one bit to each base. "
        "Goldman used a rotating base-3 code with fourfold overlapping fragments. "
        "Reed-Solomon parity lets the decoder rebuild lost oligos. ") * 12


def up(api, name, data):
    r = api.post("/files/upload", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_security(api):
    assert api.post("/files/upload", files={"file": ("x.exe", b"MZ....")}).status_code == 415
    assert api.post("/files/upload", files={"file": ("fake.pdf", b"not a pdf")}).status_code == 415
    assert api.post("/files/upload", files={"file": ("e.txt", b"")}).status_code == 400
    assert api.post("/files/upload", files={"file": ("bad.txt", b"\xff\xfe\x00bad")}).status_code == 415
    big = b"a" * (3 * 1024 * 1024)
    assert api.post("/files/upload", files={"file": ("big.txt", big)}).status_code == 413
    f = up(api, "../../etc/notes.txt", b"hello")
    assert f["filename"] == "notes.txt"


def test_future_work_codec_refused(api):
    f = up(api, "a.txt", b"hello world")
    r = api.post("/encoding/run", json={"file_id": f["id"], "codec": "hedges"})
    assert r.status_code == 400 and "future work" in r.json()["detail"]
    assert api.post("/encoding/run", json={"file_id": f["id"], "codec": "nope"}).status_code == 400


@pytest.mark.parametrize("codec,extra", [("church", {"rs_parity_pct": 25}), ("goldman", {}), ("fountain", {"overhead": 0.4}),
                                         ("yinyang", {"rs_parity_pct": 25}), ("raw2bit", {"rs_parity_pct": 25})])
def test_step_by_step_flow_text(api, codec, extra):
    f = up(api, "notes.txt", TEXT.encode())
    e = api.post("/encoding/run", json={"file_id": f["id"], "codec": codec, **extra}).json()
    assert e["label"] == "Simulation Result" and e["stats"]["n_oligos"] > 0 and e["sample_oligos"]
    v = api.post("/validation/run", json={"encoding_run_id": e["id"]}).json()
    assert v["status"] in ("VALID", "WARNING", "INVALID") and v["n_sequences"] == e["stats"]["n_oligos"]
    fasta = api.get(f"/encoding/{e['id']}/fasta")
    assert fasta.status_code == 200 and fasta.text.startswith(">oligo_0")
    s = api.post("/simulation/run", json={"encoding_run_id": e["id"], "sub": 0.004, "ins": 0.001, "dele": 0.003,
                                          "copies": 6, "seed": 3}).json()
    assert s["totals"]["reads"] > 0
    r = api.post("/retrieval/run", json={"simulation_run_id": s["id"]}).json()
    assert r["exact_match"], r["metrics"]
    assert r["sha256_got"] == r["sha256_expected"] == f["sha256"]
    assert r["llm_readiness"]["readiness"] == 100.0
    d = api.get(f"/retrieval/{r['id']}/download")
    assert d.status_code == 200 and d.content == TEXT.encode()


def test_damaged_recovery_is_flagged(api):
    f = up(api, "notes.txt", TEXT.encode())
    r = api.post("/pipeline/run", json={"file_id": f["id"], "codec": "church", "sub": 0.05, "ins": 0.02, "dele": 0.03,
                                        "copies": 1, "seed": 1}).json()["retrieval"]
    assert not r["exact_match"]
    assert r["llm_readiness"]["readiness"] < 100
    assert "DAMAGED" in api.get(f"/retrieval/{r['id']}/download").headers["content-disposition"]


def test_image_flow_with_concealment(api):
    f = up(api, "img.png", _png(48, 32))
    assert f["kind"] == "image"
    out = api.post("/pipeline/run", json={"file_id": f["id"], "codec": "yinyang", "image_mode": "pixels",
                                          "sub": 0.01, "ins": 0.002, "dele": 0.008, "copies": 2, "seed": 2}).json()
    im = out["retrieval"]["image_metrics"]
    assert im["mode"] == "pixels" and im["raw"]["decodable"]
    for which in ("ref", "img", "diff"):
        assert api.get(f"/retrieval/{out['retrieval']['id']}/image/{which}").status_code == 200
    ok = api.post("/pipeline/run", json={"file_id": f["id"], "codec": "church", "image_mode": "file", "copies": 1}).json()
    assert ok["retrieval"]["exact_match"] and ok["retrieval"]["image_metrics"]["raw"]["ssim"] == 1.0


def test_pdf_and_csv_roundtrip(api):
    for name, data in (("doc.pdf", _pdf("Twin PDF text survives")), ("table.csv", SAMPLES["table.csv"][1])):
        f = up(api, name, data)
        r = api.post("/pipeline/run", json={"file_id": f["id"], "codec": "goldman", "copies": 3, "sub": 0.002, "seed": 4}).json()
        assert r["retrieval"]["exact_match"]


def test_benchmark_recommend_report_compare(api):
    f = up(api, "notes.txt", TEXT.encode())
    b = api.post("/benchmark/run", json={"file_id": f["id"], "codecs": ["church", "yinyang", "goldman"],
                                         "error_rates": [0.0, 0.01, 0.04], "rs_levels": [0, 30], "seeds": 2, "copies": 5}).json()
    assert b["n_runs"] == 5 * 3 * 2
    assert any("llm_readiness_mean" in r for r in b["summary"])
    csv = api.get(f"/benchmark/{b['id']}/csv")
    assert csv.status_code == 200 and csv.text.startswith("# Simulation Result")
    for profile in ("archival", "llm_rag", "cost_density", "balanced"):
        rec = api.post("/recommendation/run", json={"file_id": f["id"], "profile": profile}).json()
        assert rec["ranking"] and rec["headline"] and rec["ranking"][0]["reasons"]
        assert all("value" in x for x in rec["ranking"][0]["reasons"])
    assert api.post("/recommendation/run", json={"file_id": f["id"], "profile": "nope"}).status_code == 400
    ds = api.get("/recommendation/dataset.csv")
    assert "label_exact" in ds.text
    cmp_ = api.get(f"/comparison/{f['id']}").json()
    assert cmp_["benchmark"]["summary"]
    pdf = api.post("/reports/generate", json={"file_id": f["id"]})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_knowledge_base_only_from_recovered_data(api):
    f = up(api, "notes.txt", TEXT.encode())
    assert api.post("/kb/ingest", json={"retrieval_run_id": 999}).status_code == 404
    r = api.post("/pipeline/run", json={"file_id": f["id"], "codec": "church", "rs_parity_pct": 25, "copies": 4,
                                        "sub": 0.003, "seed": 5}).json()["retrieval"]
    d = api.post("/kb/ingest", json={"retrieval_run_id": r["id"]}).json()
    assert d["chunks"] >= 1 and d["recovered_exact"] and d["codec"] == "church"
    q = api.post("/kb/query", json={"question": "Which code uses a rotating base-3 scheme?", "doc_ids": [d["doc_id"]]}).json()
    assert q["citations"] and q["citations"][0]["codec"] == "church" and q["citations"][0]["recovered_exact"]
    assert "Goldman" in q["answer"] and "[S" in q["answer"]
    assert q["label"] == "Simulation Result"


def test_lazy_retrieval_and_cross_codec_compare(api):
    f = up(api, "notes.txt", TEXT.encode())
    q1 = api.post("/kb/query", json={"question": "What rebuilds lost oligos?", "file_id": f["id"], "codec": "goldman"}).json()
    assert q1["lazy_retrieval"]["cached"] is False and q1["citations"][0]["codec"] == "goldman"
    q2 = api.post("/kb/query", json={"question": "What rebuilds lost oligos?", "file_id": f["id"], "codec": "goldman"}).json()
    assert q2["lazy_retrieval"]["cached"] is True
    c = api.post("/kb/compare", json={"file_id": f["id"], "question": "What maps one bit to each base?",
                                      "codecs": ["church", "fountain"]}).json()
    assert [x["codec"] for x in c["results"]] == ["church", "fountain"]
    assert all(x["citations"] for x in c["results"])
    docs = api.get("/kb/documents").json()
    assert {d["codec"] for d in docs} >= {"goldman", "church", "fountain"}


def test_settings_and_research(api):
    s = api.get("/settings").json()
    assert s["llm_provider"].startswith("extractive") and s["embedding"].startswith("hashing")
    r = api.get("/research").json()
    assert any(c["name"].startswith("Church") for c in r["codecs"])
    assert api.get("/codecs").json()


def test_reindex_when_embedding_provider_changes(api, monkeypatch):
    from app.kb import providers
    f = up(api, "notes.txt", TEXT.encode())
    r = api.post("/pipeline/run", json={"file_id": f["id"], "codec": "goldman", "copies": 3, "seed": 2}).json()["retrieval"]
    d1 = api.post("/kb/ingest", json={"retrieval_run_id": r["id"]}).json()

    class Small(providers.EmbeddingProvider):
        name, dim = "hashing-test-256", 256
        def embed(self, texts):
            import numpy as np
            v = np.ones((len(texts), 256), dtype="float32")
            return v / np.linalg.norm(v, axis=1, keepdims=True)
    import app.kb.rag as rag
    monkeypatch.setattr(rag, "get_embedder", lambda s=None: Small())
    d2 = api.post("/kb/ingest", json={"retrieval_run_id": r["id"]}).json()
    assert d2["embedding"] == "hashing-test-256" and d1["embedding"] != d2["embedding"]
    q = api.post("/kb/query", json={"question": "overlap", "doc_ids": [d2["doc_id"]]}).json()
    assert q["citations"], "re-indexed document must be searchable under the new embedder"
