import os
import fitz
import pytesseract
import cv2
import numpy as np
from pdf2image import convert_from_path


# ============================================================
# 🔧 PREPROCESSAMENTO
# ============================================================
def preprocessar_imagem(img):
    img_np = np.array(img)

    if len(img_np.shape) == 3:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    # 🔥 melhora contraste
    gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)

    # 🔥 binarização leve
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    return thresh


# ============================================================
# 🚀 OCR PRINCIPAL
# ============================================================
def extrair_texto_folha(caminho_pdf: str) -> str:

    if not os.path.exists(caminho_pdf):
        print("❌ Arquivo não encontrado")
        return ""

    texto = []

    # =========================
    # 1. TEXTO NATIVO (PRIORIDADE)
    # =========================
    try:
        with fitz.open(caminho_pdf) as doc:
            for i, pagina in enumerate(doc):
                print(f"📄 [FOLHA] Lendo página {i+1} (nativo)...")
                texto.append(pagina.get_text())

        texto_final = "\n".join(texto)

        if len(texto_final.strip()) > 200:
            print("✅ Texto nativo suficiente")
            return texto_final

    except Exception as e:
        print("⚠️ Erro texto nativo:", e)

    # =========================
    # 2. OCR (IMAGEM)
    # =========================
    print("🟡 Usando OCR...")

    try:
        imagens = convert_from_path(caminho_pdf, dpi=300)

        textos_ocr = []

        for i, img in enumerate(imagens):
            print(f"📄 [FOLHA] OCR página {i+1}...")

            img_proc = preprocessar_imagem(img)

            texto_ocr = pytesseract.image_to_string(
                img_proc,
                config='--oem 3 --psm 6 -l por'
            )

            textos_ocr.append(texto_ocr)

        texto_final = "\n".join(textos_ocr)

        print("✅ OCR finalizado")

        return texto_final

    except Exception as e:
        print("❌ Erro OCR:", e)
        return ""