from __future__ import annotations

import base64
import html
from io import BytesIO
from typing import Any

import qrcode
import qrcode.image.svg
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer

STYLES: dict[str, tuple[str, str]] = {
    "classic": ("#111111", "#FFFFFF"),
    "ocean": ("#0B3D91", "#FFFFFF"),
    "emerald": ("#086B4C", "#FFFFFF"),
    "violet": ("#5B2C83", "#FFFFFF"),
    "ruby": ("#8B1E2D", "#FFFFFF"),
}


def _qr(payload: str, *, box_size: int = 16) -> qrcode.QRCode:
    code = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=box_size,
        border=4,
    )
    code.add_data(payload)
    code.make(fit=True)
    return code


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def build_png(payload: str, style: str = "classic") -> bytes:
    fill, back = STYLES.get(style, STYLES["classic"])
    image = _qr(payload).make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(radius_ratio=0.7),
        color_mask=SolidFillColorMask(back_color=_rgb(back), front_color=_rgb(fill)),
    ).convert("RGB")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def build_svg(payload: str) -> bytes:
    image = _qr(payload, box_size=10).make_image(image_factory=qrcode.image.svg.SvgPathImage)
    output = BytesIO()
    image.save(output)
    return output.getvalue()


def _hex(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value.upper()
        except ValueError:
            pass
    return fallback


def _mix(first: tuple[int, int, int], second: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * ratio) for a, b in zip(first, second, strict=True))


def _design(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = value or {}
    size = max(256, min(int(raw.get("size", 768)), 2048))
    return {
        "fg": _hex(raw.get("fg"), "#111318"),
        "bg": _hex(raw.get("bg"), "#FFFFFF"),
        "gradient": bool(raw.get("gradient", False)),
        "gradient_to": _hex(raw.get("gradient_to"), "#635BFF"),
        "shape": raw.get("shape") if raw.get("shape") in {"square", "rounded", "dots"} else "rounded",
        "frame": bool(raw.get("frame", False)),
        "frame_text": str(raw.get("frame_text", "SCAN ME"))[:32],
        "size": size,
        "margin": max(2, min(int(raw.get("margin", 4)), 10)),
        "logo": str(raw.get("logo", ""))[:1_500_000],
    }


def build_custom_png(payload: str, design: dict[str, Any] | None = None) -> bytes:
    spec = _design(design)
    code = _qr(payload, box_size=1)
    matrix = code.get_matrix()
    modules = len(matrix)
    qr_size = spec["size"]
    footer = max(76, qr_size // 9) if spec["frame"] else 0
    canvas = Image.new("RGB", (qr_size, qr_size + footer), _rgb(spec["bg"]))
    draw = ImageDraw.Draw(canvas)
    margin_modules = spec["margin"]
    module = max(1, qr_size // (modules + margin_modules * 2))
    rendered = module * modules
    origin = (qr_size - rendered) // 2
    first = _rgb(spec["fg"])
    second = _rgb(spec["gradient_to"])
    radius = max(1, round(module * 0.36))

    for row_index, row in enumerate(matrix):
        color = _mix(first, second, row_index / max(1, modules - 1)) if spec["gradient"] else first
        for column_index, active in enumerate(row):
            if not active:
                continue
            x0 = origin + column_index * module
            y0 = origin + row_index * module
            x1 = x0 + module
            y1 = y0 + module
            if spec["shape"] == "dots":
                inset = max(0, module // 12)
                draw.ellipse((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=color)
            elif spec["shape"] == "rounded":
                draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=color)
            else:
                draw.rectangle((x0, y0, x1, y1), fill=color)

    logo_data = spec["logo"]
    if logo_data.startswith("data:image/") and "," in logo_data:
        try:
            logo = Image.open(BytesIO(base64.b64decode(logo_data.split(",", 1)[1]))).convert("RGBA")
            target = max(48, round(qr_size * 0.17))
            logo.thumbnail((target, target), Image.Resampling.LANCZOS)
            pad = max(8, target // 10)
            box_size = max(logo.width, logo.height) + pad * 2
            box = Image.new("RGBA", (box_size, box_size), (255, 255, 255, 255))
            mask = Image.new("L", (box_size, box_size), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, box_size, box_size), radius=box_size // 5, fill=255)
            x = (box_size - logo.width) // 2
            y = (box_size - logo.height) // 2
            box.alpha_composite(logo, (x, y))
            pos = ((qr_size - box_size) // 2, (qr_size - box_size) // 2)
            canvas.paste(box, pos, mask)
        except Exception:
            pass

    if spec["frame"]:
        text = spec["frame_text"].strip() or "SCAN ME"
        font = ImageFont.load_default(size=max(16, qr_size // 27))
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        draw.text(((qr_size - width) / 2, qr_size + footer * 0.28), text, fill=first, font=font)

    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def build_custom_svg(payload: str, design: dict[str, Any] | None = None) -> bytes:
    spec = _design(design)
    matrix = _qr(payload, box_size=1).get_matrix()
    modules = len(matrix)
    margin = spec["margin"]
    total = modules + margin * 2
    footer = 7 if spec["frame"] else 0
    gradient = (
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{spec["fg"]}"/><stop offset="1" stop-color="{spec["gradient_to"]}"/>'
        "</linearGradient></defs>"
        if spec["gradient"] else ""
    )
    fill = "url(#g)" if spec["gradient"] else spec["fg"]
    elements: list[str] = []
    for y, row in enumerate(matrix):
        for x, active in enumerate(row):
            if not active:
                continue
            px, py = x + margin, y + margin
            if spec["shape"] == "dots":
                elements.append(f'<circle cx="{px + .5}" cy="{py + .5}" r=".47" fill="{fill}"/>')
            else:
                radius = ".28" if spec["shape"] == "rounded" else "0"
                elements.append(f'<rect x="{px}" y="{py}" width="1" height="1" rx="{radius}" fill="{fill}"/>')
    if spec["logo"].startswith("data:image/"):
        center = total / 2
        side = total * .18
        elements.append(
            f'<rect x="{center-side/2-.5}" y="{center-side/2-.5}" width="{side+1}" height="{side+1}" rx="1" fill="white"/>'
            f'<image href="{html.escape(spec["logo"], quote=True)}" x="{center-side/2}" y="{center-side/2}" width="{side}" height="{side}" preserveAspectRatio="xMidYMid meet"/>'
        )
    if spec["frame"]:
        elements.append(
            f'<text x="{total/2}" y="{total + 4.4}" text-anchor="middle" fill="{spec["fg"]}" '
            f'font-family="-apple-system,BlinkMacSystemFont,Arial" font-size="2.4" font-weight="700">'
            f'{html.escape(spec["frame_text"] or "SCAN ME")}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total + footer}" '
        f'width="{spec["size"]}" height="{spec["size"] + (spec["size"] * footer / total)}">'
        f'<rect width="100%" height="100%" fill="{spec["bg"]}"/>{gradient}{"".join(elements)}</svg>'
    )
    return svg.encode("utf-8")
