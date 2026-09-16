"""Generate installer/elite-hud.ico from the HUD's own vector glyph.

The project ships no binary art, so the application icon is rendered at build
time and wrapped in a Windows .ico container (PNG-compressed entries, which
Vista and later accept).

    python tools/make_icon.py [output.ico]
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from elite_hud.overlay.icons import draw_glyph  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "installer" / "elite-hud.ico"

#: Windows picks the closest entry, so cover the taskbar through to the
#: "extra large icons" Explorer view.
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

BACKGROUND = "#0b0f14"
ACCENT = "#ff9d2e"
LEAF = "#5ee08a"


def render_png(size: int) -> bytes:
    """Render one icon frame and return it as PNG bytes."""
    from PySide6.QtGui import QImage, QPixmap

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    plate = QRectF(size * 0.03, size * 0.03, size * 0.94, size * 0.94)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BACKGROUND))
    painter.drawRoundedRect(plate, size * 0.22, size * 0.22)

    # A thin accent frame keeps the icon readable against dark taskbars.
    pen = QPen(QColor(ACCENT))
    pen.setWidthF(max(1.0, size * 0.045))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(plate, size * 0.22, size * 0.22)

    # The leaf is the HUD's "organic here" marker; below 24px the stroke detail
    # turns to mush, so the glyph gets a little more room instead.
    inset = size * (0.30 if size < 24 else 0.26)
    draw_glyph(painter, inset, inset, size - inset * 2, "bio", QColor(LEAF))
    painter.end()

    image: QImage = pixmap.toImage()
    # The QByteArray must outlive the QBuffer: QBuffer holds a raw pointer to
    # it, so passing a temporary here segfaults.
    storage = QByteArray()
    buffer = QBuffer(storage)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(storage)


def build_ico(frames: dict[int, bytes]) -> bytes:
    """Wrap PNG frames in an ICO container."""
    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)
    entries = bytearray()
    payload = bytearray()
    offset = 6 + 16 * count

    for size in sorted(frames):
        data = frames[size]
        # 0 means 256 in the ICO directory entry.
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            dimension,  # width
            dimension,  # height
            0,  # palette colours
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(data),
            offset,
        )
        payload += data
        offset += len(data)

    return bytes(header + entries + payload)


def main(argv: list[str]) -> int:
    output = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    app = QApplication.instance() or QApplication(sys.argv[:1])

    frames = {size: render_png(size) for size in SIZES}
    for size, data in frames.items():
        if len(data) < 100:
            print(f"frame {size}px looks empty ({len(data)} bytes)", file=sys.stderr)
            return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_ico(frames))
    print(f"wrote {output.relative_to(REPO_ROOT)} ({output.stat().st_size} bytes, {len(frames)} sizes)")

    # Read it back through Qt to prove the container is well formed.
    from PySide6.QtGui import QIcon

    icon = QIcon(str(output))
    if icon.isNull() or not icon.availableSizes():
        print("the generated icon could not be read back", file=sys.stderr)
        return 1
    print("sizes readable by Qt:", ", ".join(f"{s.width()}px" for s in icon.availableSizes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
