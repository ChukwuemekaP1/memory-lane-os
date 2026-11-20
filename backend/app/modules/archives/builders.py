"""Archive builders: dependency-free ZIP/PDF/slideshow construction.

The PDF writer emits minimal valid PDF 1.4 (text pages + JPEG passthrough).
PNG/GIF originals are listed, not embedded (honest limitation, noted in the
manifest) — re-encoding would need an imaging library.
"""

from __future__ import annotations

import io
import struct
import zipfile
from typing import Any


def build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return buffer.getvalue()


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Parse width/height from JPEG SOF markers. None when unparseable."""
    pos = 2
    try:
        while pos + 8 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                return width, height
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
            pos += 2 + length
    except (IndexError, struct.error):
        return None
    return None


def _pdf_escape(text: str) -> str:
    cleaned = text.encode("latin-1", errors="replace").decode("latin-1")
    return cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_lines(text: str, width: int = 90) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        probe = f"{current} {word}".strip()
        if len(probe) > width and current:
            lines.append(current)
            current = word
        else:
            current = probe
    if current:
        lines.append(current)
    return lines or [""]


class PdfWriter:
    """Minimal PDF 1.4 writer: Helvetica text pages + JPEG image pages.

    Object ids 1 (catalog), 2 (pages), 3 (font) are reserved upfront so every
    reference written during page construction is already final.
    """

    def __init__(self) -> None:
        self._objects: list[bytes | None] = [None, None, None]
        self._page_ids: list[int] = []

    def _add(self, body: bytes) -> int:
        self._objects.append(body)
        return len(self._objects)

    def add_text_page(self, title: str, lines: list[str]) -> None:
        content = ["BT /F1 18 Tf 50 770 Td 22 TL"]
        content.append(f"({_pdf_escape(title)}) Tj T*")
        content.append("/F1 11 Tf 15 TL")
        for line in lines[:52]:
            for chunk in _wrap_lines(line):
                content.append(f"({_pdf_escape(chunk)}) Tj T*")
        content.append("ET")
        stream = "\n".join(content).encode("latin-1")
        stream_id = self._add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_id = self._add(
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {stream_id} 0 R >>".encode())
        self._page_ids.append(page_id)

    def add_jpeg_page(self, jpeg: bytes, caption: str = "") -> bool:
        dims = jpeg_dimensions(jpeg)
        if dims is None:
            return False
        width, height = dims
        scale = min(512 / width, 680 / height)
        draw_w, draw_h = width * scale, height * scale
        x, y = (612 - draw_w) / 2, (792 - draw_h) / 2 + 20
        image_id = self._add(
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
            f"/Length {len(jpeg)} >>\nstream\n".encode() + jpeg + b"\nendstream")
        content = (f"q {draw_w:.1f} 0 0 {draw_h:.1f} {x:.1f} {y:.1f} cm /Im1 Do Q\n"
                   f"BT /F1 10 Tf 50 40 Td ({_pdf_escape(caption[:90])}) Tj ET").encode("latin-1")
        stream_id = self._add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        page_id = self._add(
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> "
            f"/XObject << /Im1 {image_id} 0 R >> >> /MediaBox [0 0 612 792] "
            f"/Contents {stream_id} 0 R >>".encode())
        self._page_ids.append(page_id)
        return True

    def finish(self, title: str) -> bytes:
        kids = " ".join(f"{page_id} 0 R" for page_id in self._page_ids)
        self._objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        self._objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(self._page_ids)} >>".encode()
        self._objects[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        out = io.BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, obj in enumerate(self._objects, start=1):
            assert obj is not None
            offsets.append(out.tell())
            out.write(f"{index} 0 obj\n".encode())
            out.write(obj)
            out.write(b"\nendobj\n")
        xref_at = out.tell()
        out.write(f"xref\n0 {len(self._objects) + 1}\n".encode())
        out.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            out.write(f"{offset:010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {len(self._objects) + 1} /Root 1 0 R "
                  f"/Info << /Title ({_pdf_escape(title[:120])}) >> >>\n".encode())
        out.write(b"startxref\n" + str(xref_at).encode() + b"\n%%EOF")
        return out.getvalue()


def build_memory_book_pdf(title: str, entries: list[dict[str, Any]]) -> tuple[bytes, dict]:
    """entries: [{kind, title, text} | {image_jpeg, caption}]. Returns (pdf, report)."""
    writer = PdfWriter()
    writer.add_text_page(title, ["A Memory Lane keepsake."])
    embedded = skipped = 0
    for entry in entries:
        if entry.get("image_jpeg"):
            if writer.add_jpeg_page(entry["image_jpeg"], entry.get("caption", "")):
                embedded += 1
            else:
                skipped += 1
        else:
            writer.add_text_page(entry.get("title", "Memory"), (entry.get("text") or "").split("\n"))
    pdf = writer.finish(title)
    report = {"pages": len(writer._page_ids), "images_embedded": embedded,
              "images_skipped": skipped,
              "note": "Only JPEG photos embed; other formats are listed in the manifest."}
    return pdf, report
