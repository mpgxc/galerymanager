# galerymanager

Organizador de **fotos e vídeos** por **tipo** e **data**, escrito em Python.
Lê pastas e subpastas recursivamente, identifica cada arquivo de mídia,
descobre a data em que foi capturado e reorganiza tudo em uma estrutura limpa:

```
<destino>/
├── Imagens/
│   └── 2021/
│       └── 2021-07/
│           └── praia.jpg
└── Videos/
    └── 2022/
        └── 2022-12/
            └── clip.mp4
```

Funciona em **Linux** e **macOS** usando **apenas a biblioteca padrão do
Python** — não precisa instalar Pillow, ffmpeg nem nada além do Python 3.9+.

## Como a data é descoberta

Para cada arquivo, a data é escolhida na seguinte ordem de prioridade:

1. **EXIF** `DateTimeOriginal` (fotos JPEG/TIFF e muitos formatos RAW);
2. **Metadados do vídeo** — a box `mvhd` de contêineres MP4/MOV/M4V/3GP;
3. **Data de modificação do arquivo** (fallback sempre disponível).

A coluna `[origem]` na saída indica qual fonte foi usada em cada arquivo.

## Instalação

Não é obrigatório instalar — dá para rodar direto do diretório do projeto:

```bash
python3 -m galerymanager --help
```

Para instalar o comando `galerymanager` no sistema:

```bash
pip install .
```

## Uso

Sempre comece com `--dry-run` para revisar o plano **sem alterar nada**:

```bash
python3 -m galerymanager ~/Fotos -o ~/Galeria --dry-run
```

Aplicando de verdade (o padrão é **copiar**, preservando as origens):

```bash
python3 -m galerymanager ~/Fotos ~/Downloads -o ~/Galeria
```

Movendo os arquivos em vez de copiar:

```bash
python3 -m galerymanager ~/Camera -o ~/Galeria --move
```

### Opções

| Opção | Descrição |
|-------|-----------|
| `sources...` | Uma ou mais pastas (ou arquivos) de origem. |
| `-o, --output` | Pasta de destino da galeria organizada (obrigatório). |
| `--dry-run` | Apenas simula e mostra o plano, sem tocar em arquivos. |
| `--move` | Move os arquivos em vez de copiar. |
| `--pattern` | Padrão `strftime` das subpastas de data (padrão: `%Y/%Y-%m`). |
| `--no-recursive` | Não descer em subpastas das origens. |
| `--include-other` | Também organizar arquivos que não são mídia (pasta `Outros`). |
| `--on-duplicate` | `rename` (padrão), `skip` ou `overwrite`. |
| `-q, --quiet` | Mostrar só o resumo. |

### Estruturas de data personalizadas

O `--pattern` aceita qualquer diretiva `strftime`, e `/` cria níveis de pasta:

```bash
# Imagens/2021/2021-07/20/praia.jpg
python3 -m galerymanager ~/Fotos -o ~/Galeria --pattern '%Y/%Y-%m/%d'

# Imagens/2021/Julho/praia.jpg
python3 -m galerymanager ~/Fotos -o ~/Galeria --pattern '%Y/%B'
```

## Tratamento de duplicatas

- Se o destino **já existe com conteúdo idêntico** (mesmo tamanho e hash
  SHA-256), o arquivo é **pulado** — nunca há cópia redundante.
- Se existe um arquivo **diferente** com o mesmo nome, a política padrão
  `rename` gera `arquivo_1.jpg`, `arquivo_2.jpg`, etc. Use `--on-duplicate skip`
  ou `--on-duplicate overwrite` para outro comportamento.
- Rodar duas vezes é seguro (idempotente): a segunda execução não duplica nada.

## Formatos reconhecidos

- **Imagens:** jpg, jpeg, png, gif, bmp, tif/tiff, webp, heic/heif, avif,
  svg, ico e RAW (arw, cr2, cr3, nef, orf, rw2, dng, raf, sr2, pef).
- **Vídeos:** mp4, m4v, mov, avi, mkv, wmv, flv, webm, mpg/mpeg, 3gp, mts,
  m2ts, ts, vob, ogv, mxf.

## Usando como biblioteca

```python
from pathlib import Path
from galerymanager import Organizer

org = Organizer(Path("~/Galeria"), move=False)
report = org.run([Path("~/Fotos")], dry_run=False)

print(f"Imagens: {report.by_kind()}")
for move in report.moves:
    print(move.source, "->", move.dest)
```

## Testes

```bash
python3 -m unittest discover -s tests -v
```

## Licença

MIT.
