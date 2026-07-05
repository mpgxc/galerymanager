"""Leitura mínima de metadados de data, apenas com a biblioteca padrão.

Suporta:
  * EXIF DateTimeOriginal/DateTime em arquivos JPEG e TIFF;
  * data de criação em contêineres ISO-BMFF (MP4/MOV/M4V/3GP) via a box 'mvhd'.

Não requer Pillow nem ffmpeg. Todas as funções retornam ``datetime`` ou
``None`` e nunca levantam exceções para arquivos malformados.
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Tags EXIF de data/hora, em ordem de preferência.
_TAG_DATETIME_ORIGINAL = 0x9003  # DateTimeOriginal
_TAG_DATETIME_DIGITIZED = 0x9004  # DateTimeDigitized
_TAG_DATETIME = 0x0132  # DateTime (última modificação)
_TAG_EXIF_IFD = 0x8769  # ponteiro para o sub-IFD do EXIF

# Diferença entre a época do QuickTime/MP4 (1904-01-01) e a Unix (1970-01-01).
_EPOCH_1904_TO_1970 = 2082844800


def _parse_exif_datetime(value: str) -> Optional[datetime]:
    """Converte 'AAAA:MM:DD HH:MM:SS' (formato EXIF) em ``datetime``."""
    value = value.strip().rstrip("\x00").strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError:
            continue
        # 0000:00:00 é usado por algumas câmeras como "sem data".
        if dt.year < 1900:
            return None
        return dt
    return None


def _read_tiff_datetime(data: bytes) -> Optional[datetime]:
    """Extrai a melhor data de um bloco TIFF (usado dentro do EXIF)."""
    if len(data) < 8:
        return None

    byte_order = data[0:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return None

    (magic,) = struct.unpack(endian + "H", data[2:4])
    if magic != 42:
        return None
    (first_ifd,) = struct.unpack(endian + "I", data[4:8])

    found: dict[int, str] = {}

    def read_ifd(offset: int, depth: int = 0) -> None:
        if depth > 4 or offset <= 0 or offset + 2 > len(data):
            return
        (count,) = struct.unpack(endian + "H", data[offset : offset + 2])
        entry = offset + 2
        for _ in range(count):
            if entry + 12 > len(data):
                return
            tag, typ, num = struct.unpack(endian + "HHI", data[entry : entry + 8])
            value_field = data[entry + 8 : entry + 12]
            entry += 12

            if tag == _TAG_EXIF_IFD and typ == 4:
                (sub,) = struct.unpack(endian + "I", value_field)
                read_ifd(sub, depth + 1)
                continue

            if tag in (_TAG_DATETIME_ORIGINAL, _TAG_DATETIME_DIGITIZED, _TAG_DATETIME):
                # ASCII (type 2); o valor é uma string com 'num' bytes.
                if typ != 2 or num == 0:
                    continue
                if num <= 4:
                    raw = value_field[:num]
                else:
                    (str_off,) = struct.unpack(endian + "I", value_field)
                    raw = data[str_off : str_off + num]
                try:
                    found[tag] = raw.decode("ascii", errors="ignore")
                except Exception:
                    pass

    read_ifd(first_ifd)

    for tag in (_TAG_DATETIME_ORIGINAL, _TAG_DATETIME_DIGITIZED, _TAG_DATETIME):
        if tag in found:
            dt = _parse_exif_datetime(found[tag])
            if dt is not None:
                return dt
    return None


def _read_jpeg_exif_datetime(fh) -> Optional[datetime]:
    """Percorre os segmentos de um JPEG procurando o bloco EXIF (APP1)."""
    if fh.read(2) != b"\xff\xd8":  # SOI
        return None
    while True:
        marker = fh.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        tag = marker[1]
        if tag in (0xD9, 0xDA):  # EOI ou início dos dados de imagem
            return None
        length_bytes = fh.read(2)
        if len(length_bytes) < 2:
            return None
        (length,) = struct.unpack(">H", length_bytes)
        if length < 2:
            return None
        segment = fh.read(length - 2)
        if tag == 0xE1 and segment[:6] == b"Exif\x00\x00":
            return _read_tiff_datetime(segment[6:])
        # Continua para o próximo marcador.


def read_image_datetime(path: Path) -> Optional[datetime]:
    """Data original de captura de uma imagem, ou ``None`` se indisponível."""
    try:
        with path.open("rb") as fh:
            head = fh.read(4)
            fh.seek(0)
            if head[:2] == b"\xff\xd8":  # JPEG
                return _read_jpeg_exif_datetime(fh)
            if head[:2] in (b"II", b"MM"):  # TIFF (inclui muitos RAW)
                return _read_tiff_datetime(fh.read())
    except (OSError, struct.error):
        return None
    return None


def _iter_boxes(fh, end: int):
    """Itera boxes ISO-BMFF no intervalo [pos, end), retornando (tipo, ini, fim)."""
    while fh.tell() + 8 <= end:
        start = fh.tell()
        header = fh.read(8)
        if len(header) < 8:
            return
        size, box_type = struct.unpack(">I4s", header)
        if size == 1:  # tamanho estendido de 64 bits
            ext = fh.read(8)
            if len(ext) < 8:
                return
            (size,) = struct.unpack(">Q", ext)
        elif size == 0:  # vai até o fim do arquivo
            size = end - start
        if size < 8:
            return
        yield box_type, start, start + size
        fh.seek(start + size)


def read_video_datetime(path: Path) -> Optional[datetime]:
    """Data de criação de um vídeo MP4/MOV (box 'mvhd'), ou ``None``."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            file_size = fh.tell()
            fh.seek(0)
            for box_type, _start, box_end in _iter_boxes(fh, file_size):
                if box_type != b"moov":
                    continue
                for inner_type, inner_start, _inner_end in _iter_boxes(fh, box_end):
                    if inner_type != b"mvhd":
                        continue
                    fh.seek(inner_start + 8)
                    version = fh.read(1)[0]
                    fh.read(3)  # flags
                    if version == 1:
                        created = struct.unpack(">Q", fh.read(8))[0]
                    else:
                        created = struct.unpack(">I", fh.read(4))[0]
                    if created == 0:
                        return None
                    unix_ts = created - _EPOCH_1904_TO_1970
                    if unix_ts <= 0:
                        return None
                    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).replace(
                        tzinfo=None
                    )
    except (OSError, struct.error, IndexError):
        return None
    return None
