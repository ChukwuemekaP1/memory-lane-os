"""Sync tests: archive builders (ZIP + hand-rolled PDF structure)."""

import io
import re
import zipfile

from app.modules.archives.builders import (
    PdfWriter,
    build_memory_book_pdf,
    build_zip,
    jpeg_dimensions,
)


def test_build_zip_roundtrip():
    blob = build_zip({"a.txt": b"hello", "dir/b.bin": b"\x00\x01"})
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert sorted(archive.namelist()) == ["a.txt", "dir/b.bin"]
        assert archive.read("a.txt") == b"hello"


def test_pdf_structure_valid():
    writer = PdfWriter()
    writer.add_text_page("Title", ["First line", "Second line"])
    pdf = writer.finish("Title")
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    # Every xref offset must point at its "N 0 obj" header.
    startxref = int(re.search(rb"startxref\s+(\d+)", pdf).group(1))
    assert pdf[startxref:startxref + 4] == b"xref"
    body = pdf[startxref:].split(b"\n")
    assert body[0] == b"xref"
    count = int(body[1].split()[1])
    entries = [line.split()[0] for line in body[2:2 + count]]
    assert entries[0] == b"0000000000"
    for number, offset in enumerate(entries[1:], start=1):
        expect = f"{number} 0 obj".encode()
        assert pdf[int(offset):int(offset) + len(expect)] == expect, number


def test_pdf_book_report_and_jpeg_rejection():
    pdf, report = build_memory_book_pdf("T", [{"title": "M", "text": "hi"}])
    assert report["pages"] == 2  # cover + 1
    assert report["images_embedded"] == 0
    writer = PdfWriter()
    assert writer.add_jpeg_page(b"not-a-jpeg", "") is False
    assert jpeg_dimensions(b"short") is None
