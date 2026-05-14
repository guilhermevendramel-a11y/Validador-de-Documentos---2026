import argparse
import os
from pathlib import Path

import fitz


def iter_pdfs(input_path):
    path = Path(input_path)
    if path.is_file() and path.suffix.lower() == ".pdf":
        yield path
        return

    if path.is_dir():
        yield from sorted(path.rglob("*.pdf"))


def safe_stem(path):
    stem = path.stem
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in stem)


def export_pdf_pages(pdf_path, output_dir, dpi):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    created = []
    with fitz.open(pdf_path) as doc:
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        prefix = safe_stem(Path(pdf_path))

        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            out = output_dir / f"{prefix}_pagina_{index:03d}.jpg"
            pix.save(out)
            created.append(out)

    return created


def main():
    parser = argparse.ArgumentParser(
        description="Converte PDFs de cartao ponto em imagens JPG para anotacao no CVAT."
    )
    parser.add_argument("--input", required=True, help="PDF ou pasta com PDFs.")
    parser.add_argument(
        "--output",
        default="datasets/assinaturas_cvat/images",
        help="Pasta de saida das imagens.",
    )
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()

    pdfs = list(iter_pdfs(args.input))
    if not pdfs:
        raise SystemExit("Nenhum PDF encontrado.")

    total = 0
    for pdf in pdfs:
        created = export_pdf_pages(pdf, args.output, args.dpi)
        total += len(created)
        print(f"{pdf}: {len(created)} pagina(s)")

    print(f"Concluido: {total} imagem(ns) em {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
