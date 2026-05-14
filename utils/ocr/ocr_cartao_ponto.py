import os
import re
import fitz
import cv2
import numpy as np
from pdf2image import convert_from_path
from utils.tesseract_config import pytesseract as configured_tesseract


# ==========================================================
# 🔥 PREPROCESSAMENTO PROFISSIONAL
# ==========================================================
def preprocessar_imagem(img):
    img_np = np.array(img)

    if len(img_np.shape) == 3:
        img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    # 🔥 1. contraste adaptativo (melhora MUITO OCR)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # 🔥 2. remove ruído leve
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # 🔥 3. binarização adaptativa (melhor que threshold fixo)
    gray = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2
    )

    return gray


def gerar_variantes_ocr(img):
    img_np = np.array(img)

    if len(img_np.shape) == 3:
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_np

    variantes = []

    # 1. Escala de cinza ampliada, boa para PDFs escaneados pequenos.
    escala = cv2.resize(gray, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
    variantes.append(escala)

    # 2. CLAHE + threshold adaptativo, bom para fundo acinzentado.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(escala)
    adaptive = cv2.adaptiveThreshold(
        cv2.GaussianBlur(clahe, (3, 3), 0),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    variantes.append(adaptive)

    # 3. Otsu, costuma preservar melhor tabelas e numeros de ponto.
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variantes.append(otsu)

    return variantes


def pontuar_texto(texto):
    if not texto:
        return 0

    texto_upper = texto.upper()
    score = len(texto.strip())

    palavras_chave = [
        "PONTO",
        "HORARIO",
        "HORÁRIO",
        "ENTRADA",
        "SAIDA",
        "SAÍDA",
        "EMPREGADO",
        "FUNCIONARIO",
        "FUNCIONÁRIO",
        "COMPETENCIA",
        "COMPETÊNCIA",
    ]

    score += sum(150 for palavra in palavras_chave if palavra in texto_upper)
    score += len(re.findall(r"\b\d{1,2}:\d{2}\b", texto)) * 30
    score += len(re.findall(r"\b\d{2}/\d{4}\b", texto)) * 60
    return score


def extrair_texto_tesseract_melhor(img):
    configs = [
        "--oem 3 --psm 6 -c preserve_interword_spaces=1",
        "--oem 3 --psm 4 -c preserve_interword_spaces=1",
    ]
    idiomas = ["por+eng", "por"]
    melhor_texto = ""
    melhor_score = 0
    score_suficiente = 1200

    for variante in gerar_variantes_ocr(img):
        for idioma in idiomas:
            for config in configs:
                try:
                    texto = configured_tesseract.image_to_string(
                        variante,
                        lang=idioma,
                        config=config,
                        timeout=12,
                    )
                except Exception as e:
                    print(f"[PONTO] Falha Tesseract lang={idioma} config={config}: {e}")
                    continue

                score = pontuar_texto(texto)
                if score > melhor_score:
                    melhor_score = score
                    melhor_texto = texto
                if melhor_score >= score_suficiente:
                    return melhor_texto

    return melhor_texto


def renderizar_pdf(caminho_pdf, dpi=220):
    try:
        return convert_from_path(caminho_pdf, dpi=dpi)
    except Exception as e:
        print(f"[PONTO] Poppler/pdf2image falhou: {e}. Usando PyMuPDF.")

    imagens = []
    zoom = dpi / 72

    try:
        with fitz.open(caminho_pdf) as doc:
            for pagina in doc:
                pix = pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                if pix.n == 4:
                    arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
                imagens.append(arr)
    except Exception as e:
        print(f"[PONTO] Erro ao renderizar com PyMuPDF: {e}")

    return imagens


# ==========================================================
# 🔥 VALIDAÇÃO DE TEXTO INTELIGENTE
# ==========================================================
def texto_valido(texto):
    if not texto:
        return False

    texto = texto.strip()

    # menos rígido (🔥 importante)
    if len(texto) < 50:
        return False

    if texto.count("\n") < 3:
        return False

    letras = sum(c.isalpha() for c in texto)

    if letras < 30:
        return False

    return True


# ==========================================================
# 🚀 EXTRAÇÃO PRINCIPAL
# ==========================================================
def extrair_paginas_cartao_ponto(caminho_pdf: str):

    if not os.path.exists(caminho_pdf):
        return []

    paginas = []

    # =========================================
    # 1. TEXTO NATIVO (COM VALIDAÇÃO)
    # =========================================
    try:
        with fitz.open(caminho_pdf) as doc:
            for i, pagina in enumerate(doc):
                print(f"📄 [PONTO] Lendo página {i+1} (nativo)...")

                conteudo = pagina.get_text()

                paginas.append({
                    "pagina": i + 1,
                    "texto": conteudo
                })

        # 🔥 usa nativo só se for confiável
        if any(texto_valido(p["texto"]) for p in paginas):
            print("✅ [PONTO] Texto nativo confiável")
            return paginas
        else:
            print("⚠️ [PONTO] Texto nativo ruim → usando OCR")

    except Exception as e:
        print(f"⚠️ [PONTO] Erro leitura nativa: {e}")

    # =========================================
    # 2. OCR (ROBUSTO)
    # =========================================
    print("🟡 [PONTO] Usando OCR...")

    try:
        imagens = renderizar_pdf(caminho_pdf, dpi=220)

        paginas = []

        for i, img in enumerate(imagens):
            print(f"📄 [PONTO] OCR página {i+1}...")

            texto = extrair_texto_tesseract_melhor(img)

            paginas.append({
                "pagina": i + 1,
                "texto": texto
            })

        print("✅ OCR concluído")

        return paginas

    except Exception as e:
        print(f"❌ [PONTO] Erro OCR: {e}")
        return []
