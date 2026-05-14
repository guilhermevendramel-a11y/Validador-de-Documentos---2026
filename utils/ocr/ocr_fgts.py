import os
import fitz
import pytesseract
import cv2
import numpy as np
from pdf2image import convert_from_path


def preprocessar_imagem_fgts(img):
    img_np = np.array(img)

    if len(img_np.shape) == 3:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    # remove fundo
    bg = cv2.medianBlur(gray, 21)
    diff = cv2.absdiff(gray, bg)

    # aumenta contraste
    norm = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)

    # binariza forte
    thresh = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # dilata
    kernel = np.ones((1, 1), np.uint8)
    thresh = cv2.dilate(thresh, kernel, iterations=1)

    # upscale
    h, w = thresh.shape
    thresh = cv2.resize(thresh, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    return thresh


# 🔥 MELHOR VALIDAÇÃO
def texto_invalido(texto):
    if not texto:
        return True

    texto_up = texto.upper()

    palavras_boas = [
        "RELAÇÃO DE TRABALHADORES",
        "NOME TRABALHADOR",
        "TOMADOR",
        "GUIA DO FGTS DIGITAL",
        "VALOR A RECOLHER",
        "TOTAL DA GUIA",
        "COMPROVANTE DE PAGAMENTO"
    ]

    return not any(p in texto_up for p in palavras_boas)


# 🔥 FUNÇÃO PRINCIPAL COM NÍVEL SÊNIOR
def extrair_texto_fgts(caminho_pdf: str, forcar_ocr=False) -> str:
    if not os.path.exists(caminho_pdf):
        return ""

    # =========================================
    # 1. TEXTO NATIVO
    # =========================================
    try:
        texto = []

        with fitz.open(caminho_pdf) as doc:
            for i, pagina in enumerate(doc):
                print(f"📄 [FGTS] Lendo página {i+1}...")

                conteudo = pagina.get_text()
                texto.append(conteudo)

        texto_final = "\n".join(texto)

        # 🔥 AQUI ESTÁ O PONTO CRÍTICO
        if not forcar_ocr and not texto_invalido(texto_final):
            print("✅ [FGTS] Texto nativo OK")
            return texto_final

        print("⚠️ [FGTS] Forçando OCR...")

    except Exception as e:
        print(f"⚠️ [FGTS] Erro leitura nativa: {e}")

    # =========================================
    # 2. OCR FORTE
    # =========================================
    print("🟡 [FGTS] OCR avançado...")

    try:
        imagens = convert_from_path(
            caminho_pdf,
            dpi=400
        )

        textos = []

        for i, img in enumerate(imagens):
            print(f"📄 [FGTS] OCR página {i+1}...")

            img_proc = preprocessar_imagem_fgts(img)

            texto = pytesseract.image_to_string(
                img_proc,
                config='--oem 3 --psm 4 -l por'
            )

            textos.append(texto)

        resultado = "\n".join(textos)

        print("\n🧾 [FGTS] TEXTO FINAL (OCR):")
        print(resultado[:800])

        return resultado

    except Exception as e:
        print(f"❌ [FGTS] Erro OCR: {e}")
        return ""
