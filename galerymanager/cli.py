"""Interface de linha de comando do galerymanager."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .media import MediaKind
from .organizer import DuplicatePolicy, Organizer, PlannedMove, Report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="galerymanager",
        description=(
            "Organiza fotos e vídeos em pastas por tipo e data. "
            "Lê pastas e subpastas recursivamente e cria uma estrutura "
            "Imagens/AAAA/AAAA-MM e Videos/AAAA/AAAA-MM."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  galerymanager ~/Fotos -o ~/Galeria --dry-run\n"
            "  galerymanager ~/Downloads ~/Camera -o ~/Galeria --move\n"
            "  galerymanager ~/Fotos -o ~/Galeria --pattern '%%Y/%%Y-%%m/%%d'\n"
        ),
    )
    parser.add_argument(
        "sources",
        nargs="+",
        type=Path,
        help="Uma ou mais pastas (ou arquivos) de origem a organizar.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Pasta de destino onde a galeria organizada será criada.",
    )
    parser.add_argument(
        "--pattern",
        default="%Y/%Y-%m",
        help="Padrão strftime das subpastas de data (padrão: %%Y/%%Y-%%m).",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Mover os arquivos em vez de copiar (padrão: copiar).",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Não descer em subpastas das origens.",
    )
    parser.add_argument(
        "--include-other",
        action="store_true",
        help="Também organizar arquivos que não são imagem/vídeo (pasta Outros).",
    )
    parser.add_argument(
        "--on-duplicate",
        choices=[DuplicatePolicy.RENAME, DuplicatePolicy.SKIP, DuplicatePolicy.OVERWRITE],
        default=DuplicatePolicy.RENAME,
        help="O que fazer quando o destino já existe (padrão: rename).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas simular: mostra o que seria feito, sem alterar arquivos.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Reduzir a saída (mostra apenas o resumo).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _print_move(move: PlannedMove, dest_root: Path, action: str) -> None:
    try:
        rel = move.dest.relative_to(dest_root)
    except ValueError:
        rel = move.dest
    print(f"  {action} {move.source}  ->  {rel}  [{move.dated.origin}]")


def _print_summary(report: Report, dest_root: Path, dry_run: bool, moved: bool) -> None:
    counts = report.by_kind()
    verb = "seriam processados" if dry_run else "processados"
    print()
    print("Resumo:")
    print(f"  Imagens: {counts.get(MediaKind.IMAGE, 0)}")
    print(f"  Vídeos:  {counts.get(MediaKind.VIDEO, 0)}")
    if MediaKind.OTHER in counts:
        print(f"  Outros:  {counts.get(MediaKind.OTHER, 0)}")
    op = "movidos" if moved else "copiados"
    print(f"  Total {verb} ({op}): {report.total_planned}")
    if report.skipped:
        print(f"  Pulados (duplicados/existentes): {len(report.skipped)}")
    if report.ignored_other:
        print(f"  Ignorados (não são mídia): {report.ignored_other}")
    if report.errors:
        print(f"  Erros: {len(report.errors)}")
        for path, msg in report.errors[:10]:
            print(f"    ! {path}: {msg}")
    if dry_run:
        print()
        print("  (dry-run: nenhum arquivo foi alterado. Rode sem --dry-run para aplicar.)")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    missing = [s for s in args.sources if not s.expanduser().exists()]
    if missing:
        for s in missing:
            print(f"erro: origem não encontrada: {s}", file=sys.stderr)
        return 2

    organizer = Organizer(
        dest_root=args.output,
        date_pattern=args.pattern,
        move=args.move,
        recursive=not args.no_recursive,
        include_other=args.include_other,
        duplicate_policy=args.on_duplicate,
    )

    report = organizer.plan(args.sources)

    action = "MOVER " if args.move else "COPIAR"
    if not args.quiet:
        if report.moves:
            header = "Plano (dry-run):" if args.dry_run else "Aplicando:"
            print(header)
        for move in report.moves:
            _print_move(move, organizer.dest_root, action)

    if not args.dry_run and report.moves:
        organizer.execute(report)

    _print_summary(report, organizer.dest_root, args.dry_run, args.move)
    return 1 if report.errors else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
