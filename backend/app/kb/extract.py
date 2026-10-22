"""Text extraction from RECOVERED bytes. Tolerant by design: damaged data yields what it can."""
from __future__ import annotations

import io
import re
import zipfile

TEXT_MIMES = ("text/", "application/json", "application/csv")


def extract_pages(data: bytes | None, mime: str, filename: str = "") -> list[tuple[int | None, str]]:
    if not data:
        return []
    name = filename.lower()
    if mime.startswith(TEXT_MIMES) or name.endswith((".txt", ".csv", ".md", ".json")):
        return [(None, data.decode("utf-8", errors="replace"))]
    if mime == "application/pdf" or name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return [(i + 1, (p.extract_text() or "")) for i, p in enumerate(reader.pages)]
        except Exception:
            return []
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            text = re.sub(r"</w:p>", "\n", xml)
            return [(None, re.sub(r"<[^>]+>", "", text))]
        except Exception:
            return []
    if mime.startswith("image/"):
        try:
            import numpy as np
            from PIL import Image

            from app.core.imaging import ocr

            img = Image.open(io.BytesIO(data)).convert("RGB")
            return [(None, ocr(np.asarray(img)))]
        except Exception:
            return []
    return []


def clean(text: str) -> str:
    text = text.replace("�", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def chunk_text(pages: list[tuple[int | None, str]], size: int = 500, overlap: int = 50) -> list[dict]:
    """Chunks of ~`size` tokens with `overlap`. Tokens are approximated as whitespace words."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks: list[dict] = []
    for page, text in pages:
        words = clean(text).split()
        step = size - overlap
        for start in range(0, max(len(words), 1), step):
            piece = words[start : start + size]
            if not piece:
                break
            chunks.append({"page": page, "text": " ".join(piece), "token_count": len(piece)})
            if start + size >= len(words):
                break
    for i, c in enumerate(chunks):
        c["chunk_idx"] = i
    return chunks
