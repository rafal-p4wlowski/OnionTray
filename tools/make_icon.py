r"""Generate assets/icon.ico (application icon: a keyboard).

Run from the project root:  .venv\Scripts\python tools\make_icon.py
Each size is drawn separately and stored as a PNG entry in the .ico container.
"""
import os
import struct
import sys

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND = QColor("#1E1E1E")
ACCENT = QColor("#22C55E")


def draw(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 64, size / 64)

    # rounded square background
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BACKGROUND)
    p.drawRoundedRect(QRectF(1, 1, 62, 62), 14, 14)

    # keyboard body outline
    p.setPen(QPen(ACCENT, 5 if size <= 24 else 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(7, 17, 50, 32), 5, 5)

    # keys: fewer, bigger ones at small sizes so they stay visible
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ACCENT)
    cols = 3 if size <= 24 else 5
    gap = 2.5
    key_w = (40 - gap * (cols - 1)) / cols
    for row in range(2):
        for col in range(cols):
            p.drawRoundedRect(QRectF(12 + col * (key_w + gap), 22 + row * 8, key_w, 5.5), 1.5, 1.5)
    p.drawRoundedRect(QRectF(20, 39, 24, 5.5), 1.5, 1.5)  # space bar
    p.end()
    return img


def png_bytes(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def write_ico(path, images):
    entries = [(img.width(), png_bytes(img)) for img in images]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory, blobs = b"", b""
    for size, blob in entries:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(header + directory + blobs)


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 (needed for QPainter)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "assets", "icon.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_ico(out, [draw(s) for s in SIZES])
    print("written", out)


if __name__ == "__main__":
    main()
