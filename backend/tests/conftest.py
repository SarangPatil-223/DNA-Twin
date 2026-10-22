"""Fixtures: small but real TXT, CSV, PNG and PDF files generated in-process (no binary blobs in git)."""
import os
import struct
import zlib

os.environ.setdefault("DNA_TWIN_SKIP_DOTENV", "1")  # tests must not pick up a developer .env

import pytest


def _png(w=24, h=16) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(
        b"\x00" + bytes(v for x in range(w) for v in ((x * 10) % 256, (y * 15) % 256, ((x ^ y) * 7) % 256))
        for y in range(h)
    )
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _pdf(text="DNA Twin test document. Simulation only.") -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


SAMPLES = {
    "notes.txt": ("text/plain", ("Write it. Mutate it. Get it back. ünïcødé ✓\n" * 40).encode()),
    "table.csv": ("text/csv", ("id,codec,error_rate\n" + "".join(f"{i},church,{i/100}\n" for i in range(120))).encode()),
    "image.png": ("image/png", _png()),
    "doc.pdf": ("application/pdf", _pdf()),
    "empty.bin": ("application/octet-stream", b""),
    "allbytes.bin": ("application/octet-stream", bytes(range(256)) * 3),
}


@pytest.fixture(params=sorted(SAMPLES))
def sample(request):
    name = request.param
    mime, data = SAMPLES[name]
    return name, mime, data


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """Fresh app with its own data dir, SQLite DB and embedded Qdrant."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "extractive")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hashing")
    from app import settings
    from app.db import session
    from app.kb import providers, store
    settings.reset_settings(); session.reset_engine(); store.reset_client(); providers.clear_cache()
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
    store.reset_client(); session.reset_engine(); settings.reset_settings()
