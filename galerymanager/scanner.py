"""Varredura recursiva de diretórios em busca de arquivos."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

# Nomes ocultos/de sistema que nunca devem ser tratados como mídia.
_SKIP_NAMES: frozenset[str] = frozenset(
    {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}
)


def scan(root: Path, *, recursive: bool = True, follow_symlinks: bool = False) -> Iterator[Path]:
    """Gera todos os arquivos regulares abaixo de ``root``.

    Ignora arquivos ocultos de sistema. Diretórios ocultos (iniciados por '.')
    são pulados para evitar entrar em pastas de configuração/lixeira.
    """
    root = root.expanduser()
    if root.is_file():
        yield root
        return

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Poda diretórios ocultos in-place (afeta a descida do os.walk).
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if not recursive:
            dirnames[:] = []

        for name in filenames:
            if name in _SKIP_NAMES or name.startswith("._"):
                continue
            path = Path(dirpath) / name
            try:
                if path.is_file():
                    yield path
            except OSError:
                continue
