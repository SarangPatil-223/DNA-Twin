"""PDF reports (reportlab + matplotlib). Every simulated number is labelled "Simulation Result"."""
from __future__ import annotations

import datetime as dt
import io
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,  # noqa: E402
                                Table, TableStyle)

from app.core import SIMULATION_LABEL  # noqa: E402

INK = colors.HexColor("#14171C")
SOFT = colors.HexColor("#5B6170")
LINE = colors.HexColor("#E3DFD3")
ACCENT = colors.HexColor("#3B5BDB")
PALETTE = ["#3B5BDB", "#E8590C", "#2B8A3E", "#AE3EC9", "#C92A2A", "#0B7285", "#5C940D", "#862E9C", "#D9480F"]

RESEARCH_PATH = pathlib.Path(__file__).resolve().parent / "research" / "research.json"


def research() -> dict:
    return json.loads(RESEARCH_PATH.read_text())


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK)
    return {
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=22, leading=26, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13.5, leading=17, spaceBefore=12, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3),
        "b": base,
        "small": ParagraphStyle("s", parent=base, fontSize=8, leading=10.5, textColor=SOFT),
        "cell": ParagraphStyle("c", parent=base, fontSize=7.8, leading=10),
        "badge": ParagraphStyle("badge", parent=base, fontName="Helvetica-Bold", fontSize=8, textColor=colors.white,
                                backColor=ACCENT, borderPadding=(2, 5, 2, 5)),
    }


def _badge(st) -> Table:
    t = Table([[Paragraph("Simulation Result", ParagraphStyle("bd", parent=st["b"], fontName="Helvetica-Bold",
                                                              fontSize=8, leading=10, textColor=colors.white))]],
              colWidths=[32 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT), ("TOPPADDING", (0, 0), (-1, -1), 2),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _table(rows: list[list], widths: list[float], st) -> Table:
    data = [[Paragraph(str(c), st["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1EEE5")),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _chart(summary: list[dict], key: str, ylabel: str) -> Image:
    fig, ax = plt.subplots(figsize=(7.2, 3.1), dpi=160)
    variants = sorted({r["variant"] for r in summary})
    for i, v in enumerate(variants):
        rows = sorted((r for r in summary if r["variant"] == v), key=lambda r: r["error_rate"])
        xs = [100 * r["error_rate"] for r in rows]
        ys = [r[f"{key}_mean"] if r[f"{key}_mean"] is not None else float("nan") for r in rows]
        ax.plot(xs, ys, marker="o", ms=3.5, lw=1.6, color=PALETTE[i % len(PALETTE)], label=v)
    ax.set_xlabel("channel error rate (%)", fontsize=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.25)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=6.5, ncol=4, frameon=False, loc="lower left")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=180 * mm, height=77 * mm)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SOFT)
    canvas.drawString(18 * mm, 10 * mm, f"DNA Twin · {SIMULATION_LABEL} — software simulation, no wet-lab validation")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"page {doc.page}")
    canvas.restoreState()


def _research_section(st) -> list:
    r = research()
    out = [Paragraph("Published codecs and how they compare with Church 2012", st["h2"]),
           Paragraph(r["headline"], st["b"]), Spacer(1, 4)]
    rows = [["Codec", "bits/nt", "ECC", "Indels", "Reported result", "vs Church", "In DNA Twin"]]
    for c in r["codecs"]:
        rows.append([f"<a href='{c['source']['url']}' color='#3B5BDB'>{c['name']}</a>", c["bits_per_nt"], c["ecc"],
                     c["handles_indels"], c["reported_result"], c["vs_church"], f"{c['in_platform']} ({c['platform_status']})"])
    out.append(_table(rows, [26 * mm, 15 * mm, 25 * mm, 13 * mm, 40 * mm, 34 * mm, 25 * mm], st))
    b = r["benchmark_2026"]
    out += [Paragraph(f"<a href='{b['url']}' color='#3B5BDB'>{b['title']}</a>", st["h3"])]
    out += [Paragraph("• " + f, st["b"]) for f in b["findings"]]
    out += [Paragraph("Related platforms (overlap with DNA Twin)", st["h3"])]
    out += [Paragraph(f"• <b>{p['name']}</b>: {p['what']} <a href='{p['url']}' color='#3B5BDB'>link</a>", st["b"])
            for p in r["related_platforms"]]
    return out


def benchmark_pdf(file_row: dict, summary: list[dict], rec: dict | None, retrievals: list[dict]) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"DNA Twin report – {file_row['filename']}")
    s: list = [_badge(st), Spacer(1, 6),
               Paragraph(f"DNA Twin report: {file_row['filename']}", st["h1"]),
               Paragraph(f"{file_row['mime']} · {file_row['size']:,} bytes · SHA-256 {file_row['sha256'][:16]}… · "
                         f"generated {dt.datetime.now().strftime('%d %b %Y %H:%M')}", st["small"]), Spacer(1, 8)]
    if rec and rec.get("ranking"):
        s += [Paragraph("Recommendation", st["h2"]), Paragraph(rec["headline"], st["b"]),
              Paragraph(rec.get("caveat", ""), st["small"])]
        rows = [["#", "Variant", "Score", "Strengths", "Weaknesses"]]
        for i, e in enumerate(rec["ranking"], 1):
            rows.append([i, e["variant"], e["score"], ", ".join(e["strengths"]) or "–", ", ".join(e["weaknesses"]) or "–"])
        s += [Spacer(1, 4), _table(rows, [8 * mm, 34 * mm, 16 * mm, 61 * mm, 61 * mm], st)]
    if summary:
        s += [Paragraph("Benchmark: byte-exact recovery vs error rate", st["h2"]),
              Paragraph("Share of seeds recovering the file byte-exactly (SHA-256 match). "
                        "Channel: substitutions, insertions and deletions in the configured mix, with dropout and "
                        "multiple read copies; reads clustered without ground truth.", st["small"]),
              _chart(summary, "exact_match", "exact recovery (share of seeds)"),
              _chart(summary, "file_byte_accuracy", "file byte accuracy")]
        variants = sorted({r["variant"] for r in summary})
        rows = [["Variant", "Density (bits/nt)", "GC", "Max homopolymer", "Constraints", "Error tolerance", "LLM readiness"]]
        for v in variants:
            rs = [r for r in summary if r["variant"] == v]
            llm = [r.get("llm_readiness_mean") for r in rs if r.get("llm_readiness_mean") is not None]
            tol = rs[0]["error_tolerance"]
            rows.append([v, f"{rs[0]['density_bits_per_nt']:.3f}", f"{rs[0]['gc']:.2f}", rs[0]["max_homopolymer"],
                         rs[0]["constraint_status"], "none" if tol is None else f"{tol:.1%}",
                         f"{sum(llm) / len(llm):.0f}/100" if llm else "–"])
        s += [KeepTogether([Paragraph("Per-variant properties", st["h3"]),
                            _table(rows, [34 * mm, 22 * mm, 14 * mm, 24 * mm, 24 * mm, 26 * mm, 26 * mm], st)])]
    if retrievals:
        s += [Paragraph("Individual retrieval runs", st["h2"])]
        rows = [["Run", "Codec", "Channel", "Exact", "Byte acc.", "Unrecoverable units", "LLM readiness"]]
        for r in retrievals[:25]:
            ch = r.get("channel", {})
            llm = (r.get("llm_readiness") or {}).get("readiness")
            rows.append([r["id"], r["codec"], f"sub {ch.get('sub', 0):.2%} ins {ch.get('ins', 0):.2%} del {ch.get('dele', 0):.2%} ×{ch.get('copies', 1)}",
                         "yes" if r["exact_match"] else "no", f"{(r['metrics'].get('file_byte_accuracy') or 0):.2%}",
                         r["metrics"].get("units_unrecoverable"), "–" if llm is None else f"{llm:.0f}"])
        s.append(_table(rows, [12 * mm, 22 * mm, 56 * mm, 13 * mm, 18 * mm, 30 * mm, 26 * mm], st))
    s += [PageBreak()] + _research_section(st)
    s += [Paragraph("Limitations", st["h2"])] + [Paragraph("• " + x, st["b"]) for x in LIMITATIONS]
    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


LIMITATIONS = [
    "All results come from a software channel model. No DNA was synthesized or sequenced.",
    "The channel uses independent per-base errors, first-order decay and fixed or Poisson copy numbers. "
    "It does not model synthesis bias per sequence, PCR amplification bias, or position-dependent sequencing error.",
    "Goldman, DNA Fountain and Yin-Yang are simplified re-implementations; their numbers describe these "
    "implementations, not the published systems.",
    "HEDGES, DNA-Aeon and DP-DNA are listed for comparison only and are not implemented.",
    "LLM readiness is measured on text extracted from the recovered bytes; answer quality also depends on the LLM.",
]


def research_pdf(extra_findings: list[str] | None = None, bench_tables: list[tuple[str, list[dict]]] | None = None,
                 tables: list[tuple[str, list[list], list[float]]] | None = None, intro: str | None = None) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="DNA Twin – research notes")
    s: list = [Paragraph("DNA Twin research notes", st["h1"]),
               Paragraph(f"Updated {research()['updated']}", st["small"]), Spacer(1, 6)]
    if intro:
        s.append(Paragraph(intro, st["b"]))
    if extra_findings:
        s += [Paragraph("Measured on this platform", st["h2"]), _badge(st), Spacer(1, 4)]
    for f in extra_findings or []:
        s.append(Paragraph("• " + f, st["b"]))
    for title, rows, widths in tables or []:
        s += [Paragraph(title, st["h3"]), _table(rows, [w * mm for w in widths], st)]
    s += _research_section(st)
    for title, summary in bench_tables or []:
        s += [PageBreak(), _badge(st), Spacer(1, 4), Paragraph(title, st["h2"]),
              _chart(summary, "exact_match", "exact recovery (share of seeds)"),
              _chart(summary, "file_byte_accuracy", "file byte accuracy")]
    s += [Paragraph("Limitations", st["h2"])] + [Paragraph("• " + x, st["b"]) for x in LIMITATIONS]
    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
