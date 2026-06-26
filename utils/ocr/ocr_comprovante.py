import re
import pytesseract
import cv2
import fitz
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
import unicodedata

from utils.ocr import extrair_documento_inteligente


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
        print(f"[COMPROVANTE] Leitura nativa falhou: {exc}")
        return ""


def _carregar_imagens(path):
    if str(path).lower().endswith(".pdf"):
        try:
            return convert_from_path(path, dpi=300)
        except Exception as exc:
            print(f"[COMPROVANTE] pdf2image indisponivel, usando fitz: {exc}")
            imagens = []
            zoom = 300 / 72.0
            with fitz.open(path) as doc:
                for page in doc:
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    imagens.append(img)
            return imagens

    return [Image.open(path)]


def _ocr_imagem(gray):
    try:
        return pytesseract.image_to_string(gray, lang="por", config="--oem 3 --psm 6")
    except Exception as exc:
        print(f"[COMPROVANTE] OCR em portugues falhou, tentando padrao: {exc}")
        return pytesseract.image_to_string(gray, config="--oem 3 --psm 6")


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).upper()


def _normalizar_valor(texto):
    if not texto:
        return 0.0
    txt = str(texto).strip().replace("R$", "").replace("r$", "").replace(" ", "")
    txt = txt.replace(",", ".") if "," in txt and "." not in txt else txt
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    txt = "".join(c for c in txt if c.isdigit() or c in {".", ","})
    if not txt:
        return 0.0
    if txt.count(",") > 0 and txt.count(".") == 0:
        txt = txt.replace(",", ".")
    elif txt.count(",") > 0 and txt.count(".") > 0:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return round(float(txt), 2)
    except Exception:
        return 0.0


def _render_primeira_pagina(path, dpi=300):
    if not str(path).lower().endswith(".pdf"):
        return None
    try:
        zoom = dpi / 72.0
        with fitz.open(path) as doc:
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    except Exception as exc:
        print(f"[COMPROVANTE] render direto falhou: {exc}")
        return None


def _agrupar_linhas_ocr(imagem, psm="11"):
    try:
        dados = pytesseract.image_to_data(
            imagem,
            lang="por",
            config=f"--oem 3 --psm {psm}",
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
        print(f"[COMPROVANTE] image_to_data falhou: {exc}")
        return []

    linhas = {}
    total = len(dados.get("text", []))
    for i in range(total):
        texto = str(dados["text"][i] or "").strip()
        if not texto:
            continue
        try:
            conf = float(dados["conf"][i])
        except Exception:
            conf = -1.0
        if conf < 0:
            continue
        key = (int(dados["block_num"][i]), int(dados["par_num"][i]), int(dados["line_num"][i]))
        grp = linhas.setdefault(
            key,
            {
                "words": [],
                "top": int(dados["top"][i]),
                "left": int(dados["left"][i]),
            },
        )
        grp["top"] = min(grp["top"], int(dados["top"][i]))
        grp["left"] = min(grp["left"], int(dados["left"][i]))
        grp["words"].append((int(dados["left"][i]), texto, conf))

    saida = []
    for grp in linhas.values():
        palavras = sorted(grp["words"], key=lambda item: item[0])
        texto_linha = " ".join(token for _, token, _ in palavras).strip()
        if texto_linha:
            saida.append(
                {
                    "top": grp["top"],
                    "left": grp["left"],
                    "text": texto_linha,
                    "tokens": palavras,
                }
            )

    saida.sort(key=lambda item: (item["top"], item["left"]))
    return saida


def extrair_valor_comprovante_arquivo(path, texto=None):
    imagens = []
    try:
        imagens = _carregar_imagens(path)
    except Exception as exc:
        print(f"[COMPROVANTE] Falha ao carregar imagens: {exc}")
        imagens = []

    candidatos = []
    for pagina_idx, imagem in enumerate(imagens):
        if imagem is None:
            continue
        arr = np.array(imagem)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # Mantem o documento inteiro, mas procura primeiro a regiao de transacao.
        for psm in ("11", "6", "4"):
            linhas = _agrupar_linhas_ocr(gray, psm=psm)
            if not linhas:
                continue

            for idx, linha in enumerate(linhas):
                linha_norm = _sem_acento(linha["text"])
                if not any(
                    termo in linha_norm
                    for termo in ("VALOR", "TRANSACAO", "TRANSFERENCIA", "PAGAMENTO", "PIX", "DADOS DA TRANSACAO", "FAVORECIDO", "BENEFICIARIO")
                ):
                    continue

                janela = linhas[max(0, idx - 2): min(len(linhas), idx + 4)]
                for janela_linha in janela:
                    texto_linha = janela_linha["text"]
                    for match in re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", texto_linha):
                        valor = _normalizar_valor(match)
                        if valor <= 0:
                            continue
                        score = 0
                        if "VALOR" in linha_norm:
                            score += 55
                        if "TRANSACAO" in linha_norm or "TRANSFERENCIA" in linha_norm:
                            score += 40
                        if "PIX" in linha_norm or "PAGAMENTO" in linha_norm:
                            score += 20
                        if "FAVORECIDO" in linha_norm or "BENEFICIARIO" in linha_norm:
                            score += 15
                        if "." in match:
                            score += 10
                        if "R$" in texto_linha.upper():
                            score += 10
                        score += min(20, len(match))
                        score += max(0, 5 - pagina_idx)
                        candidatos.append((score, valor))

    if candidatos:
        candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
        melhor = candidatos[0][1]
        if melhor > 0:
            return melhor

    if texto:
        texto_norm = _sem_acento(texto)
        linhas_texto = [linha.strip() for linha in texto_norm.splitlines() if linha.strip()]
        for idx, linha in enumerate(linhas_texto):
            linha_norm = _sem_acento(linha)
            if not any(
                termo in linha_norm
                for termo in ("VALOR", "TRANSACAO", "TRANSFERENCIA", "PAGAMENTO", "PIX", "DADOS DA TRANSACAO", "FAVORECIDO", "BENEFICIARIO")
            ):
                continue
            janela = linhas_texto[max(0, idx - 1): min(len(linhas_texto), idx + 4)]
            for janela_linha in janela:
                for match in re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", janela_linha):
                    valor = _normalizar_valor(match)
                    if valor > 0:
                        return valor
        for match in re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", texto_norm):
            valor = _normalizar_valor(match)
            if valor > 0:
                return valor

    return 0.0


def extrair_texto_comprovante(path):
    try:
        resultado = extrair_documento_inteligente(path, usar_ocr=True)
        texto = (resultado or {}).get("texto", "")
        if texto and len(texto.strip()) > 50:
            return texto
    except Exception as exc:
        print(f"[COMPROVANTE] OCR inteligente falhou, usando fallback manual: {exc}")

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
