"""galerymanager - organizador de fotos e vídeos por data.

Varre pastas e subpastas, identifica imagens e vídeos e os reorganiza em
uma estrutura limpa por tipo e data:

    <destino>/
        Imagens/AAAA/AAAA-MM/arquivo.jpg
        Videos/AAAA/AAAA-MM/arquivo.mp4

Funciona em Linux e macOS usando apenas a biblioteca padrão do Python.
"""

from .media import MediaKind, classify
from .datesource import extract_date
from .organizer import Organizer, PlannedMove, Report

__version__ = "0.1.0"

__all__ = [
    "MediaKind",
    "classify",
    "extract_date",
    "Organizer",
    "PlannedMove",
    "Report",
    "__version__",
]
