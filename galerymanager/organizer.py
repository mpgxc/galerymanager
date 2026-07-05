"""Planejamento e execução da reorganização da galeria."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

from .datesource import DatedFile, extract_date
from .media import MediaKind, classify
from .scanner import scan


class DuplicatePolicy:
    """Estratégias para quando o destino já existe."""

    RENAME = "rename"  # adiciona sufixo _1, _2, ...
    SKIP = "skip"      # não move/copia
    OVERWRITE = "overwrite"  # sobrescreve o destino


@dataclass
class PlannedMove:
    """Uma operação planejada para um único arquivo."""

    source: Path
    dest: Path
    dated: DatedFile
    reason: str = ""  # preenchido quando pulado (ex.: 'duplicado')

    @property
    def skipped(self) -> bool:
        return bool(self.reason)


@dataclass
class Report:
    """Resumo de uma execução (real ou simulada)."""

    moves: list[PlannedMove] = field(default_factory=list)
    skipped: list[PlannedMove] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    ignored_other: int = 0

    @property
    def total_planned(self) -> int:
        return len(self.moves)

    def by_kind(self) -> dict[MediaKind, int]:
        counts: dict[MediaKind, int] = {}
        for m in self.moves:
            counts[m.dated.kind] = counts.get(m.dated.kind, 0) + 1
        return counts


def _sanitize(name: str) -> str:
    """Remove caracteres problemáticos de nomes de componente de caminho."""
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip() or "sem-nome"


def _date_subpath(date: datetime, pattern: str) -> Path:
    """Constrói o subcaminho de data a partir de um padrão strftime.

    O padrão pode conter '/' para criar níveis (ex.: '%Y/%Y-%m').
    """
    rendered = date.strftime(pattern)
    parts = [_sanitize(p) for p in rendered.split("/") if p]
    return Path(*parts) if parts else Path(_sanitize(rendered))


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _same_content(a: Path, b: Path) -> bool:
    """True se dois arquivos têm o mesmo conteúdo (tamanho + hash)."""
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return _sha256(a) == _sha256(b)
    except OSError:
        return False


def _unique_dest(dest: Path, reserved: "set[Path] | frozenset[Path]" = frozenset()) -> Path:
    """Gera um destino livre adicionando sufixo _1, _2, ...

    Considera livre um caminho que não existe em disco *e* não foi reservado
    por uma movimentação já planejada nesta execução (``reserved``).
    """
    if not dest.exists() and dest not in reserved:
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists() and candidate not in reserved:
            return candidate
        i += 1


class Organizer:
    """Orquestra a varredura, o planejamento e a execução."""

    def __init__(
        self,
        dest_root: Path,
        *,
        date_pattern: str = "%Y/%Y-%m",
        move: bool = False,
        recursive: bool = True,
        include_other: bool = False,
        duplicate_policy: str = DuplicatePolicy.RENAME,
        folder_names: Optional[dict[MediaKind, str]] = None,
    ) -> None:
        self.dest_root = Path(dest_root).expanduser()
        self.date_pattern = date_pattern
        self.move = move
        self.recursive = recursive
        self.include_other = include_other
        self.duplicate_policy = duplicate_policy
        self.folder_names = folder_names or {}

    def _kind_folder(self, kind: MediaKind) -> str:
        return self.folder_names.get(kind, kind.folder)

    def target_for(self, dated: DatedFile) -> Path:
        """Calcula o caminho de destino final (antes de tratar duplicatas)."""
        kind_folder = self._kind_folder(dated.kind)
        sub = _date_subpath(dated.date, self.date_pattern)
        return self.dest_root / kind_folder / sub / dated.path.name

    def plan(self, sources: Iterable[Path]) -> Report:
        """Monta o plano de movimentação sem tocar em nenhum arquivo."""
        report = Report()
        seen_dests: set[Path] = set()

        for source in sources:
            for path in scan(source, recursive=self.recursive):
                try:
                    kind = classify(path)
                    if kind is MediaKind.OTHER and not self.include_other:
                        report.ignored_other += 1
                        continue

                    dated = extract_date(path, kind)
                    dest = self.target_for(dated)

                    # Nunca reorganizar algo que já está no lugar certo.
                    if dest.resolve() == path.resolve():
                        continue

                    move = self._resolve_collision(path, dest, seen_dests)
                    if move.skipped:
                        report.skipped.append(move)
                    else:
                        seen_dests.add(move.dest)
                        report.moves.append(move)
                except OSError as exc:
                    report.errors.append((path, str(exc)))

        return report

    def _resolve_collision(
        self, source: Path, dest: Path, seen_dests: set[Path]
    ) -> PlannedMove:
        """Aplica a política de duplicatas e retorna a movimentação planejada."""
        dated = extract_date(source)
        collides = dest.exists() or dest in seen_dests

        if not collides:
            return PlannedMove(source=source, dest=dest, dated=dated)

        # Duplicata idêntica já existente: nunca copiar de novo.
        if dest.exists() and _same_content(source, dest):
            return PlannedMove(
                source=source, dest=dest, dated=dated, reason="idêntico-já-existe"
            )

        if self.duplicate_policy == DuplicatePolicy.SKIP:
            return PlannedMove(
                source=source, dest=dest, dated=dated, reason="destino-existe"
            )
        if self.duplicate_policy == DuplicatePolicy.OVERWRITE:
            return PlannedMove(source=source, dest=dest, dated=dated)

        # RENAME (padrão): acha um nome livre, considerando também os destinos
        # já reservados por outras movimentações desta mesma execução.
        candidate = _unique_dest(dest, seen_dests)
        return PlannedMove(source=source, dest=candidate, dated=dated)

    def execute(
        self,
        report: Report,
        *,
        progress: Optional[Callable[[PlannedMove], None]] = None,
    ) -> Report:
        """Executa as movimentações planejadas no relatório."""
        done: list[PlannedMove] = []
        for move in report.moves:
            try:
                move.dest.parent.mkdir(parents=True, exist_ok=True)
                if self.move:
                    shutil.move(str(move.source), str(move.dest))
                else:
                    shutil.copy2(str(move.source), str(move.dest))
                done.append(move)
                if progress is not None:
                    progress(move)
            except OSError as exc:
                report.errors.append((move.source, str(exc)))
        report.moves = done
        return report

    def run(
        self,
        sources: Iterable[Path],
        *,
        dry_run: bool = True,
        progress: Optional[Callable[[PlannedMove], None]] = None,
    ) -> Report:
        """Planeja e (se não for dry-run) executa em uma única chamada."""
        report = self.plan(sources)
        if not dry_run:
            self.execute(report, progress=progress)
        return report
