from __future__ import annotations

from io import BytesIO

import qrcode
import qrcode.image.svg
from qrcode.constants import ERROR_CORRECT_H
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styledpil import StyledPilImage
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
