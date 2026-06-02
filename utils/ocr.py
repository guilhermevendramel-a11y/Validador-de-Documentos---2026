import os
import fitz
import pytesseract
import cv2
import numpy as np
import re
from pdf2image import convert_from_path
import utils.tesseract_config as tesseract_config

# Garante que o cmd configurado em utils.tesseract_config prevaleca
if getattr(tesseract_config, "tesseract_cmd", None):
    pytesseract.pytesseract.tesseract_cmd = tesseract_config.tesseract_cmd


# =========================================================
# 🔥 CORREÇÃO DE ROTAÇÃO (CRÍTICO PARA FGTS)
# =========================================================
def corrigir_rotacao(img):
    try:
        img_np = np.array(img)

        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_np

        coords = np.column_stack(np.where(gray > 0))

        if len(coords) == 0:
            return img_np

        angle = cv2.minAreaRect(coords)[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        (h, w) = img_np.shape[:2]
        center = (w // 2, h // 2)

        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img_np,
            M,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

        return rotated

    except:
        return img


# =========================================================
# 🔥 PRÉ-PROCESSAMENTO PESADO (FGTS MODE)
# =========================================================
def preprocessar_imagem(img):
    img_np = np.array(img)

    if len(img_np.shape) == 3:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    # 🔥 remove fundo/sombra
    bg = cv2.medianBlur(gray, 21)
    diff = cv2.absdiff(gray, bg)

    # 🔥 contraste forte
    norm = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)

    # 🔥 binarização inteligente
    thresh = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # 🔥 engrossa texto
    kernel = np.ones((1, 1), np.uint8)
    thresh = cv2.dilate(thresh, kernel, iterations=1)

    # 🔥 upscale
    h, w = thresh.shape
    thresh = cv2.resize(thresh, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    return thresh


def preprocessar_imagem_adaptativo(img):
    img_np = np.array(img)
    if len(img_np.shape) == 3:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    # Aumenta contraste local (bom para scans claros/acinzentados)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    # Binarizacao adaptativa para papeis com iluminacao desigual
    th = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        15
    )
    h, w = th.shape
    th = cv2.resize(th, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    return th


def score_texto(texto):
    if not texto:
        return 0
    letras = sum(c.isalpha() for c in texto)
    digitos = sum(c.isdigit() for c in texto)
    palavras = len(re.findall(r"\b[\wÀ-ÿ]{2,}\b", texto))
    return (letras * 2) + digitos + (palavras * 5)


def renderizar_paginas_fitz(caminho_pdf, max_paginas=10, zoom=3):
    imagens = []
    try:
        with fitz.open(caminho_pdf) as doc:
            limite = min(len(doc), max_paginas)
            for i in range(limite):
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                if pix.n == 4:
                    arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
                imagens.append(arr)
    except Exception:
        return []
    return imagens


# =========================================================
# 🔥 LIMPEZA DE TEXTO
# =========================================================
def limpar_texto(texto: str) -> str:
    if not texto:
        return ""

    texto = "".join(ch for ch in texto if ord(ch) >= 32 or ch in "\n\r")

    linhas_limpas = []
    padroes_lixo = [
        r'ICCBased', r'width', r'height', r'bpc',
        r'sRGB', r'DeviceRGB'
    ]

    for linha in texto.split('\n'):
        if not any(re.search(p, linha, re.IGNORECASE) for p in padroes_lixo):
            linhas_limpas.append(linha)

    return "\n".join(linhas_limpas).strip()


# =========================================================
# 🔥 DETECTA PDF RUIM (IMAGEM)
# =========================================================
def eh_pdf_imagem(texto):
    if not texto:
        return True

    if "<image:" in texto:
        return True

    if len(texto.strip()) < 300:
        return True

    palavras_chave = ["FGTS", "TRABALHADOR", "EMPRESA"]
    if not any(p in texto.upper() for p in palavras_chave):
        return True

    return False


# =========================================================
# 🔥 QUALIDADE DO OCR
# =========================================================
def texto_esta_ruim(texto):
    if not texto:
        return True

    letras = sum(c.isalpha() for c in texto)
    total = len(texto)

    if total == 0:
        return True

    ratio = letras / total
    return ratio < 0.3


# =========================================================
# 🚀 EXTRAÇÃO PRINCIPAL
# =========================================================
def extrair_texto_pdf(caminho_pdf: str) -> str:

    if not os.path.exists(caminho_pdf):
        return ""

    # =========================================
    # 1. TENTATIVA NATIVA
    # =========================================
    try:
        texto_nativo = []

        with fitz.open(caminho_pdf) as doc:
            for i, pagina in enumerate(doc):
                print(f"📄 [OCR] Lendo página {i+1} (modo estruturado)...")

                texto_pagina = pagina.get_text()

                print(f"\n🧾 TEXTO PÁGINA {i+1}:\n{texto_pagina[:300]}\n")

                texto_nativo.append(texto_pagina)

        texto_final = "\n".join(texto_nativo)

        if not eh_pdf_imagem(texto_final):
            print("✅ [OCR] Texto estruturado detectado (SEM OCR)")
            return limpar_texto(texto_final)
        else:
            print("⚠️ PDF detectado como imagem → Forçando OCR...")

    except Exception as e:
        print(f"⚠️ Falha no OCR nativo: {e}")

    # =========================================
    # 2. OCR AVANÇADO
    # =========================================
    print("🟡 [OCR] Iniciando Tesseract (Modo Avançado)...")

    try:
        try:
            imagens = convert_from_path(
                caminho_pdf,
                dpi=500,
                first_page=1,
                last_page=10
            )
        except Exception:
            print("⚠️ Poppler indisponivel no ambiente. Usando fallback via PyMuPDF.")
            imagens = renderizar_paginas_fitz(caminho_pdf, max_paginas=10, zoom=3)
            # Converte arrays numpy para formato esperado das funcoes de preprocessamento
            imagens = [cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if len(img.shape) == 3 else img for img in imagens]

        texto_ocr = []
        psm_opcoes = [6, 11, 4]

        for i, img in enumerate(imagens):
            print(f"📄 [OCR] Processando página {i+1}...")
            img_np = np.array(img)
            if len(img_np.shape) == 3 and img_np.shape[2] == 4:
                img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2RGB)

            variantes = [
                ("pesado", corrigir_rotacao(preprocessar_imagem(img_np))),
                ("adaptativo", corrigir_rotacao(preprocessar_imagem_adaptativo(img_np))),
                ("cinza_simples", cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY) if len(img_np.shape) == 3 else img_np),
            ]

            melhor_texto = ""
            melhor_score = -1

            for nome_variante, img_proc in variantes:
                for psm in psm_opcoes:
                    custom_config = f'--oem 3 --psm {psm} -l por'
                    try:
                        texto_candidato = pytesseract.image_to_string(
                            img_proc,
                            config=custom_config
                        )
                    except Exception:
                        texto_candidato = ""

                    score = score_texto(texto_candidato)
                    if score > melhor_score:
                        melhor_score = score
                        melhor_texto = texto_candidato

            print(f"\n🧾 TEXTO PÁGINA {i+1} (melhor score={melhor_score}):\n{melhor_texto[:400]}\n")
            texto_ocr.append(melhor_texto)

        completo = "\n".join(texto_ocr)

        print("\n🧾 TEXTO FINAL PROCESSADO:")
        print(completo[:1000])
        print("----------------------\n")

        if texto_esta_ruim(completo):
            print("⚠️ OCR com baixa qualidade detectado")

        return limpar_texto(completo)

    except Exception as e:
        print(f"❌ Erro OCR: {e}")
        return ""


# =========================================================
# 🔄 COMPATIBILIDADE
# =========================================================
extrair_texto_pdf_folha = extrair_texto_pdf
extrair_texto_pdf_inteligente = extrair_texto_pdf
