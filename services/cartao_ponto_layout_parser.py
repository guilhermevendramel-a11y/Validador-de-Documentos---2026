import re
import json
import os
import time
import hashlib
import unicodedata
from datetime import datetime
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import cv2
import fitz
import numpy as np
import pytesseract
import utils.tesseract_config  # noqa: F401
from rapidfuzz import fuzz

from utils.ocr_doctr import doctr_disponivel, executar_doctr_imagem
from utils.ocr_easy import easyocr_disponivel, executar_easyocr_imagem
from utils.ocr_paddle import executar_paddleocr_imagem, executar_paddleocr_regiao, paddle_disponivel
from utils.ocr_surya import executar_surya_ocr_imagem, surya_disponivel
from utils.signature_detection import pontuar_rubrica
from utils.yolo_signature_detection import caminhos_modelos_yolo


FECHAMENTO_TOKENS = [
    "ASSINATURA DO EMPREGADO",
    "ASSINATURA",
    "RUBRICA",
    "RECEBI O SALDO",
    "RECONHECO A EXATIDAO",
    "2 QUINZENA",
    "2A QUINZENA",
]

PALAVRAS_CHAVE_CARTAO = [
    "NOME", "COLABORADOR", "FUNCIONARIO", "FUNCIONÁRIO", "EMPREGADO",
    "FOLHA DE PONTO", "PERIODO", "PERÍODO", "ENTRADA", "SAIDA", "SAÍDA",
    "ASSINATURA", "LOG DE ASSINATURA", "ASSINADO EM",
]

RECORTE_CFG = {
    "topo": (0.0, 0.0, 1.0, 0.35),
    "faixa_nome": (0.0, 0.10, 0.75, 0.45),
    "cabecalho_esquerdo": (0.0, 0.0, 0.70, 0.30),
    "cabecalho_direito": (0.60, 0.0, 1.0, 0.30),
    "tabela": (0.0, 0.20, 1.0, 0.85),
    "coluna_assinatura": (0.70, 0.20, 1.0, 0.90),
    "rodape": (0.0, 0.75, 1.0, 1.0),
}

_YOLO_MODELS = None
CACHE_VERSION = "v4_topo_nome_estrito"


def _cache_dir():
    pasta = os.path.join(".cache", "cartao_ponto")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _cache_key(caminho_arquivo, pagina, dpi=200, tipo_recorte="pagina"):
    st = os.stat(caminho_arquivo)
    bruto = f"{CACHE_VERSION}|{os.path.abspath(caminho_arquivo)}|{pagina}|{st.st_size}|{st.st_mtime_ns}|{dpi}|{tipo_recorte}"
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _cache_load(chave, sufixo):
    path = os.path.join(_cache_dir(), f"{chave}_{sufixo}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_save(chave, sufixo, payload):
    path = os.path.join(_cache_dir(), f"{chave}_{sufixo}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


def _norm(texto):
    txt = unicodedata.normalize("NFKD", str(texto or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"\s+", " ", txt.upper())
    return txt.strip()


def _to_mm_aaaa(mes, ano):
    m = str(mes).zfill(2)
    a = str(ano)
    if len(a) == 2:
        a = f"20{a}"
    return f"{m}/{a}"


def _data_valida(dia, mes, ano):
    try:
        datetime(int(ano), int(mes), int(dia))
        return True
    except Exception:
        return False


def classificar_layout_cartao_ponto(texto_pagina: str, imagem_info=None) -> str:
    t = _norm(texto_pagina)
    if all(k in t for k in ["ASSINATURA DE:", "LOG DE ASSINATURA", "ASSINADO EM:"]):
        return "log_assinatura_digital"
    if all(k in t for k in ["DADOS DO COLABORADOR", "NOME", "FOLHA DE PONTO"]) and ("PERIODO" in t or "PERÍODO" in t):
        return "cartao_digital_texto_nativo"
    if all(k in t for k in ["FUNCION.", "CLIENTE", "PERIODO"]) and ("JORNADA" in t or "HORARIO" in t or "HORÁRIO" in t):
        return "manual_frente"
    if ("2 QUINZENA" in t or "2ª QUINZENA" in t or "2° QUINZENA" in t) and any(k in t for k in ["RECEBI O SALDO", "ASSINATURA DO EMPREGADO", "REGISTRO DE OCORRENCIAS", "REGISTRO DE OCORRÊNCIAS"]):
        return "manual_verso"
    if any(k in t for k in ["ASSINATURA DO EMPREGADO", "ASSINATURA DO FUNCIONARIO", "ASSINATURA DO FUNCIONÁRIO", "ASSINATURA/OBSERVACOES", "ASSINATURA/OBSERVAÇÕES"]):
        return "manual_assinatura_diaria"
    if len(t) < 90:
        return "imagem_escaneada_generica"
    return "desconhecido"


def extrair_nome_cartao_ponto_info(texto_pagina, nomes_esperados=None):
    t = str(texto_pagina or "")
    tn = _norm(t)
    nomes_esperados = nomes_esperados or []

    for nome in nomes_esperados:
        if _norm(nome) and _norm(nome) in tn:
            return {"nome": nome.title(), "confianca": 0.98, "origem": "nome_esperado", "ancora_usada": "lista_esperada"}

    stops = r"(FUNCAO|FUNÇÃO|CARGO|PERIODO|PERÍODO|JORNADA|HORARIO|HORÁRIO|CPF|CTPS|CNPJ|EMPRESA)"
    anchors = [
        (r"\bNOME DO EMPREGADO\s*[:\-]?\s*([^\n]{5,100})", "NOME DO EMPREGADO"),
        (r"\bNOME DO COLABORADOR\s*[:\-]?\s*([^\n]{5,100})", "NOME DO COLABORADOR"),
        (r"\bDADOS DO COLABORADOR\s*[:\-]?\s*([^\n]{5,100})", "DADOS DO COLABORADOR"),
        (r"\bFUNCION[\w\.º°]*\s*[:\-]\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{4,}?)\b(?:\s+FUN[CÇ][AÃ]O|$)", "FUNCIONARIO"),
        (r"\bFUNCION\.\s*[:\-]?\s*([^\n]{5,100})", "FUNCION."),
        (r"\bCOLABORADOR\s*[:\-]?\s*([^\n]{5,100})", "COLABORADOR"),
        (r"\bEMPREGADO\s*[:\-]?\s*([^\n]{5,100})", "EMPREGADO"),
        (r"\bTRABALHADOR\s*[:\-]?\s*([^\n]{5,100})", "TRABALHADOR"),
        (r"\bNOME\s*[:\-]?\s*([^\n]{5,100})", "NOME"),
    ]

    for pat, anc in anchors:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if not m:
            continue
        raw = re.split(stops, m.group(1), flags=re.IGNORECASE)[0]
        cand = re.sub(r"\s+", " ", raw).strip()
        cand_norm = _norm(cand)
        if len(cand.split()) < 2 or re.search(r"\d{3,}", cand):
            continue
        if any(b in cand_norm for b in ["REGISTRO DE OCORREN", "ASSINATURA DO EMPREGADO", "HORAS EXTRAS", "EMPREGADOR", "RAZAO SOCIAL"]):
            continue
        return {"nome": cand.title(), "confianca": 0.88, "origem": "ancora", "ancora_usada": anc}

    # Fallback tolerante: captura linhas em caixa alta com >=2 palavras, excluindo cabeçalhos comuns.
    linhas = [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines() if ln and ln.strip()]
    bloqueios = [
        "FOLHA DE PONTO", "ASSINATURA", "PERIODO", "PERÍODO", "JORNADA", "HORARIO", "HORÁRIO",
        "ENTRADA", "SAIDA", "SAÍDA", "REGISTRO", "OCORREN", "EMPRESA", "CNPJ", "CPF",
        "LTDA", "EIRELI", "S/A", "HORAS EXTRAS", "TOTAL DE HORAS", "IMP RENDA", "IMPOSTO RENDA", "IRRF", "PREV SOCIAL",
    ]
    for ln in linhas:
        ln_norm = _norm(ln)
        if any(b in ln_norm for b in bloqueios):
            continue
        if re.search(r"\d{3,}", ln):
            continue
        palavras = [p for p in re.split(r"\s+", ln) if p]
        if len(palavras) < 2:
            continue
        alpha_ratio = sum(ch.isalpha() for ch in ln) / max(1, len(ln))
        if alpha_ratio < 0.65:
            continue
        if len(ln) < 8 or len(ln) > 80:
            continue
        return {"nome": ln.title(), "confianca": 0.72, "origem": "fallback_linha", "ancora_usada": "linha_caixa_alta"}

    return {"nome": "", "confianca": 0.0, "origem": "heuristica", "ancora_usada": ""}


def extrair_nome_cartao_ponto(texto_pagina, nomes_esperados=None):
    return extrair_nome_cartao_ponto_info(texto_pagina, nomes_esperados=nomes_esperados).get("nome", "")


def extrair_competencia_cartao_ponto_info(texto_pagina):
    t = _norm(texto_pagina)
    avisos = []

    m = re.search(r"\b(0?[1-9]|1[0-2])[/-](\d{4})\b", t)
    if m:
        return {"competencia": _to_mm_aaaa(m.group(1), m.group(2)), "periodo_inicio": "", "periodo_fim": "", "origem": "competencia_numerica", "confianca": 0.95, "avisos": avisos}

    m = re.search(r"\b(0?[1-9]|1[0-2])[/-](\d{2})\b", t)
    if m:
        return {"competencia": _to_mm_aaaa(m.group(1), m.group(2)), "periodo_inicio": "", "periodo_fim": "", "origem": "competencia_numerica", "confianca": 0.9, "avisos": avisos}

    meses = {"JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "MARÇO": "03", "ABRIL": "04", "MAIO": "05", "JUNHO": "06", "JULHO": "07", "AGOSTO": "08", "SETEMBRO": "09", "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12", "JAN": "01"}
    for nome, num in meses.items():
        m = re.search(rf"\b{nome}\s*[/-]?\s*(\d{{4}})\b", t)
        if m:
            return {"competencia": _to_mm_aaaa(num, m.group(1)), "periodo_inicio": "", "periodo_fim": "", "origem": "competencia_textual", "confianca": 0.88, "avisos": avisos}

    datas_brutas = re.findall(r"\b([0-3]?\d)/(0[1-9]|1[0-2])/(\d{2,4})\b", t)
    datas = []
    for dd, mm, aa in datas_brutas:
        ano4 = str(aa).zfill(4)[-4:]
        if _data_valida(dd, mm, ano4):
            datas.append((dd, mm, ano4))
    if len(datas) >= 2:
        d1, m1, a1 = datas[0]
        d2, m2, a2 = datas[1]
        ini = f"{int(d1):02d}/{int(m1):02d}/{a1}"
        fim = f"{int(d2):02d}/{int(m2):02d}/{a2}"
        meses_periodo = [_to_mm_aaaa(mm, aa) for _dd, mm, aa in datas]
        comp = Counter(meses_periodo).most_common(1)[0][0]
        if len(set(meses_periodo)) > 1:
            avisos.append("Período cruza meses diferentes; competência por mês predominante.")
        else:
            avisos.append("Competência extraída por período.")
        return {"competencia": comp, "periodo_inicio": ini, "periodo_fim": fim, "origem": "periodo", "confianca": 0.9, "avisos": avisos}

    return {"competencia": "", "periodo_inicio": "", "periodo_fim": "", "origem": "nao_identificada", "confianca": 0.0, "avisos": avisos}


def extrair_competencia_cartao_ponto(texto_pagina):
    info = extrair_competencia_cartao_ponto_info(texto_pagina)
    return info["competencia"], info["avisos"]


def normalizar_horario_ocr(valor):
    original = str(valor or "")
    v = re.sub(r"[^\d]", "", original)
    if len(v) < 3:
        return "", False
    if len(v) == 3:
        v = f"0{v}"
    hh, mm = int(v[:2]), int(v[2:4])
    if hh in {72, 73, 76, 77}:
        hh -= 60
    if hh > 23 and hh >= 60:
        hh -= 60
    if hh > 23 or mm > 59:
        return "", False
    out = f"{hh:02d}:{mm:02d}"
    return out, out != original


def extrair_marcacoes_cartao_ponto(texto_pagina):
    t = str(texto_pagina or "")
    candidatos = re.findall(r"\b\d{1,2}[:\.\s]\d{2}\b", t)
    horarios = []
    corrigidos = []
    for c in candidatos:
        h, corr = normalizar_horario_ocr(c)
        if h:
            horarios.append(h)
            if corr:
                corrigidos.append({"original": c, "corrigido": h})
    horarios = sorted(set(horarios))
    qtd = len(horarios)
    # Marcação manual: linha com dia seguido de pelo menos 2 horários (ex.: "15 08:00 12:00")
    linhas = [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines() if ln and ln.strip()]
    linhas_marcacao_manual = 0
    for ln in linhas:
        if not re.search(r"^\s*\d{1,2}\b", ln):
            continue
        hs = re.findall(r"\b\d{1,2}[:\.\s]\d{2}\b", ln)
        if len(hs) >= 2:
            linhas_marcacao_manual += 1
    marcacao_manual_detectada = linhas_marcacao_manual > 0

    linhas_com_4 = 0
    linhas_minuto_zero = 0
    linhas_minuto_redondo = 0
    for ln in linhas:
        if not re.search(r"^\s*\d{1,2}\b", ln):
            continue
        hs = re.findall(r"\b\d{1,2}[:\.\s]\d{2}\b", ln)
        hs_norm = []
        for hraw in hs[:4]:
            hnorm, _ = normalizar_horario_ocr(hraw)
            if hnorm:
                hs_norm.append(hnorm)
        if len(hs_norm) >= 4:
            linhas_com_4 += 1
            if all(h.endswith(":00") for h in hs_norm[:4]):
                linhas_minuto_zero += 1
            # "Horario britanico": minutos excessivamente redondos e repetitivos.
            mins = [int(h.split(":")[1]) for h in hs_norm[:4]]
            if all(m in {0, 5, 10, 15, 20, 30, 40, 45, 50, 55} for m in mins):
                linhas_minuto_redondo += 1

    ratio_zero = (linhas_minuto_zero / max(1, linhas_com_4))
    ratio_redondo = (linhas_minuto_redondo / max(1, linhas_com_4))
    indicio_britanico = (
        (linhas_com_4 >= 5 and ratio_zero >= 0.80)
        or (linhas_com_4 >= 5 and ratio_redondo >= 0.90)
    )

    marcacoes_ok = ((qtd >= 8) or (marcacao_manual_detectada and qtd >= 2)) and (not indicio_britanico)
    return {
        "marcacoes_encontradas": marcacoes_ok,
        "qtd_horarios": qtd,
        "horarios": horarios,
        "horarios_corrigidos": corrigidos,
        "marcacao_manual_detectada": marcacao_manual_detectada,
        "linhas_marcacao_manual": linhas_marcacao_manual,
        "indicio_rasura_horario_britanico": indicio_britanico,
        "rasura_motivo": "Indício de horário britânico: horários redondos e repetitivos (ex.: 08:00 12:00 13:00 17:00)." if indicio_britanico else "",
        "confianca": min(1.0, qtd / 24.0),
    }


def extrair_campos_texto_nativo_cartao(texto, layout):
    nome_info = extrair_nome_cartao_ponto_info(texto)
    comp_info = extrair_competencia_cartao_ponto_info(texto)
    marc = extrair_marcacoes_cartao_ponto(texto)
    ass = {"assinatura": False, "assinatura_tipo": "ausente", "assinatura_origem": "nao_identificada", "assinatura_confianca": 0.0, "assinatura_zona": "desconhecida", "assinatura_bbox": []}
    if layout == "log_assinatura_digital":
        m_nome = re.search(r"ASSINATURA\s+DE:\s*(.+)", str(texto or ""), flags=re.IGNORECASE)
        nome = (m_nome.group(1).strip() if m_nome else "") or nome_info.get("nome") or ""
        ass = {
            "assinatura": True,
            "assinatura_tipo": "assinatura_digital",
            "assinatura_origem": "texto_nativo_log",
            "assinatura_confianca": 0.99,
            "assinatura_zona": "texto_digital",
            "assinatura_bbox": [],
        }
        return {
            "nome_info": {"nome": nome.title() if nome else "", "confianca": 0.95, "origem": "texto_nativo_log", "ancora_usada": "ASSINATURA DE"},
            "competencia_info": comp_info,
            "marcacoes_info": marc,
            "assinatura_info": ass,
        }
    if "ASSINATURA DE:" in _norm(texto) and "ASSINADO EM:" in _norm(texto):
        ass.update({"assinatura": True, "assinatura_tipo": "assinatura_digital", "assinatura_origem": "texto_nativo_log", "assinatura_confianca": 0.95, "assinatura_zona": "texto_digital"})
    return {"nome_info": nome_info, "competencia_info": comp_info, "marcacoes_info": marc, "assinatura_info": ass}


def recortar_area_documento(imagem):
    if imagem is None or imagem.size == 0:
        return imagem, [0, 0, 0, 0]
    gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY) if len(imagem.shape) == 3 else imagem
    _, th = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)), iterations=2)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        h, w = gray.shape[:2]
        return imagem, [0, 0, w, h]
    c = max(cnts, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    px, py = max(10, int(w * 0.02)), max(10, int(h * 0.02))
    x1, y1 = max(0, x - px), max(0, y - py)
    x2, y2 = min(imagem.shape[1], x + w + px), min(imagem.shape[0], y + h + py)
    crop = imagem[y1:y2, x1:x2]
    return cv2.convertScaleAbs(crop, alpha=1.15, beta=8), [x1, y1, x2, y2]


def diagnosticar_pagina_cartao(page, page_index):
    texto_nativo = (page.get_text("text") or "").strip()
    texto_len = len(texto_nativo)
    norm = _norm(texto_nativo)
    tem_chaves = sum(1 for p in PALAVRAS_CHAVE_CARTAO if _norm(p) in norm) >= 3
    precisa_ocr = not (texto_len >= 120 and tem_chaves)

    if "ASSINATURA DE:" in norm and "LOG DE ASSINATURA" in norm:
        tipo_inicial = "log_assinatura_digital"
        motivo = "log_digital_textual"
        precisa_ocr = False
    elif all(k in norm for k in ["DADOS DO COLABORADOR", "NOME", "FOLHA DE PONTO"]):
        tipo_inicial = "cartao_digital_texto_nativo"
        motivo = "texto_nativo_estruturado"
        precisa_ocr = False
    elif precisa_ocr:
        tipo_inicial = "imagem_escaneada"
        motivo = "texto_nativo_insuficiente"
    else:
        tipo_inicial = "cartao_texto_nativo"
        motivo = "texto_nativo_suficiente"

    return {
        "pagina": int(page_index) + 1,
        "texto_nativo": texto_nativo,
        "texto_nativo_len": texto_len,
        "tem_texto_nativo": texto_len > 0,
        "precisa_ocr": bool(precisa_ocr),
        "tipo_inicial": tipo_inicial,
        "motivo": motivo,
    }


def renderizar_pagina_fitz(page, dpi=200):
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def renderizar_pagina_pdf(pdf_path, page_index, dpi=200):
    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        return renderizar_pagina_fitz(page, dpi=dpi)


def preparar_imagem_cartao_manual(caminho_pdf, pagina, dpi=350):
    """
    Prepara recortes visuais para modo manual_escaneado_visual usando PyMuPDF.
    """
    img = renderizar_pagina_pdf(caminho_pdf, max(0, int(pagina) - 1), dpi=dpi)
    if img is None:
        return {"pagina_inteira": None, "cabecalho": None, "faixa_empregado": None, "tabela": None, "rodape": None}
    info = recortar_area_util_documento(img)
    base = info.get("imagem")
    if base is None or getattr(base, "size", 0) == 0:
        return {"pagina_inteira": None, "cabecalho": None, "faixa_empregado": None, "tabela": None, "rodape": None}

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY) if len(base.shape) == 3 else base
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    den = cv2.fastNlMeansDenoising(gray, h=7)
    proc = cv2.cvtColor(den, cv2.COLOR_GRAY2BGR)

    h, w = proc.shape[:2]
    def r(y1, y2, x1=0.0, x2=1.0):
        return proc[int(h * y1):int(h * y2), int(w * x1):int(w * x2)]

    return {
        "pagina_inteira": proc,
        "cabecalho": r(0.00, 0.35),
        "faixa_empregado": r(0.12, 0.32),
        "tabela": r(0.28, 0.82),
        "rodape": r(0.78, 1.00),
    }


def preprocessar_cartao_ponto_imagem(imagem):
    passos = []
    gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY) if len(imagem.shape) == 3 else imagem.copy()
    passos.append("gray")
    gray = cv2.convertScaleAbs(gray, alpha=1.25, beta=10)
    passos.append("contraste")
    blur_bg = cv2.medianBlur(gray, 31)
    sem_sombra = cv2.divide(gray, blur_bg, scale=255)
    passos.append("reducao_sombra")
    binaria = cv2.adaptiveThreshold(sem_sombra, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 12)
    passos.append("threshold")
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))
    passos.append("ruido_leve")
    return {"imagem_processada": binaria, "preprocessamentos": passos}


def recortar_area_documento_cartao(imagem):
    info = recortar_area_util_documento(imagem)
    crop, bbox = info["imagem"], info["bbox"]
    return {
        "imagem_recortada": crop,
        "bbox": bbox,
        "recorte_aplicado": bool(info.get("aplicou_recorte")),
        "percentual_area_util": float(info.get("percentual_area_util") or 1.0),
    }


def recortar_area_util_documento(imagem):
    if imagem is None or imagem.size == 0:
        return {"imagem": imagem, "bbox": [0, 0, 0, 0], "aplicou_recorte": False, "percentual_area_util": 0.0}
    gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY) if len(imagem.shape) == 3 else imagem
    _, th = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11)), iterations=2)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    if not cnts:
        return {"imagem": imagem, "bbox": [0, 0, w, h], "aplicou_recorte": False, "percentual_area_util": 1.0}
    c = max(cnts, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(c)
    pad_x, pad_y = max(8, int(bw * 0.015)), max(8, int(bh * 0.015))
    x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
    x2, y2 = min(w, x + bw + pad_x), min(h, y + bh + pad_y)
    area_total = max(1, w * h)
    area_util = max(1, (x2 - x1) * (y2 - y1))
    pct = float(area_util / area_total)
    crop = imagem[y1:y2, x1:x2]
    aplicou = (x1 > 0 or y1 > 0 or x2 < w or y2 < h)
    return {"imagem": crop, "bbox": [x1, y1, x2, y2], "aplicou_recorte": aplicou, "percentual_area_util": round(pct, 4)}


def gerar_recortes_cartao_ponto(imagem_recortada):
    h, w = imagem_recortada.shape[:2]
    def rec(x1, y1, x2, y2):
        return imagem_recortada[int(h * y1):int(h * y2), int(w * x1):int(w * x2)]
    out = {"pagina_inteira_recortada": imagem_recortada}
    for nome, (x1, y1, x2, y2) in RECORTE_CFG.items():
        out[nome] = rec(x1, y1, x2, y2)
    return out


def _ocr_tesseract_imagem(imagem):
    proc = preprocessar_cartao_ponto_imagem(imagem)["imagem_processada"]
    try:
        return pytesseract.image_to_string(proc, lang="por", config="--oem 3 --psm 6")
    except Exception:
        return ""


def executar_ocr_regioes_cartao_ponto(imagem_recortada):
    recortes = gerar_recortes_cartao_ponto(imagem_recortada)
    metodos = []
    linhas = []
    textos = {}
    qualidade = 0.0
    print(f"[CARTAO] PaddleOCR: {'disponível' if paddle_disponivel() else 'indisponível'}")
    print(f"[CARTAO] EasyOCR: {'disponível' if easyocr_disponivel() else 'indisponível'}")
    print(f"[CARTAO] docTR: {'disponível' if doctr_disponivel() else 'indisponível'}")
    print(f"[CARTAO] Surya OCR: {'disponível' if surya_disponivel() else 'indisponível'}")
    print("[CARTAO] OCR região topo")
    print("[CARTAO] OCR região tabela")
    print("[CARTAO] OCR região rodapé")

    def absorver_resultado(resultado, regiao):
        nonlocal qualidade
        metodo = resultado.get("metodo", "")
        texto_resultado = str(resultado.get("texto") or "").strip()
        if texto_resultado and metodo in {"paddleocr", "easyocr", "doctr", "surya"}:
            metodos.append(metodo)
            qualidade = max(qualidade, float(resultado.get("qualidade") or 0))
            for ln in resultado.get("linhas", []):
                item = dict(ln)
                item["regiao"] = regiao
                item["metodo"] = metodo
                linhas.append(item)
        return texto_resultado

    for nome, img in {"total": imagem_recortada, **recortes}.items():
        partes_texto = []
        texto = absorver_resultado(executar_paddleocr_imagem(img, lang="pt"), nome)
        if texto:
            partes_texto.append(texto)
        texto_combinado = "\n".join(partes_texto).strip()

        if len(texto_combinado) < 30:
            easy = absorver_resultado(executar_easyocr_imagem(img, lang=("pt", "en")), nome)
            if easy:
                partes_texto.append(easy)
            texto_combinado = "\n".join(partes_texto).strip()

        if len(texto_combinado) < 30:
            doctr = absorver_resultado(executar_doctr_imagem(img), nome)
            if doctr:
                partes_texto.append(doctr)
            texto_combinado = "\n".join(partes_texto).strip()

        if len(texto_combinado) < 30:
            surya = absorver_resultado(executar_surya_ocr_imagem(img), nome)
            if surya:
                partes_texto.append(surya)
            texto_combinado = "\n".join(partes_texto).strip()

        if len(texto_combinado) < 30:
            tess = _ocr_tesseract_imagem(img)
            if tess:
                metodos.append("tesseract")
                partes_texto.append(tess)
                qualidade = max(qualidade, min(1.0, len(tess) / 1200.0))
        textos[f"texto_{nome}"] = "\n".join(partes_texto).strip()
    return {
        "texto_total": textos.get("texto_total", ""),
        "texto_topo": textos.get("texto_topo", ""),
        "texto_cabecalho_esquerdo": textos.get("texto_cabecalho_esquerdo", ""),
        "texto_tabela": textos.get("texto_tabela", ""),
        "texto_coluna_assinatura": textos.get("texto_coluna_assinatura", ""),
        "texto_rodape": textos.get("texto_rodape", ""),
        "linhas": linhas,
        "qualidade": round(qualidade, 4),
        "metodos_usados": sorted(set(metodos)) or ["tesseract"],
        "recortes": recortes,
    }


def extrair_nome_cartao_ponto_por_regiao(resultado_ocr, nomes_esperados=None):
    textos = "\n".join([
        resultado_ocr.get("texto_topo", ""),
        resultado_ocr.get("texto_cabecalho_esquerdo", ""),
        resultado_ocr.get("texto_total", ""),
    ])
    nomes_esperados = nomes_esperados or []
    norm_total = _norm(textos)
    for nome in nomes_esperados:
        if fuzz.partial_ratio(_norm(nome), norm_total) >= 75:
            return {"nome": nome.title(), "nome_encontrado": True, "origem": "nome_esperado", "confianca": 0.9}
    info = extrair_nome_cartao_ponto_info(textos)
    if info.get("nome"):
        return {"nome": info["nome"], "nome_encontrado": True, "origem": "topo" if "NOME" in _norm(resultado_ocr.get("texto_topo", "")) else "cabecalho_esquerdo", "confianca": info.get("confianca", 0.0)}
    linhas = resultado_ocr.get("linhas", [])
    for idx, linha in enumerate(linhas):
        if any(a in _norm(linha.get("texto", "")) for a in ["FUNCIONARIO", "FUNCION.", "COLABORADOR", "EMPREGADO", "NOME"]):
            for cand in [linha.get("texto", ""), linhas[idx + 1].get("texto", "") if idx + 1 < len(linhas) else ""]:
                cand = re.sub(r"^\d+\s*[-:]\s*", "", cand or "")
                info = extrair_nome_cartao_ponto_info(f"NOME: {cand}")
                if info.get("nome"):
                    return {"nome": info["nome"], "nome_encontrado": True, "origem": "linha_ocr", "confianca": 0.78}
    return {"nome": "", "nome_encontrado": False, "origem": "nao_encontrado", "confianca": 0.0}


def extrair_competencia_cartao_ponto_por_regiao(resultado_ocr):
    texto = "\n".join([resultado_ocr.get("texto_topo", ""), resultado_ocr.get("texto_cabecalho_esquerdo", ""), resultado_ocr.get("texto_total", "")])
    return extrair_competencia_cartao_ponto_info(texto)


def extrair_marcacoes_cartao_ponto_por_regiao(resultado_ocr):
    return extrair_marcacoes_cartao_ponto("\n".join([resultado_ocr.get("texto_tabela", ""), resultado_ocr.get("texto_total", "")]))


def _ocr_regiao_tesseract(imagem, config):
    if imagem is None or getattr(imagem, "size", 0) == 0:
        return ""
    gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY) if len(imagem.shape) == 3 else imagem
    return pytesseract.image_to_string(gray, lang="por", config=config) or ""


def ocr_cartao_por_regioes(recortes, layout):
    # OCR agressivo de nome: combina topo, cabeçalho e faixa dedicada de empregado/funcionário.
    texto_topo = _ocr_regiao_tesseract(recortes.get("topo"), "--oem 1 --psm 6 -l por")
    texto_ce = _ocr_regiao_tesseract(recortes.get("cabecalho_esquerdo"), "--oem 1 --psm 6 -l por")
    texto_fn = _ocr_regiao_tesseract(recortes.get("faixa_nome"), "--oem 1 --psm 6 -l por")
    base_header = "\n".join([texto_topo, texto_ce, texto_fn]).strip()
    nome_info = extrair_nome_cartao_ponto_info(base_header)
    comp_info = extrair_competencia_cartao_ponto_info(base_header)

    if not nome_info.get("nome"):
        # Segunda passada mais agressiva somente quando nome está ausente.
        texto_fn_alt = _ocr_regiao_tesseract(recortes.get("faixa_nome"), "--oem 1 --psm 11 -l por")
        nome_info = extrair_nome_cartao_ponto_info("\n".join([base_header, texto_fn_alt]))

    texto_tabela = ""
    if not (nome_info.get("nome") and comp_info.get("competencia")) or layout in {"manual_frente", "manual_frente_verso", "manual_assinatura_diaria", "imagem_escaneada_generica", "desconhecido"}:
        texto_tabela = _ocr_regiao_tesseract(recortes.get("tabela"), "--oem 1 --psm 6 -l por")
    marc_info = extrair_marcacoes_cartao_ponto(texto_tabela)

    texto_rodape = ""
    texto_coluna_assinatura = _ocr_regiao_tesseract(recortes.get("coluna_assinatura"), "--oem 1 --psm 6 -l por")
    if layout in {"manual_verso", "manual_assinatura_diaria", "desconhecido", "imagem_escaneada_generica"}:
        texto_rodape = _ocr_regiao_tesseract(recortes.get("rodape"), "--oem 1 --psm 7 -l por")

    texto_total = "\n".join([base_header, texto_tabela, texto_rodape]).strip()
    return {
        "texto_total": texto_total,
        "texto_topo": texto_topo,
        "texto_faixa_nome": texto_fn,
        "texto_cabecalho_esquerdo": texto_ce,
        "texto_tabela": texto_tabela,
        "texto_coluna_assinatura": texto_coluna_assinatura,
        "texto_rodape": texto_rodape,
        "nome_info": nome_info,
        "competencia_info": comp_info,
        "marcacoes_info": marc_info,
        "metodos_usados": ["tesseract"],
    }


def tem_marcacao_manual_na_regiao(imagem_regiao):
    if imagem_regiao is None or getattr(imagem_regiao, "size", 0) == 0:
        return False, 0.0
    gray = cv2.cvtColor(imagem_regiao, cv2.COLOR_BGR2GRAY) if len(imagem_regiao.shape) == 3 else imagem_regiao
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 12)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 35))
    linhas = cv2.morphologyEx(th, cv2.MORPH_OPEN, h_kernel) | cv2.morphologyEx(th, cv2.MORPH_OPEN, v_kernel)
    sem_linhas = cv2.bitwise_and(th, cv2.bitwise_not(linhas))
    densidade = float(np.count_nonzero(sem_linhas)) / float(max(1, sem_linhas.size))
    cnts, _ = cv2.findContours(sem_linhas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    irreg = [c for c in cnts if 12 < cv2.contourArea(c) < 5000]
    score = min(1.0, (densidade * 9.0) + (len(irreg) / 35.0))
    return score >= 0.22, round(score, 4)


def detectar_assinatura_cartao_ponto_por_regiao(imagem_recortada, resultado_ocr=None):
    recortes = (resultado_ocr or {}).get("recortes") or gerar_recortes_cartao_ponto(imagem_recortada)
    coluna = recortes.get("coluna_assinatura")
    rodape = recortes.get("rodape")
    ok_col, conf_col, motivo_col = _heuristica_coluna_assinatura(coluna)
    print(f"[CARTAO] Rubrica coluna: {ok_col}")
    if ok_col:
        return {"assinatura": True, "assinatura_tipo": "rubrica", "assinatura_origem": "heuristica_coluna", "assinatura_confianca": round(conf_col, 4), "assinatura_zona": "coluna_assinatura", "assinatura_bbox": [], "motivo": motivo_col}
    score = pontuar_rubrica(cv2.cvtColor(rodape, cv2.COLOR_BGR2GRAY) if len(rodape.shape) == 3 else rodape)
    ok_rodape = score >= 55
    print(f"[CARTAO] Assinatura rodapé: {ok_rodape}")
    if ok_rodape:
        return {"assinatura": True, "assinatura_tipo": "assinatura_manual", "assinatura_origem": "opencv_rodape", "assinatura_confianca": round(min(0.95, score / 100.0), 4), "assinatura_zona": "rodape", "assinatura_bbox": [], "motivo": f"OpenCV rodape score={score}"}
    return {"assinatura": False, "assinatura_tipo": "ausente", "assinatura_origem": "nao_identificada", "assinatura_confianca": 0.0, "assinatura_zona": "desconhecida", "assinatura_bbox": [], "motivo": "Sem assinatura visual por região."}


def deve_chamar_ia_visual_cartao_ponto(resultado_local):
    return bool(
        not resultado_local.get("nome_colaborador")
        or not resultado_local.get("competencia")
        or resultado_local.get("assinatura_tipo") == "inconclusiva"
        or resultado_local.get("qualidade_ocr", 1.0) < 0.35
        or resultado_local.get("layout") == "generico"
    )


def fallback_ia_visual_cartao_ponto(recortes, resultado_local):
    return {
        "usado": False,
        "motivo": "IA visual não configurada.",
        "campos_corrigidos": [],
        "confianca": 0.0,
        "resultado": {},
    }


def mesclar_resultado_cartao_local_ia(resultado_local, resultado_ia):
    out = dict(resultado_local)
    fb = {"usado": False, "motivo": "", "campos_corrigidos": [], "confianca": 0.0}
    ia = (resultado_ia or {}).get("resultado", {})
    conf = float((resultado_ia or {}).get("confianca") or ia.get("confianca") or 0)
    if ia.get("nome") and not out.get("nome_colaborador"):
        out["nome_colaborador"] = ia["nome"]
        fb["campos_corrigidos"].append("nome")
    if ia.get("assinatura") and not out.get("assinatura") and conf >= 0.75:
        out["assinatura"] = True
        out["assinatura_tipo"] = ia.get("assinatura_tipo", "inconclusiva")
        out["assinatura_origem"] = "ia_fallback"
        fb["campos_corrigidos"].append("assinatura")
    fb["usado"] = bool(fb["campos_corrigidos"])
    fb["confianca"] = conf
    out["fallback_ia"] = fb
    return out


def _heuristica_coluna_assinatura(imagem_crop):
    if imagem_crop is None or imagem_crop.size == 0:
        return False, 0.0, "Sem imagem para heuristica da assinatura."
    gray = cv2.cvtColor(imagem_crop, cv2.COLOR_BGR2GRAY) if len(imagem_crop.shape) == 3 else imagem_crop
    h, w = gray.shape[:2]
    roi = gray[int(h * 0.2):h, int(w * 0.72):w]
    _, th = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    validos = [c for c in cnts if 20 < cv2.contourArea(c) < 4000]
    ok = len(validos) >= 6
    return ok, min(0.75, len(validos) / 10.0), f"Contornos coluna assinatura: {len(validos)}"


def _get_yolo_models():
    global _YOLO_MODELS
    if _YOLO_MODELS is not None:
        return _YOLO_MODELS
    _YOLO_MODELS = []
    try:
        from ultralytics import YOLO
        for p in caminhos_modelos_yolo():
            try:
                _YOLO_MODELS.append(YOLO(str(p)))
            except Exception:
                continue
    except Exception:
        _YOLO_MODELS = []
    return _YOLO_MODELS


def _predict_yolo_crop(imagem, zona):
    modelos = _get_yolo_models()
    if not modelos or imagem is None or getattr(imagem, "size", 0) == 0:
        return None
    classes_ok = {"assinatura", "rubrica", "assinatura_digital_visual"}
    best = None
    for m in modelos:
        try:
            res = m.predict(source=imagem, conf=0.25, verbose=False)
            for r in (res or []):
                boxes = getattr(r, "boxes", None)
                if boxes is None:
                    continue
                names = getattr(r, "names", {}) or {}
                for b in boxes:
                    cls = int(float(b.cls[0])) if getattr(b, "cls", None) is not None else -1
                    conf = float(b.conf[0]) if getattr(b, "conf", None) is not None else 0.0
                    nome = str(names.get(cls, cls)).lower()
                    if nome not in classes_ok:
                        continue
                    if (best is None) or (conf > best["assinatura_confianca"]):
                        tipo = "rubrica" if nome == "rubrica" else ("assinatura_digital" if nome == "assinatura_digital_visual" else "assinatura_manual")
                        xyxy = b.xyxy[0].tolist() if getattr(b, "xyxy", None) is not None else []
                        best = {
                            "assinatura": True,
                            "assinatura_tipo": tipo,
                            "assinatura_origem": f"yolo_{zona}",
                            "assinatura_confianca": conf,
                            "assinatura_zona": zona,
                            "bbox": [float(v) for v in xyxy] if xyxy else [],
                        }
        except Exception:
            continue
    return best


def detectar_assinatura_rapida(imagem_recortada, recortes, texto_pagina, layout):
    tn = _norm(texto_pagina)
    if layout == "log_assinatura_digital" or ("ASSINATURA DE:" in tn and "ASSINADO EM:" in tn):
        return {"assinatura": True, "assinatura_tipo": "assinatura_digital", "assinatura_origem": "texto_nativo_log", "assinatura_confianca": 0.99, "assinatura_zona": "texto_digital", "bbox": []}

    ordem = []
    if layout == "manual_assinatura_diaria":
        ordem = ["coluna_assinatura"]
    elif layout == "manual_verso" or "ASSINATURA DO EMPREGADO" in tn:
        ordem = ["rodape"]
    else:
        ordem = ["rodape", "coluna_assinatura"]

    for zona in ordem:
        img = recortes.get(zona)
        manual, score = tem_marcacao_manual_na_regiao(img)
        if manual:
            return {
                "assinatura": True,
                "assinatura_tipo": "rubrica" if zona == "coluna_assinatura" else "assinatura_manual",
                "assinatura_origem": f"heuristica_{zona}",
                "assinatura_confianca": score,
                "assinatura_zona": zona,
                "bbox": [],
            }
        pred = _predict_yolo_crop(img, zona)
        if pred:
            return pred
        if zona == "rodape":
            score_cv = pontuar_rubrica(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img)
            if score_cv >= 55:
                return {
                    "assinatura": True,
                    "assinatura_tipo": "assinatura_manual",
                    "assinatura_origem": "opencv_rodape",
                    "assinatura_confianca": round(min(0.95, score_cv / 100.0), 4),
                    "assinatura_zona": "rodape",
                    "bbox": [],
                }

    pred_full = _predict_yolo_crop(imagem_recortada, "pagina_inteira")
    if pred_full:
        return pred_full
    return {"assinatura": False, "assinatura_tipo": "ausente", "assinatura_origem": "nao_identificada", "assinatura_confianca": 0.0, "assinatura_zona": "desconhecida", "bbox": []}


def detectar_assinatura_cartao_ponto(layout, texto_pagina, pagina_num, deteccoes_yolo_pagina, imagem_crop):
    tn = _norm(texto_pagina)
    if all(k in tn for k in ["ASSINATURA DE:", "ASSINADO EM:"]) or "DOCUMENTO ASSINADO DIGITALMENTE" in tn:
        return {"assinatura": True, "assinatura_tipo": "assinatura_digital", "assinatura_origem": "texto_digital", "assinatura_confianca": 0.95, "assinatura_bbox": [], "assinatura_zona": "desconhecida", "assinatura_pagina": pagina_num, "assinatura_motivo": "Log/assinatura digital textual identificado."}

    classes_ok = {"assinatura", "rubrica", "campo_assinatura", "campo_assinatura_vazio", "assinatura_digital_visual"}
    cand = [d for d in (deteccoes_yolo_pagina or []) if d.get("pagina") == pagina_num and str(d.get("classe_nome", "")).lower() in classes_ok and str(d.get("classe_nome", "")).lower() != "campo_assinatura_vazio"]
    if cand:
        best = max(cand, key=lambda x: float(x.get("confianca") or 0))
        c = str(best.get("classe_nome", "")).lower()
        tipo = "rubrica" if c == "rubrica" else ("assinatura_digital" if c == "assinatura_digital_visual" else "assinatura_manual")
        return {"assinatura": True, "assinatura_tipo": tipo, "assinatura_origem": "yolo", "assinatura_confianca": float(best.get("confianca") or 0), "assinatura_bbox": best.get("bbox") or [], "assinatura_zona": best.get("zona_vertical") or "desconhecida", "assinatura_pagina": pagina_num, "assinatura_motivo": f"YOLO detectou '{c}'."}

    if layout == "tabela_com_assinatura_diaria":
        ok, conf, motivo = _heuristica_coluna_assinatura(imagem_crop)
        if ok:
            return {"assinatura": True, "assinatura_tipo": "rubrica", "assinatura_origem": "heuristica_visual", "assinatura_confianca": round(conf, 4), "assinatura_bbox": [], "assinatura_zona": "coluna_assinatura", "assinatura_pagina": pagina_num, "assinatura_motivo": motivo}

    score_cv = pontuar_rubrica(cv2.cvtColor(imagem_crop, cv2.COLOR_BGR2GRAY) if len(imagem_crop.shape) == 3 else imagem_crop)
    if score_cv >= 55:
        return {"assinatura": True, "assinatura_tipo": "assinatura_manual", "assinatura_origem": "opencv", "assinatura_confianca": round(min(0.95, score_cv / 100.0), 4), "assinatura_bbox": [], "assinatura_zona": "rodape", "assinatura_pagina": pagina_num, "assinatura_motivo": f"Rubrica detectada por OpenCV (score={score_cv})."}

    if any(k in tn for k in FECHAMENTO_TOKENS):
        return {"assinatura": False, "assinatura_tipo": "inconclusiva", "assinatura_origem": "nao_identificada", "assinatura_confianca": 0.15, "assinatura_bbox": [], "assinatura_zona": "rodape", "assinatura_pagina": pagina_num, "assinatura_motivo": "Campo/termo de assinatura presente sem evidencia visual conclusiva."}

    return {"assinatura": False, "assinatura_tipo": "ausente", "assinatura_origem": "nao_identificada", "assinatura_confianca": 0.0, "assinatura_bbox": [], "assinatura_zona": "desconhecida", "assinatura_pagina": None, "assinatura_motivo": "Sem evidencia de assinatura/rubrica."}


def agrupar_paginas_cartao_ponto(resultados_paginas):
    return consolidar_frente_verso(resultados_paginas)


def consolidar_frente_verso(resultados_paginas):
    grupos = []
    i = 0
    while i < len(resultados_paginas):
        atual = dict(resultados_paginas[i])
        atual["paginas_grupo"] = [atual["pagina"]]
        if i + 1 < len(resultados_paginas):
            prox = resultados_paginas[i + 1]
            prox_t = _norm(prox.get("texto_pagina", ""))
            frente = bool(atual.get("nome_colaborador")) and bool(atual.get("competencia")) and bool(atual.get("qtd_horarios", 0) >= 8)
            prox_tem_nome = bool(prox.get("nome_colaborador"))
            nome_atual = _norm(atual.get("nome_colaborador", ""))
            nome_prox = _norm(prox.get("nome_colaborador", ""))
            nome_similar = bool(nome_atual and nome_prox and (fuzz.ratio(nome_atual, nome_prox) >= 80))
            prox_ass = bool(prox.get("assinatura")) or any(k in prox_t for k in FECHAMENTO_TOKENS) or ("LOG DE ASSINATURA" in prox_t)
            cond_frente_verso = frente and (not prox_tem_nome) and prox_ass
            cond_log_digital = ("ASSINATURA DE:" in prox_t and "ASSINADO EM:" in prox_t and (nome_similar or (not nome_prox)))
            if cond_frente_verso or cond_log_digital:
                atual["paginas_grupo"].append(prox["pagina"])
                atual["assinatura"] = bool(prox.get("assinatura"))
                atual["assinatura_tipo"] = prox.get("assinatura_tipo") or atual.get("assinatura_tipo")
                atual["assinatura_origem"] = prox.get("assinatura_origem") or atual.get("assinatura_origem")
                atual["assinatura_confianca"] = max(float(atual.get("assinatura_confianca") or 0), float(prox.get("assinatura_confianca") or 0))
                atual["assinatura_bbox"] = prox.get("assinatura_bbox") or atual.get("assinatura_bbox")
                atual["assinatura_motivo"] = prox.get("assinatura_motivo") or atual.get("assinatura_motivo")
                atual["assinatura_pagina"] = prox.get("assinatura_pagina") or prox.get("pagina")
                atual["assinatura_zona"] = prox.get("assinatura_zona") or atual.get("assinatura_zona")
                atual["qtd_horarios"] = int(atual.get("qtd_horarios") or 0) + int(prox.get("qtd_horarios") or 0)
                atual["marcacoes_encontradas"] = bool(atual["qtd_horarios"] >= 8)
                if not atual.get("periodo_inicio") and prox.get("periodo_inicio"):
                    atual["periodo_inicio"] = prox.get("periodo_inicio")
                if not atual.get("periodo_fim") and prox.get("periodo_fim"):
                    atual["periodo_fim"] = prox.get("periodo_fim")
                i += 1
        grupos.append(atual)
        i += 1
    return grupos


def consolidar_colaboradores_cartao_ponto(resultados_paginas):
    consolidados = []
    for grupo in agrupar_paginas_cartao_ponto(resultados_paginas):
        nome = grupo.get("nome_colaborador") or "Colaborador sem nome"
        competencia = grupo.get("competencia") or ""
        marcacoes = bool(grupo.get("marcacoes_encontradas"))
        assinatura = bool(grupo.get("assinatura"))
        score = (25 if nome != "Colaborador sem nome" else 0) + (25 if competencia else 0) + (25 if marcacoes else 0) + (25 if assinatura else 0)
        if score >= 80:
            status = "OK"
        elif score >= 50:
            status = "INCONCLUSIVO"
        else:
            status = "FALTANDO"
        if nome == "Colaborador sem nome" and status == "OK":
            status = "INCONCLUSIVO"
        motivos = []
        if nome == "Colaborador sem nome":
            motivos.append("Nome não encontrado")
        if not competencia:
            motivos.append("Competência não encontrada")
        if not marcacoes:
            motivos.append("Marcações não encontradas")
        if not assinatura:
            motivos.append("Assinatura/rubrica ausente")
        consolidados.append({
            "nome": nome,
            "paginas": grupo.get("paginas_grupo") or [grupo.get("pagina")],
            "competencia": competencia,
            "periodo_inicio": grupo.get("periodo_inicio", ""),
            "periodo_fim": grupo.get("periodo_fim", ""),
            "marcacoes_encontradas": marcacoes,
            "qtd_horarios": int(grupo.get("qtd_horarios") or 0),
            "assinatura": assinatura,
            "assinatura_tipo": grupo.get("assinatura_tipo") or "ausente",
            "assinatura_origem": grupo.get("assinatura_origem") or "nao_identificada",
            "assinatura_pagina": grupo.get("assinatura_pagina"),
            "assinatura_zona": grupo.get("assinatura_zona", "desconhecida"),
            "status": status,
            "motivos": motivos,
            "avisos": list(grupo.get("avisos", [])),
        })
    return consolidados


def _render_page_bgr(page, dpi=300):
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    else:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return arr


def _ocr_crop(imagem):
    gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    txt1 = pytesseract.image_to_string(cv2.convertScaleAbs(gray, alpha=1.2, beta=8), lang="por", config="--oem 3 --psm 6")
    if len(txt1.strip()) >= 70:
        return txt1
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12)
    return pytesseract.image_to_string(thr, lang="por", config="--oem 3 --psm 6")


def extrair_ocr_cartao_ponto_pagina(imagem_pagina, pagina_numero):
    h, w = imagem_pagina.shape[:2]
    topo = [0, 0, w, int(h * 0.28)]
    tabela = [0, int(h * 0.22), w, int(h * 0.78)]
    rodape = [0, int(h * 0.72), w, h]
    col_ass = [int(w * 0.72), int(h * 0.2), w, h]

    print(f"[CARTAO][P{pagina_numero}] Recorte documento: aplicado")
    print(f"[CARTAO][P{pagina_numero}] PaddleOCR: {'disponível' if paddle_disponivel() else 'indisponível'}")

    full = executar_paddleocr_imagem(imagem_pagina, lang="pt")
    top = executar_paddleocr_regiao(imagem_pagina, topo, lang="pt")
    mid = executar_paddleocr_regiao(imagem_pagina, tabela, lang="pt")
    bot = executar_paddleocr_regiao(imagem_pagina, rodape, lang="pt")
    col = executar_paddleocr_regiao(imagem_pagina, col_ass, lang="pt")

    texto_full = full.get("texto", "")
    metodos = []
    if full.get("qualidade", 0) > 0:
        metodos.append("paddleocr")
    if not texto_full or len(texto_full) < 80:
        print(f"[CARTAO][P{pagina_numero}] Tesseract: usado como fallback")
        texto_full = _ocr_crop(imagem_pagina)
        metodos.append("tesseract")

    linhas = []
    for bloco in [full, top, mid, bot, col]:
        linhas.extend(bloco.get("linhas", []))

    return {
        "pagina": pagina_numero,
        "texto_total": texto_full or "",
        "texto_topo": top.get("texto", ""),
        "texto_tabela": mid.get("texto", ""),
        "texto_rodape": bot.get("texto", ""),
        "linhas_ocr": linhas,
        "metodos_usados": sorted(set(metodos)) or ["tesseract"],
        "qualidade": max(full.get("qualidade", 0.0), min(1.0, len(texto_full) / 1200.0)),
    }


def processar_paginas_cartao_ponto_layout(caminho_pdf, deteccoes_yolo=None, nomes_esperados=None, paginas_texto=None, render_imagem=True, paginas_assinatura_alvo=None):
    mapa_texto = {int(p.get("pagina")): str(p.get("texto", "") or "") for p in (paginas_texto or []) if p.get("pagina")}
    paginas_assinatura_alvo_set = {
        int(x) for x in (paginas_assinatura_alvo or []) if str(x).strip().isdigit() and int(x) > 0
    }
    total_paginas = 0
    with fitz.open(caminho_pdf) as doc_count:
        total_paginas = len(doc_count)

    def _nome_baixa_qualidade(nome_info_local):
        nome = str((nome_info_local or {}).get("nome") or "")
        if not nome.strip():
            return True
        letras = sum(ch.isalpha() for ch in nome)
        ratio = letras / max(1, len(nome))
        conf = float((nome_info_local or {}).get("confianca") or 0.0)
        if conf < 0.8:
            return True
        if ratio < 0.70:
            return True
        if "CAMSCANNER" in nome.upper() or "DIGITALIZADO" in nome.upper():
            return True
        return False

    def _processar_pagina(idx):
        t0 = time.perf_counter()
        cache_key = _cache_key(caminho_pdf, idx, dpi=200, tipo_recorte="pagina")
        item_cache = _cache_load(cache_key, "resultado")
        if item_cache:
            item_cache.setdefault("performance", {})
            item_cache["performance"]["cache_usado"] = True
            return item_cache

        with fitz.open(caminho_pdf) as doc_local:
            page = doc_local[idx - 1]
            diag = diagnosticar_pagina_cartao(page, idx - 1)
            texto_base = (mapa_texto.get(idx) or diag.get("texto_nativo") or "").strip()
            layout = classificar_layout_cartao_ponto(texto_base)

            t_texto = time.perf_counter()
            print(f"[CARTAO][P{idx}] texto_nativo: {t_texto - t0:.2f}s")
            print(f"[CARTAO][P{idx}] layout: {layout}")

            nome_info = {"nome": "", "confianca": 0.0, "origem": "nao_encontrado", "ancora_usada": ""}
            comp_info = {"competencia": "", "periodo_inicio": "", "periodo_fim": "", "avisos": [], "confianca": 0.0, "origem": "nao_identificada"}
            marc = {"marcacoes_encontradas": False, "qtd_horarios": 0, "horarios": [], "horarios_corrigidos": [], "confianca": 0.0}
            ass = {"assinatura": False, "assinatura_tipo": "ausente", "assinatura_origem": "nao_identificada", "assinatura_confianca": 0.0, "assinatura_zona": "desconhecida", "bbox": []}
            texto_topo = ""
            texto_tabela = ""
            texto_rodape = ""
            texto_coluna_assinatura = ""
            usou_ocr = False
            usou_yolo = False
            usou_opencv = False
            dpi_usado = 0

            campos_txt = extrair_campos_texto_nativo_cartao(texto_base, layout)
            pagina_alvo_assinatura = idx in paginas_assinatura_alvo_set
            layout_forca_visual = layout in {"manual_verso", "manual_assinatura_diaria", "manual_frente_verso", "imagem_escaneada_generica"}
            # Mesmo com texto nativo, força visão computacional nas páginas-alvo de assinatura
            # e nos layouts de verso para não perder assinatura na segunda folha.
            pode_pular_ocr = (not diag.get("precisa_ocr")) and (not pagina_alvo_assinatura) and (not layout_forca_visual)
            if pode_pular_ocr or layout in {"log_assinatura_digital", "cartao_digital_texto_nativo"}:
                nome_info = campos_txt["nome_info"]
                comp_info = campos_txt["competencia_info"]
                marc = campos_txt["marcacoes_info"]
                ass = campos_txt["assinatura_info"]
                print(f"[CARTAO][P{idx}] OCR pulado: texto nativo suficiente")
            else:
                t_render = time.perf_counter()
                dpi_usado = 200
                img = renderizar_pagina_fitz(page, dpi=dpi_usado)
                print(f"[CARTAO][P{idx}] render_fitz_200dpi: {time.perf_counter() - t_render:.2f}s")

                t_crop = time.perf_counter()
                recorte = recortar_area_util_documento(img)
                imagem_recortada = recorte["imagem"]
                recortes = gerar_recortes_cartao_ponto(imagem_recortada)
                print(f"[CARTAO][P{idx}] recorte_area_util: {time.perf_counter() - t_crop:.2f}s")

                t_ocr = time.perf_counter()
                ocr = ocr_cartao_por_regioes(recortes, layout)
                usou_ocr = True
                nome_info = ocr.get("nome_info") or nome_info
                comp_info = ocr.get("competencia_info") or comp_info
                marc = ocr.get("marcacoes_info") or marc
                texto_topo = ocr.get("texto_topo") or ""
                texto_tabela = ocr.get("texto_tabela") or ""
                texto_rodape = ocr.get("texto_rodape") or ""
                texto_coluna_assinatura = ocr.get("texto_coluna_assinatura") or ""
                texto_base = (texto_base + "\n" + (ocr.get("texto_total") or "")).strip()
                print(f"[CARTAO][P{idx}] ocr_regioes: {time.perf_counter() - t_ocr:.2f}s")

                if _nome_baixa_qualidade(nome_info) and dpi_usado == 200:
                    t_hq = time.perf_counter()
                    dpi_usado = 300
                    topo_hq = renderizar_pagina_fitz(page, dpi=300)
                    topo_crop = gerar_recortes_cartao_ponto(recortar_area_util_documento(topo_hq)["imagem"]).get("topo")
                    texto_topo_hq = _ocr_regiao_tesseract(topo_crop, "--oem 1 --psm 6 -l por")
                    nome_retry = extrair_nome_cartao_ponto_info(texto_topo_hq)
                    if nome_retry.get("nome"):
                        nome_info = nome_retry
                    print(f"[CARTAO][P{idx}] retry_topo_300dpi: {time.perf_counter() - t_hq:.2f}s")

                t_ass = time.perf_counter()
                ass = detectar_assinatura_rapida(imagem_recortada, recortes, texto_base, layout)
                usou_yolo = str(ass.get("assinatura_origem", "")).startswith("yolo_")
                usou_opencv = "opencv" in str(ass.get("assinatura_origem", "")) or "heuristica" in str(ass.get("assinatura_origem", ""))
                print(f"[CARTAO][P{idx}] assinatura_regiao: {time.perf_counter() - t_ass:.2f}s")

            item = {
                "pagina": idx,
                "layout": layout,
                "nome_colaborador": nome_info.get("nome", ""),
                "nome_info": nome_info,
                "competencia": comp_info.get("competencia", ""),
                "periodo_inicio": comp_info.get("periodo_inicio", ""),
                "periodo_fim": comp_info.get("periodo_fim", ""),
                "competencia_info": comp_info,
                "marcacoes_encontradas": bool(marc.get("marcacoes_encontradas")),
                "qtd_horarios": int(marc.get("qtd_horarios") or 0),
                "marcacoes_info": marc,
                "assinatura": bool(ass.get("assinatura")),
                "assinatura_tipo": ass.get("assinatura_tipo", "ausente"),
                "assinatura_origem": ass.get("assinatura_origem", "nao_identificada"),
                "assinatura_confianca": float(ass.get("assinatura_confianca") or 0.0),
                "assinatura_bbox": ass.get("bbox", ass.get("assinatura_bbox", [])),
                "assinatura_zona": ass.get("assinatura_zona", "desconhecida"),
                "assinatura_pagina": idx if ass.get("assinatura") else None,
                "assinatura_motivo": ass.get("motivo", ""),
                "motivos": [],
                "avisos": list(comp_info.get("avisos", [])),
                "texto_pagina": texto_base,
                "texto_topo": texto_topo,
                "texto_tabela": texto_tabela,
                "texto_rodape": texto_rodape,
                "texto_coluna_assinatura": texto_coluna_assinatura,
                "qualidade_ocr": float(marc.get("confianca") or 0.0) if usou_ocr else 1.0,
                "performance": {
                    "tempo_total_seg": round(time.perf_counter() - t0, 3),
                    "usou_texto_nativo": bool(diag.get("tem_texto_nativo")),
                    "usou_ocr": usou_ocr,
                    "usou_yolo": usou_yolo,
                    "usou_opencv": usou_opencv,
                    "dpi": dpi_usado or 150,
                    "cache_usado": False,
                },
            }
            print(f"[CARTAO][P{idx}] total: {item['performance']['tempo_total_seg']:.2f}s")
            _cache_save(cache_key, "resultado", item)
            return item

    max_workers = min(4, os.cpu_count() or 2)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        resultados = list(executor.map(_processar_pagina, range(1, total_paginas + 1)))
    resultados = sorted(resultados, key=lambda x: int(x.get("pagina") or 0))
    return resultados
