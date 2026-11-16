r"""Generate assets/icon.ico (application icon: a keyboard in a full green battery ring).

The same artwork as the tray icon (ui_components), on a dark disc so it reads on
light and dark Explorer backgrounds alike.
Run from the project root:  .venv\Scripts\python tools\make_icon.py
Each size is drawn separately and stored as a PNG entry in the .ico container.
"""
import os
import struct
import sys

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ui_components  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND = QColor("#1E1E1E")


def draw(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BACKGROUND)
    inset = size / 64          # keep the disc edge under the ring
    p.drawEllipse(QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    # full, charging-green ring with the white glyph of a dark taskbar
    p.drawPixmap(0, 0, ui_components.render_icon(size, 100, charging=True, light_taskbar=False))
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
    out = os.path.join(ROOT, "assets", "icon.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_ico(out, [draw(s) for s in SIZES])
    print("written", out)


if __name__ == "__main__":
    main()
