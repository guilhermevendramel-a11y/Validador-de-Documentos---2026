import re
from typing import Dict

import cv2

from services.cartao_ponto_layout_parser import renderizar_pagina_pdf
from utils.tesseract_config import pytesseract


_MESES = {
    "JAN": "01",
    "FEV": "02",
    "MAR": "03",
    "ABR": "04",
    "MAI": "05",
    "JUN": "06",
    "JUL": "07",
    "AGO": "08",
    "SET": "09",
    "OUT": "10",
    "NOV": "11",
    "DEZ": "12",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().upper()


def eh_modelo_ordem(texto: str) -> bool:
    t = _norm(texto)
    return ("N ORDEM" in t or "Nº ORDEM" in t) and "EMPREGADOR" in t and "EMPREGADO" in t


def _preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 11
    )
    return bw


def _extrair_nome_de_texto(texto: str) -> str:
    t = str(texto or "")
    # ancora principal
    m = re.search(
        r"\bEMPREGADO\b\s*[:\-|.]?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç ]{6,120})",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        nome = re.split(
            r"\b(N[ºO]\s*REGISTRO|FUN[ÇC][AÃ]O|LOCAL DO TRABALHO|1[ºO]?\s*QUINZENA|M[EÊ]S|ANO)\b",
            m.group(1),
            flags=re.IGNORECASE,
        )[0]
        nome = re.sub(r"\s+", " ", nome).strip()
        if len(nome.split()) >= 2:
            return nome

    # fallback por linha após âncora
    linhas = [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines() if ln.strip()]
    for i, ln in enumerate(linhas):
        if "EMPREGADO" in _norm(ln):
            for j in range(i, min(i + 3, len(linhas))):
                cand = re.sub(r"^.*EMPREGADO\s*[:\-|.]?\s*", "", linhas[j], flags=re.IGNORECASE)
                cand = re.split(
                    r"\b(N[ºO]\s*REGISTRO|FUN[ÇC][AÃ]O|LOCAL DO TRABALHO|QUINZENA|M[EÊ]S|ANO)\b",
                    cand,
                    flags=re.IGNORECASE,
                )[0].strip()
                if len(cand.split()) >= 2 and not re.search(r"\d", cand):
                    return cand
    return ""


def _extrair_competencia_de_texto(texto: str, competencia_esperada: str = "") -> str:
    t = _norm(texto)
    # MM/AAAA direto
    m = re.search(r"\b(0?[1-9]|1[0-2])[/-](20\d{2})\b", t)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    # MES + ANO
    mm = None
    for k, v in _MESES.items():
        if k in t:
            mm = v
            break
    ay = re.search(r"\b(20\d{2})\b", t)
    if mm and ay:
        return f"{mm}/{ay.group(1)}"
    return competencia_esperada or ""


def extrair_campos_modelo_ordem(caminho_arquivo: str, pagina: int, competencia_esperada: str = "") -> Dict:
    img = renderizar_pagina_pdf(caminho_arquivo, max(0, int(pagina) - 1), dpi=450)
    if img is None:
        return {"nome": "", "competencia": competencia_esperada or "", "confianca": 0.0, "origem": "modelo_ordem"}

    h, w = img.shape[:2]
    topo = img[0 : int(h * 0.35), 0:w]
    proc = _preprocess(topo)

    txt6 = pytesseract.image_to_string(proc, lang="por", config="--oem 1 --psm 6")
    txt11 = pytesseract.image_to_string(proc, lang="por", config="--oem 1 --psm 11")
    texto = f"{txt6}\n{txt11}"

    nome = _extrair_nome_de_texto(texto)
    competencia = _extrair_competencia_de_texto(texto, competencia_esperada=competencia_esperada)
    conf = 0.9 if nome else 0.0
    return {
        "nome": nome,
        "competencia": competencia,
        "confianca": conf,
        "origem": "modelo_ordem",
    }
