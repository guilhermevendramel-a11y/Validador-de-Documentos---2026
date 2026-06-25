import re
import unicodedata

import cv2
import fitz
import numpy as np
import pytesseract
from PIL import Image

import utils.tesseract_config as tesseract_config
from utils.ocr import extrair_documento_inteligente

if getattr(tesseract_config, "tesseract_cmd", None):
    pytesseract.pytesseract.tesseract_cmd = tesseract_config.tesseract_cmd


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).upper()


def _normalizar_valor(texto):
    if not texto:
        return 0.0
    txt = str(texto).strip().replace("R$", "").replace("r$", "").replace(" ", "")
    txt = re.sub(r"[^\d,\.-]", "", txt)
    if txt in {"", "-", ".", ","}:
        return 0.0
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif "," in txt:
        txt = txt.replace(",", ".")
    try:
        return round(float(txt), 2)
    except Exception:
        return 0.0


def _compactar(texto):
    return re.sub(r"[^A-Z0-9]+", "", _sem_acento(texto))


def _linha_indica_valor_liquido(texto):
    compact = _compactar(texto)
    if not compact:
        return False
    if "TOTALDEVENCIMENTOS" in compact or "VENCIMENTOS" in compact and "LIQUID" not in compact:
        return False
    rotulos_validos = (
        "VALORLIQUIDO",
        "VALORLQUIDO",
        "LIQUIDOARECEBER",
        "LQUIDOARECEBER",
        "TOTALLIQUIDO",
        "TOTALLQUIDO",
        "VALORARECEBER",
    )
    return any(rotulo in compact for rotulo in rotulos_validos)


def _extrair_valor_linha_ou_vizinhas(linhas, idx):
    trechos = [linhas[idx]["text"], *[l["text"] for l in linhas[idx + 1: idx + 4]]]
    for trecho in trechos:
        for match in re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", trecho):
            valor = _normalizar_valor(match)
            if valor > 0:
                return valor
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
        print(f"[HOLERITE] render direto falhou: {exc}")
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
        print(f"[HOLERITE] image_to_data falhou: {exc}")
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


def _ocr_texto_recorte(imagem, psm="6"):
    try:
        return pytesseract.image_to_string(imagem, lang="por", config=f"--oem 3 --psm {psm}")
    except Exception as exc:
        print(f"[HOLERITE] OCR recorte falhou: {exc}")
        return ""


def extrair_valor_liquido_holerite(path):
    imagem = _render_primeira_pagina(path, dpi=300)
    if imagem is None:
        return 0.0

    gray = cv2.cvtColor(np.array(imagem), cv2.COLOR_RGB2GRAY)
    altura = gray.shape[0]
    candidatos = []

    for psm in ("11", "4", "6"):
        linhas = _agrupar_linhas_ocr(gray, psm=psm)
        if not linhas:
            continue

        for idx, linha in enumerate(linhas):
            if linha["top"] < altura * 0.45:
                continue
            if not _linha_indica_valor_liquido(linha["text"]):
                continue
            valor = _extrair_valor_linha_ou_vizinhas(linhas, idx)
            if valor > 0:
                candidatos.append((linha["top"], idx, valor))

    if candidatos:
        candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidatos[0][2]

    altura, largura = gray.shape[:2]
    recortes = [
        gray[int(altura * 0.55):altura, int(largura * 0.40):largura],
        gray[int(altura * 0.65):altura, int(largura * 0.35):largura],
        gray[int(altura * 0.70):altura, :],
    ]
    for recorte in recortes:
        if recorte.size == 0:
            continue
        for psm in ("6", "11", "4"):
            texto_recorte = _ocr_texto_recorte(recorte, psm=psm)
            linhas_recorte = [linha.strip() for linha in str(texto_recorte or "").splitlines() if linha.strip()]
            for idx, linha in enumerate(linhas_recorte):
                if not _linha_indica_valor_liquido(linha):
                    continue
                for trecho in [linha, *linhas_recorte[idx + 1: idx + 4]]:
                    for match in re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", trecho):
                        valor = _normalizar_valor(match)
                        if valor > 0:
                            return valor

    texto = extrair_documento_inteligente(path, tipo_documento="holerite", usar_ocr=True).get("texto", "")
    linhas_texto = [linha.strip() for linha in str(texto or "").splitlines() if linha.strip()]
    for idx, linha in enumerate(linhas_texto):
        if not _linha_indica_valor_liquido(linha):
            continue
        for trecho in [linha, *linhas_texto[idx + 1: idx + 4]]:
            for match in re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", trecho):
                valor = _normalizar_valor(match)
                if valor > 0:
                    return valor

    return 0.0


def extrair_texto_holerite(path):
    return extrair_documento_inteligente(path, tipo_documento="holerite", usar_ocr=True).get("texto", "")
