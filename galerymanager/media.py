"""Classificação de arquivos de mídia por extensão."""

from __future__ import annotations

import enum
from pathlib import Path


class MediaKind(enum.Enum):
    """Categoria de um arquivo."""

    IMAGE = "Imagens"
    VIDEO = "Videos"
    OTHER = "Outros"

    @property
    def folder(self) -> str:
        """Nome da pasta de destino para esta categoria."""
        return self.value


# Extensões reconhecidas (sempre em minúsculas, sem o ponto).
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        "jpg", "jpeg", "jpe", "jfif",
        "png", "gif", "bmp", "tif", "tiff",
        "webp", "heic", "heif", "avif",
        "raw", "arw", "cr2", "cr3", "nef", "orf",
        "rw2", "dng", "raf", "sr2", "pef",
        "svg", "ico",
    }
)

VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        "mp4", "m4v", "mov", "avi", "mkv",
        "wmv", "flv", "webm", "mpg", "mpeg",
        "3gp", "3g2", "mts", "m2ts", "ts",
        "vob", "ogv", "mxf",
    }
)


def extension_of(path: Path) -> str:
    """Retorna a extensão em minúsculas, sem ponto (ex.: 'jpg')."""
    return path.suffix.lower().lstrip(".")


def classify(path: Path) -> MediaKind:
    """Classifica um arquivo como imagem, vídeo ou outro pela extensão."""
    ext = extension_of(path)
    if ext in IMAGE_EXTENSIONS:
        return MediaKind.IMAGE
    if ext in VIDEO_EXTENSIONS:
        return MediaKind.VIDEO
    return MediaKind.OTHER
