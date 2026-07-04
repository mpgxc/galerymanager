"""Determina a melhor data para organizar um arquivo de mídia."""

from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional

from . import exif
from .media import MediaKind, classify


class DateOrigin(enum.Enum):
    """De onde a data foi obtida (para relatórios/depuração)."""

    EXIF = "exif"
    VIDEO_METADATA = "metadados-video"
    FILE_MTIME = "data-modificacao"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class DatedFile(NamedTuple):
    """Um arquivo já resolvido com sua data e origem."""

    path: Path
    kind: MediaKind
    date: datetime
    origin: DateOrigin


def _file_mtime(path: Path) -> datetime:
    """Data de modificação do arquivo, como fallback confiável."""
    return datetime.fromtimestamp(path.stat().st_mtime)


def extract_date(path: Path, kind: Optional[MediaKind] = None) -> DatedFile:
    """Resolve a data de captura de um arquivo.

    Ordem de preferência:
      1. EXIF (imagens) / metadados 'mvhd' (vídeos);
      2. data de modificação do arquivo.

    Nunca levanta exceção por metadados ausentes; sempre retorna uma data.
    """
    if kind is None:
        kind = classify(path)

    metadata_date: Optional[datetime] = None
    origin = DateOrigin.FILE_MTIME

    if kind is MediaKind.IMAGE:
        metadata_date = exif.read_image_datetime(path)
        if metadata_date is not None:
            origin = DateOrigin.EXIF
    elif kind is MediaKind.VIDEO:
        metadata_date = exif.read_video_datetime(path)
        if metadata_date is not None:
            origin = DateOrigin.VIDEO_METADATA

    date = metadata_date if metadata_date is not None else _file_mtime(path)
    return DatedFile(path=path, kind=kind, date=date, origin=origin)
