import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.core import imaging
from app.core.benchmark import SweepConfig, run_sweep, summarize, to_csv
from app.core.binary import read_header
from app.core.channel import ChannelParams
from app.core.pipeline import run_all


@pytest.fixture(scope="module")
def png():
    img = Image.new("RGB", (96, 64), (230, 220, 200))
    d = ImageDraw.Draw(img)
    for i in range(0, 96, 8):
        d.line([(i, 0), (96 - i, 64)], fill=(i * 2, 90, 200 - i), width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.parametrize("mode", imaging.MODES)
@pytest.mark.parametrize("max_side", [256, 40])
def test_image_modes_roundtrip_exact(png, mode, max_side):
    payload, info = imaging.prepare(png, mode, max_side)
    ref = imaging.reference_pixels(png, info)
    r = run_all(payload, "i.png", "image/png", "church", ChannelParams(), {})
    got, _ = imaging.reconstruct(r["retrieval"].recovered_file, info)
    q = imaging.quality(ref, got)
    assert r["retrieval"].exact_match and q["psnr_infinite"] and q["ssim"] == 1.0


def test_compressed_image_is_all_or_nothing_raw_pixels_degrade(png):
    """The core image finding: under the same channel, PNG bytes become undecodable while raw
    pixels stay viewable, and concealment raises SSIM."""
    ch = ChannelParams.from_error_rate(0.015, copies=2, seed=4)
    pf, info_f = imaging.prepare(png, "file")
    rf = run_all(pf, "i.png", "image/png", "yinyang", ch, {})
    got_f, _ = imaging.reconstruct(rf["retrieval"].recovered_file, info_f)
    assert not rf["retrieval"].exact_match and got_f is None

    pp, info_p = imaging.prepare(png, "pixels")
    ref = imaging.reference_pixels(png, info_p)
    rp = run_all(pp, "i.png", "image/png", "yinyang", ch, {})
    got_p, _ = imaging.reconstruct(rp["retrieval"].recovered_file, info_p)
    q = imaging.quality(ref, got_p)
    assert q["decodable"] and 0 < q["ssim"] < 1
    mask = imaging.lost_pixel_mask(info_p, rp["retrieval"].lost_ranges, read_header(rp["encode"].container)[1])
    assert mask.any()
    fixed = imaging.conceal(got_p, mask)
    assert imaging.quality(ref, fixed)["ssim"] > q["ssim"]
    assert np.array_equal(fixed[~mask], got_p[~mask])  # known pixels untouched


def test_psnr_ssim_basics():
    a = np.zeros((16, 16), dtype=np.uint8)
    assert imaging.psnr(a, a) == float("inf")
    b = a.copy()
    b[0, 0] = 255
    assert 20 < imaging.psnr(a, b) < 40


def test_benchmark_rows_summary_and_tolerance():
    data = b"benchmark data " * 40
    cfg = SweepConfig(codecs=["church", "goldman"], error_rates=[0.0, 0.01, 0.2], rs_levels=[0.0, 30.0], seeds=[1, 2], copies=4)
    res = run_sweep(data, "b.txt", "text/plain", cfg)
    assert len(res["rows"]) == 3 * 3 * 2  # (church, church+rs30, goldman) x rates x seeds
    summ = {(r["variant"], r["error_rate"]): r for r in res["summary"]}
    for v in ("church", "church+rs30", "goldman"):
        assert summ[(v, 0.0)]["exact_match_mean"] == 1.0
        assert summ[(v, 0.2)]["exact_match_mean"] == 0.0  # 20% error at 4 copies must fail
        assert summ[(v, 0.0)]["error_tolerance"] in (0.0, 0.01)
    csv_text = to_csv(res["summary"])
    assert csv_text.startswith("# Simulation Result") and "error_tolerance" in csv_text
    assert summarize([]) == []
