from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EXPECTED_CASES = {
    "ref-3ph-001b",
    "pfa-es-001",
    "double-bus",
    "multi-bus",
    "mixed-resolved-pending",
    "loads-and-compensation",
}


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        (Path("C:/Windows/Fonts/segoeuib.ttf"), Path("C:/Windows/Fonts/arialbd.ttf"))
        if bold
        else (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/arial.ttf"))
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _fit(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGB")
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    panel = Image.new("RGB", (width, height), "white")
    panel.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return panel


def _comparison(case: dict[str, object], root: Path) -> bytes:
    qt_path = root / str(case["qt_png"])
    svg_path = root / str(case["svg_png"])
    for path in (qt_path, svg_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing review image for {case['name']}: {path}")

    panel_width = 1120
    panel_height = 760
    margin = 24
    header_height = 76
    gap = 20
    canvas_width = margin * 2 + panel_width * 2 + gap
    canvas_height = margin * 2 + header_height + panel_height
    canvas = Image.new("RGB", (canvas_width, canvas_height), "#F1F5F9")
    draw = ImageDraw.Draw(canvas)

    case_name = str(case["name"])
    draw.text((margin, margin), case_name, fill="#0F172A", font=_font(30, bold=True))
    draw.text(
        (margin, margin + 42),
        f"{case.get('buses', 0)} buses/nodes  |  {case.get('equipment', 0)} equipment  |  "
        f"{case.get('terminals', 0)} terminals  |  {case.get('connections', 0)} conductors  |  "
        f"{case.get('unresolved', 0)} unresolved  |  {case.get('partial_data', 0)} partial",
        fill="#334155",
        font=_font(16),
    )

    left_x = margin
    right_x = margin + panel_width + gap
    top = margin + header_height
    draw.rounded_rectangle(
        (left_x, top, left_x + panel_width, top + 32), radius=6, fill="#E2E8F0"
    )
    draw.rounded_rectangle(
        (right_x, top, right_x + panel_width, top + 32), radius=6, fill="#E2E8F0"
    )
    draw.text((left_x + 12, top + 7), "QT / QGraphicsView", fill="#0F172A", font=_font(16, bold=True))
    draw.text((right_x + 12, top + 7), "SVG export (rasterized for comparison)", fill="#0F172A", font=_font(16, bold=True))

    panel_top = top + 40
    qt = _fit(Image.open(qt_path), panel_width, panel_height - 48)
    svg = _fit(Image.open(svg_path), panel_width, panel_height - 48)
    canvas.paste(qt, (left_x, panel_top))
    canvas.paste(svg, (right_x, panel_top))
    draw.rectangle((left_x, panel_top, left_x + panel_width - 1, panel_top + panel_height - 49), outline="#94A3B8", width=2)
    draw.rectangle((right_x, panel_top, right_x + panel_width - 1, panel_top + panel_height - 49), outline="#94A3B8", width=2)

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()



def _verify_release(release_dir: Path, expected_commit: str) -> None:
    build_info_path = release_dir / "BUILD-INFO.json"
    checksum_path = release_dir / "SHA256SUMS.txt"
    sbom_path = release_dir / "SBOM.cdx.json"
    zip_path = release_dir / "PFA-Windows-x64.zip"
    for path in (build_info_path, checksum_path, sbom_path, zip_path):
        if not path.is_file():
            raise FileNotFoundError(f"Release sidecar is missing: {path}")

    build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    if build_info.get("git_commit") != expected_commit:
        raise RuntimeError(
            f"BUILD-INFO commit {build_info.get('git_commit')} does not match "
            f"gallery commit {expected_commit}."
        )
    if build_info.get("architecture") != "x64":
        raise RuntimeError(f"Unexpected release architecture: {build_info.get('architecture')}")

    checksums: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise RuntimeError(f"Malformed SHA256SUMS row: {line}")
        expected, filename = parts[0].lower(), parts[1].lstrip("*").strip()
        target = release_dir / filename
        if not target.is_file():
            raise FileNotFoundError(f"Checksum target is missing: {target}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch for release file: {filename}")
        checksums[filename] = actual
        print(f"PFA_RELEASE_SHA256|{filename}|{actual}", flush=True)
    if "PFA-Windows-x64.zip" not in checksums:
        raise RuntimeError("SHA256SUMS.txt does not cover PFA-Windows-x64.zip.")

    with zipfile.ZipFile(zip_path) as archive:
        embedded_info = next(
            (name for name in archive.namelist() if Path(name).name == "BUILD-INFO.json"),
            None,
        )
        if embedded_info is None:
            raise RuntimeError("Portable package does not embed BUILD-INFO.json.")
        embedded = json.loads(archive.read(embedded_info).decode("utf-8-sig"))
        if embedded.get("git_commit") != expected_commit:
            raise RuntimeError("Embedded BUILD-INFO commit does not match the accepted commit.")
        if embedded.get("git_commit") != build_info.get("git_commit"):
            raise RuntimeError("Embedded and sidecar BUILD-INFO files disagree.")

    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    components = sbom.get("components", [])
    print(
        "PFA_RELEASE_INFO|"
        + json.dumps(
            {
                "version": build_info.get("version"),
                "architecture": build_info.get("architecture"),
                "python": build_info.get("python"),
                "git_commit": build_info.get("git_commit"),
                "distribution": build_info.get("distribution"),
                "zip_sha256": checksums["PFA-Windows-x64.zip"],
                "zip_bytes": zip_path.stat().st_size,
                "sbom_components": len(components),
                "sbom_serial": sbom.get("serialNumber"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit compact Qt/SVG comparison previews into the GitHub Actions log."
    )
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    manifest_path = root / "gallery-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Gallery manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise TypeError("Gallery manifest does not contain a cases array.")
    names = {str(case.get("name", "")) for case in cases}
    if len(cases) != 6 or names != EXPECTED_CASES:
        raise RuntimeError(
            f"Expected exactly six acceptance cases {sorted(EXPECTED_CASES)}, got {sorted(names)}."
        )

    print(f"PFA_REVIEW_MANIFEST|commit={manifest.get('commit')}|cases={len(cases)}")
    for case in cases:
        if case.get("validation_errors"):
            raise RuntimeError(f"{case['name']}: validation errors are not allowed.")
        if not case.get("svg") or not case.get("qt_png") or not case.get("svg_png"):
            raise RuntimeError(f"{case['name']}: incomplete SVG/Qt image pair.")
        payload = _comparison(case, root)
        digest = hashlib.sha256(payload).hexdigest()
        encoded = base64.b64encode(payload).decode("ascii")
        name = str(case["name"])
        chunk_size = 6000
        total_chunks = (len(encoded) + chunk_size - 1) // chunk_size
        print(f"PFA_REVIEW_IMAGE_BEGIN|{name}|{digest}|{total_chunks}", flush=True)
        for chunk_index in range(total_chunks):
            start = chunk_index * chunk_size
            print(
                f"PFA_REVIEW_IMAGE_CHUNK|{name}|{chunk_index}|"
                f"{encoded[start:start + chunk_size]}",
                flush=True,
            )
        print(f"PFA_REVIEW_IMAGE_END|{name}", flush=True)
        print(
            f"PFA_REVIEW_CASE|{name}|buses={case.get('buses', 0)}"
            f"|equipment={case.get('equipment', 0)}|terminals={case.get('terminals', 0)}"
            f"|connections={case.get('connections', 0)}"
            f"|unresolved={case.get('unresolved', 0)}|partial={case.get('partial_data', 0)}"
            f"|warnings={json.dumps(case.get('warnings', []), ensure_ascii=False)}",
            flush=True,
        )
    print("PFA_REVIEW_PAIRS_COMPLETE|6", flush=True)
    _verify_release(Path("dist/release"), str(manifest.get("commit", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
