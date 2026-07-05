"""Testes do galerymanager (apenas stdlib + unittest)."""

from __future__ import annotations

import os
import struct
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from galerymanager.datesource import DateOrigin, extract_date
from galerymanager.media import MediaKind, classify
from galerymanager.organizer import DuplicatePolicy, Organizer


def _touch(path: Path, content: bytes = b"x", mtime: datetime | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        ts = mtime.timestamp()
        os.utime(path, (ts, ts))
    return path


def _jpeg_with_exif(dt: datetime) -> bytes:
    """Constrói um JPEG mínimo com um segmento EXIF DateTimeOriginal."""
    date_str = dt.strftime("%Y:%m:%d %H:%M:%S").encode("ascii") + b"\x00"  # 20 bytes

    endian = b"MM"  # big-endian
    # IFD0 com um único ponteiro para o Exif sub-IFD.
    # Layout do bloco TIFF:
    #   [0:8]   cabeçalho TIFF (MM, 42, offset IFD0=8)
    #   IFD0 em 8
    tiff = bytearray()
    tiff += endian + struct.pack(">H", 42) + struct.pack(">I", 8)

    # IFD0: 1 entrada (ExifIFDPointer 0x8769, type LONG, count 1)
    ifd0_offset = 8
    exif_ifd_offset = ifd0_offset + 2 + 12 + 4  # após count+entrada+next
    tiff += struct.pack(">H", 1)
    tiff += struct.pack(">HHI", 0x8769, 4, 1) + struct.pack(">I", exif_ifd_offset)
    tiff += struct.pack(">I", 0)  # next IFD = 0

    # Exif sub-IFD: 1 entrada (DateTimeOriginal 0x9003, ASCII, count=20)
    # A string (20 bytes) vem logo após a estrutura do sub-IFD.
    str_offset = exif_ifd_offset + 2 + 12 + 4
    tiff += struct.pack(">H", 1)
    tiff += struct.pack(">HHI", 0x9003, 2, len(date_str)) + struct.pack(">I", str_offset)
    tiff += struct.pack(">I", 0)  # next IFD = 0
    tiff += date_str

    exif_payload = b"Exif\x00\x00" + bytes(tiff)
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload

    # SOI + APP1 + EOI (sem dados de imagem reais; suficiente para o parser).
    return b"\xff\xd8" + app1 + b"\xff\xd9"


class TestClassify(unittest.TestCase):
    def test_image_extensions(self):
        self.assertIs(classify(Path("a.JPG")), MediaKind.IMAGE)
        self.assertIs(classify(Path("a.heic")), MediaKind.IMAGE)

    def test_video_extensions(self):
        self.assertIs(classify(Path("a.MP4")), MediaKind.VIDEO)
        self.assertIs(classify(Path("a.mkv")), MediaKind.VIDEO)

    def test_other(self):
        self.assertIs(classify(Path("a.txt")), MediaKind.OTHER)


class TestExtractDate(unittest.TestCase):
    def test_exif_takes_priority(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "foto.jpg"
            exif_dt = datetime(2019, 5, 4, 12, 30, 0)
            _touch(p, _jpeg_with_exif(exif_dt), mtime=datetime(2023, 1, 1))
            dated = extract_date(p)
            self.assertEqual(dated.origin, DateOrigin.EXIF)
            self.assertEqual(dated.date, exif_dt)

    def test_fallback_to_mtime(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "foto.png"
            mtime = datetime(2021, 7, 15, 8, 0, 0)
            _touch(p, b"notarealpng", mtime=mtime)
            dated = extract_date(p)
            self.assertEqual(dated.origin, DateOrigin.FILE_MTIME)
            self.assertEqual(dated.date.year, 2021)
            self.assertEqual(dated.date.month, 7)


class TestOrganizer(unittest.TestCase):
    def test_plan_structure(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            src, dst = Path(src), Path(dst)
            _touch(src / "sub" / "foto.jpg", _jpeg_with_exif(datetime(2020, 3, 2, 10, 0)))
            _touch(src / "clip.mp4", b"video", mtime=datetime(2022, 11, 5))
            _touch(src / "nota.txt", b"texto")

            org = Organizer(dst)
            report = org.plan([src])

            self.assertEqual(report.by_kind().get(MediaKind.IMAGE), 1)
            self.assertEqual(report.by_kind().get(MediaKind.VIDEO), 1)
            self.assertEqual(report.ignored_other, 1)

            dests = {m.dest.relative_to(dst).as_posix() for m in report.moves}
            self.assertIn("Imagens/2020/2020-03/foto.jpg", dests)
            self.assertIn("Videos/2022/2022-11/clip.mp4", dests)

    def test_execute_copy(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            src, dst = Path(src), Path(dst)
            _touch(src / "foto.jpg", _jpeg_with_exif(datetime(2020, 3, 2, 10, 0)))

            org = Organizer(dst, move=False)
            report = org.run([src], dry_run=False)

            self.assertEqual(len(report.moves), 1)
            self.assertTrue((dst / "Imagens/2020/2020-03/foto.jpg").exists())
            self.assertTrue((src / "foto.jpg").exists())  # cópia preserva a origem

    def test_execute_move(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            src, dst = Path(src), Path(dst)
            _touch(src / "foto.jpg", _jpeg_with_exif(datetime(2020, 3, 2, 10, 0)))

            org = Organizer(dst, move=True)
            org.run([src], dry_run=False)

            self.assertTrue((dst / "Imagens/2020/2020-03/foto.jpg").exists())
            self.assertFalse((src / "foto.jpg").exists())  # movido

    def test_identical_duplicate_skipped(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            src, dst = Path(src), Path(dst)
            content = _jpeg_with_exif(datetime(2020, 3, 2, 10, 0))
            _touch(src / "foto.jpg", content)

            org = Organizer(dst)
            org.run([src], dry_run=False)
            # Segunda passada: destino idêntico já existe -> pulado.
            report = org.run([src], dry_run=False)
            self.assertEqual(len(report.moves), 0)
            self.assertEqual(len(report.skipped), 1)

    def test_rename_on_different_content(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            src, dst = Path(src), Path(dst)
            _touch(src / "a" / "foto.jpg", _jpeg_with_exif(datetime(2020, 3, 2, 10, 0)))
            # Mesmo nome e data, conteúdo diferente -> deve renomear.
            other = bytearray(_jpeg_with_exif(datetime(2020, 3, 2, 10, 0)))
            other += b"\x00extra"
            _touch(src / "b" / "foto.jpg", bytes(other))

            org = Organizer(dst, duplicate_policy=DuplicatePolicy.RENAME)
            report = org.run([src], dry_run=False)
            names = sorted(m.dest.name for m in report.moves)
            self.assertEqual(names, ["foto.jpg", "foto_1.jpg"])

    def test_custom_pattern(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            src, dst = Path(src), Path(dst)
            _touch(src / "foto.jpg", _jpeg_with_exif(datetime(2020, 3, 2, 10, 0)))
            org = Organizer(dst, date_pattern="%Y/%Y-%m/%d")
            report = org.plan([src])
            rel = report.moves[0].dest.relative_to(dst).as_posix()
            self.assertEqual(rel, "Imagens/2020/2020-03/02/foto.jpg")


if __name__ == "__main__":
    unittest.main()
