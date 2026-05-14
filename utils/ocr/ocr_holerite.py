import pytesseract
import cv2
import fitz
import numpy as np
from pdf2image import convert_from_path
from PIL import Image


def _texto_nativo_pdf(path):
    if not str(path).lower().endswith(".pdf"):
        return ""

    try:
        textos = []
        with fitz.open(path) as doc:
            for pagina in doc:
                textos.append((pagina.get_text() or "").strip())
        return "\n\f\n".join(textos).strip()
    except Exception as exc:
        print(f"[HOLERITE] Leitura nativa falhou: {exc}")
        return ""


def _carregar_imagens(path):
    if str(path).lower().endswith(".pdf"):
        return convert_from_path(path, dpi=300)

    return [Image.open(path)]


def _ocr_imagem(gray):
    try:
        return pytesseract.image_to_string(gray, lang="por", config="--oem 3 --psm 6")
    except Exception as exc:
        print(f"[HOLERITE] OCR em portugues falhou, tentando padrao: {exc}")
        return pytesseract.image_to_string(gray, config="--oem 3 --psm 6")


def extrair_texto_holerite(path):
    texto_nativo = _texto_nativo_pdf(path)
    if len(texto_nativo) > 50:
        return texto_nativo

    imagens = _carregar_imagens(path)
    textos = []

    for img in imagens:
        img_np = np.array(img)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        textos.append(_ocr_imagem(gray))

    return "\n\f\n".join(textos)
