import os

import fitz
import pytesseract
from pdf2image import convert_from_path


def extrair_texto_pdf_inteligente(caminho_pdf):
    if not caminho_pdf or not os.path.exists(caminho_pdf):
        return ""

    textos = []
    try:
        with fitz.open(caminho_pdf) as doc:
            for pagina in doc:
                texto = (pagina.get_text() or "").strip()
                textos.append(texto)
        texto_final = "\n\f\n".join(textos).strip()
        if len(texto_final) > 80:
            return texto_final
    except Exception:
        pass

    try:
        imagens = convert_from_path(caminho_pdf, dpi=300)
        ocr = []
        for img in imagens:
            ocr.append(pytesseract.image_to_string(img, lang="por"))
        return "\n\f\n".join(ocr).strip()
    except Exception:
        return ""
