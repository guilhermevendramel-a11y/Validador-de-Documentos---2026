import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

import cv2
import fitz
import numpy as np
import pytesseract
from pdf2image import convert_from_path

import utils.tesseract_config as tesseract_config
from utils.ocr_profiles import carregar_perfis, encontrar_perfil_documento, encontrar_perfil_por_texto

if getattr(tesseract_config, "tesseract_cmd", None):
    pytesseract.pytesseract.tesseract_cmd = tesseract_config.tesseract_cmd

OCR_VERSION = "ocr_v4"
CACHE_DIR = Path("data") / "ocr_cache"

KEYWORDS_BY_DOC = {
    "cartao_ponto": ["PONTO", "FUNCIONARIO", "FUNCIONÁRIO", "COMPETENCIA", "COMPETÊNCIA", "ENTRADA", "SAIDA", "SAÍDA", "ASSINATURA"],
    "holerite": ["HOLERITE", "RECIBO", "SALARIO", "SALÁRIO", "COMPETENCIA", "COMPETÊNCIA", "LIQUIDO", "LÍQUIDO", "LÍQUIDO A RECEBER", "ADIANTAMENTO", "ASSINATURA", "RUBRICA", "VENCIMENTOS", "DESCONTOS"],
    "fgts": ["FGTS", "COMPETENCIA", "COMP. APURACAO", "COMP. APURAÇÃO", "TRABALHADOR", "TOMADOR", "ESTABELECIMENTO", "CNO"],
    "inss": ["DCTFWEB", "DARF", "SALDO A PAGAR", "PERIODO DE APURACAO", "PERÍODO DE APURAÇÃO", "CNPJ"],
    "folha": [
        "FOLHA",
        "PAGAMENTO",
        "EMPRESA",
        "RAZAO SOCIAL",
        "RAZÃO SOCIAL",
        "FUNCIONARIO",
        "FUNCIONÁRIO",
        "NOME DO FUNCIONARIO",
        "NOME DO FUNCIONÁRIO",
        "COLABORADOR",
        "EMPREGADO",
        "COMPETENCIA",
        "COMPETÊNCIA",
    ],
}

FIELD_ANCHORS = {
    "nome": ["NOME", "FUNCIONARIO", "FUNCIONÁRIO", "COLABORADOR", "EMPREGADO"],
    "empresa": ["RAZAO SOCIAL", "RAZÃO SOCIAL", "EMPRESA"],
    "competencia": ["COMPETENCIA", "COMPETÊNCIA", "PERIODO", "PERÍODO", "PA:"],
    "valor_liquido": ["VALOR LIQUIDO", "VALOR LÍQUIDO", "LÍQUIDO A RECEBER", "LIQUIDO A RECEBER", "TOTAL LÍQUIDO", "TOTAL LIQUIDO", "VALOR A RECEBER"],
    "data_pagamento": ["DATA PAGAMENTO", "PAGAMENTO", "VENCIMENTO"],
    "cno": ["CNO", "TOMADOR", "OBRA"],
    "saldo_a_pagar": ["SALDO A PAGAR", "VALOR A RECOLHER", "TOTAL DA GUIA"],
}


def _norm(texto):
    txt = unicodedata.normalize("NFKD", str(texto or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return txt.upper()


def _arquivo_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(caminho_pdf, tipo_documento=None, max_paginas=None, usar_ocr=True, doc_hash=None):
    doc_hash = doc_hash or _arquivo_hash(caminho_pdf)
    raw = f"{doc_hash}|{tipo_documento or ''}|{max_paginas}|{usar_ocr}|{OCR_VERSION}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _cache_path(key):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _load_cache(key):
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(key, data):
    p = _cache_path(key)
    try:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def calcular_qualidade_texto(texto, tipo_documento=None):
    if not texto:
        return 0.0

    txt = str(texto)
    n = len(txt)
    if n < 20:
        return 0.0

    letras = sum(c.isalpha() for c in txt)
    numeros = sum(c.isdigit() for c in txt)
    uteis = letras + numeros
    simbolos_estranhos = sum(1 for c in txt if ord(c) < 32 or c in "�")

    ratio_uteis = uteis / max(1, n)
    ratio_letras = letras / max(1, n)
    penalidade_ruido = min(1.0, simbolos_estranhos / max(1, n))

    base = 0.35 * min(1.0, n / 1200) + 0.35 * ratio_uteis + 0.15 * ratio_letras + 0.15 * (1.0 - penalidade_ruido)

    bonus_keywords = 0.0
    if tipo_documento and tipo_documento in KEYWORDS_BY_DOC:
        norm = _norm(txt)
        kws = KEYWORDS_BY_DOC[tipo_documento]
        hits = sum(1 for k in kws if _norm(k) in norm)
        bonus_keywords = min(0.25, (hits / max(1, len(kws))) * 0.25)

    qualidade = max(0.0, min(1.0, base + bonus_keywords))
    return round(qualidade, 4)


def preprocessar_para_ocr(imagem, perfil="padrao"):
    img = np.array(imagem)
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if perfil == "documento_claro":
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        out = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8)
    elif perfil == "documento_escuro":
        gray = cv2.convertScaleAbs(gray, alpha=1.8, beta=18)
        out = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 10)
    elif perfil == "tabela":
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        out = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    elif perfil == "comprovante":
        gray = cv2.convertScaleAbs(gray, alpha=1.6, beta=6)
        out = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 12)
    elif perfil == "assinatura_nao_usar":
        out = gray
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        out = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)

    return out


def extrair_texto_regiao(imagem, bbox, perfil="padrao", psm=6):
    x1, y1, x2, y2 = [int(max(0, v)) for v in bbox]
    arr = np.array(imagem)
    if y2 <= y1 or x2 <= x1:
        return ""
    recorte = arr[y1:y2, x1:x2]
    if recorte.size == 0:
        return ""
    proc = preprocessar_para_ocr(recorte, perfil=perfil)
    try:
        return pytesseract.image_to_string(proc, lang="por", config=f"--oem 3 --psm {psm}")
    except Exception:
        return ""


def _bbox_absoluto(bbox, largura, altura):
    if not bbox or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = bbox
    if max(abs(float(v)) for v in bbox) <= 1.5:
        return [
            int(max(0, round(float(x1) * largura))),
            int(max(0, round(float(y1) * altura))),
            int(min(largura, round(float(x2) * largura))),
            int(min(altura, round(float(y2) * altura))),
        ]
    return [
        int(max(0, round(float(x1)))),
        int(max(0, round(float(y1)))),
        int(min(largura, round(float(x2)))),
        int(min(altura, round(float(y2)))),
    ]


def _render_pagina(page, dpi=250):
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
    return arr


def _ocr_pagina_com_perfis(img, tipo_documento=None):
    perfis = ["padrao", "documento_claro", "documento_escuro", "tabela", "comprovante"]
    if tipo_documento in {"fgts", "folha", "cartao_ponto"}:
        perfis = ["tabela", "padrao", "documento_claro", "comprovante"]

    configs = ["--oem 3 --psm 6", "--oem 3 --psm 4", "--oem 3 --psm 11"]

    melhor_txt, melhor_q = "", 0.0
    for perfil in perfis:
        proc = preprocessar_para_ocr(img, perfil=perfil)
        for cfg in configs:
            try:
                txt = pytesseract.image_to_string(proc, lang="por", config=cfg)
            except Exception:
                txt = ""
            q = calcular_qualidade_texto(txt, tipo_documento=tipo_documento)
            if q > melhor_q:
                melhor_q = q
                melhor_txt = txt
            if melhor_q >= 0.75:
                return melhor_txt, melhor_q

    return melhor_txt, melhor_q


def _ocr_pagina_com_perfil_layout(img, perfil_layout, tipo_documento=None):
    if img is None or not perfil_layout:
        return "", 0.0

    altura, largura = img.shape[:2]
    regiao_base = _bbox_absoluto(perfil_layout.get("ocr_region"), largura, altura) or [0, 0, largura, altura]
    x1, y1, x2, y2 = regiao_base
    recorte_principal = img[y1:y2, x1:x2]
    if recorte_principal.size == 0:
        return "", 0.0

    txt_principal, q_principal = _ocr_pagina_com_perfis(recorte_principal, tipo_documento=tipo_documento)
    linhas_sinteticas = []

    campos = perfil_layout.get("campos") or {}
    for campo, definicao in campos.items():
        if not isinstance(definicao, dict):
            continue
        bbox = _bbox_absoluto(definicao.get("bbox"), largura, altura)
        if not bbox:
            continue
        texto_campo = extrair_texto_regiao(
            img,
            bbox,
            perfil=definicao.get("perfil", "documento_claro"),
            psm=int(definicao.get("psm", 6)),
        )
        texto_campo = re.sub(r"\s+", " ", str(texto_campo or "")).strip()
        if not texto_campo:
            continue
        rotulo = definicao.get("label") or campo.replace("_", " ").upper()
        linhas_sinteticas.append(f"{rotulo}: {texto_campo}")

    texto_final = txt_principal.strip()
    if linhas_sinteticas:
        prefixo = "\n".join(linhas_sinteticas).strip()
        texto_final = f"{prefixo}\n{texto_final}".strip() if texto_final else prefixo

    qualidade_campos = calcular_qualidade_texto("\n".join(linhas_sinteticas), tipo_documento=tipo_documento) if linhas_sinteticas else 0.0
    qualidade_final = max(q_principal, min(1.0, qualidade_campos + (0.03 * len(linhas_sinteticas))))
    return texto_final, round(qualidade_final, 4)


def extrair_trechos_relevantes(texto, tipo_documento, campos_esperados=None, janela=500):
    texto = str(texto or "")
    norm = _norm(texto)

    campos = campos_esperados or list(FIELD_ANCHORS.keys())
    trechos = []

    for campo in campos:
        anchors = FIELD_ANCHORS.get(campo, [])
        for anc in anchors:
            anc_norm = _norm(anc)
            pos = norm.find(anc_norm)
            if pos == -1:
                continue
            ini = max(0, pos - janela)
            fim = min(len(texto), pos + len(anc_norm) + janela)
            trechos.append({
                "campo": campo,
                "ancora": anc,
                "trecho": texto[ini:fim],
            })
            break

    return trechos


def deve_chamar_ia(resultado_ocr, resultado_parser=None, tipo_documento=None):
    qualidade = float((resultado_ocr or {}).get("qualidade") or 0)
    limiar_qualidade = 0.60
    if tipo_documento == "comprovante":
        # Comprovante costuma ter menos texto estruturado e mais variação visual.
        # Mantemos o OCR local para casos bons, mas subimos o gatilho da IA quando a leitura vier só "razoável".
        limiar_qualidade = 0.82

    if qualidade < limiar_qualidade:
        return True, "qualidade_ocr_baixa"

    parser = resultado_parser or {}
    campos_obrigatorios = {
        "holerite": ["nome", "valor_liquido"],
        "inss": ["cnpj", "competencia"],
        "fgts": ["competencia"],
        "cartao_ponto": ["nome", "competencia"],
        "folha": ["nome", "competencia", "empresa"],
    }.get(tipo_documento or "", [])

    campos = parser.get("campos") if isinstance(parser, dict) else {}
    faltando = [c for c in campos_obrigatorios if not (campos or {}).get(c)]
    if faltando:
        return True, f"campos_obrigatorios_ausentes:{','.join(faltando)}"

    if isinstance(parser, dict) and parser.get("inconclusivo"):
        return True, "parser_local_inconclusivo"

    if isinstance(parser, dict) and parser.get("competencia_divergente"):
        return True, "competencia_divergente"

    return False, "ocr_local_suficiente"


def montar_payload_ia_economico(tipo_documento, resultado_ocr, resultado_parser, evidencias_visuais=None):
    campos_esperados = {
        "holerite": ["nome", "valor_liquido"],
        "inss": ["cnpj", "competencia", "saldo_a_pagar"],
        "fgts": ["empresa", "competencia", "cno"],
        "cartao_ponto": ["nome", "competencia"],
        "folha": ["nome", "competencia", "empresa"],
    }.get(tipo_documento or "", ["nome", "competencia"])

    texto = (resultado_ocr or {}).get("texto", "")
    trechos = extrair_trechos_relevantes(texto, tipo_documento or "", campos_esperados=campos_esperados, janela=450)

    precisa_ia, motivo = deve_chamar_ia(resultado_ocr, resultado_parser, tipo_documento)

    return {
        "tipo_documento": tipo_documento,
        "campos_esperados": campos_esperados,
        "resultado_local": resultado_parser or {},
        "trechos_relevantes": trechos,
        "evidencias_visuais": evidencias_visuais or {},
        "problema": motivo if precisa_ia else "sem_problema",
    }


def extrair_documento_inteligente(caminho_pdf, tipo_documento=None, max_paginas=None, usar_ocr=True):
    inicio = time.time()

    if not caminho_pdf or not os.path.exists(caminho_pdf):
        return {
            "texto": "",
            "metodo": "falha",
            "qualidade": 0.0,
            "precisa_ia": True,
            "motivo_ia": "arquivo_inexistente",
            "paginas": [],
        }

    doc_hash = _arquivo_hash(caminho_pdf)
    key = _cache_key(caminho_pdf, tipo_documento=tipo_documento, max_paginas=max_paginas, usar_ocr=usar_ocr, doc_hash=doc_hash)
    cache = _load_cache(key)
    if cache:
        cache["cache_hit"] = True
        return cache

    perfil_documento = encontrar_perfil_documento(tipo_documento, caminho_arquivo=caminho_pdf, arquivo_hash=doc_hash)
    perfis_tipo = carregar_perfis(tipo_documento) if tipo_documento else []

    paginas_result = []
    metodo_set = set()

    try:
        with fitz.open(caminho_pdf) as doc:
            total_paginas = len(doc)
            limite = min(total_paginas, max_paginas) if max_paginas else total_paginas

            for i in range(limite):
                page = doc[i]
                txt_nativo = (page.get_text("text") or "").strip()
                q_nativo = calcular_qualidade_texto(txt_nativo, tipo_documento=tipo_documento)

                if q_nativo >= 0.62 or not usar_ocr:
                    paginas_result.append({
                        "pagina": i + 1,
                        "texto": txt_nativo,
                        "metodo": "texto_nativo",
                        "qualidade": q_nativo,
                        "rotacao_corrigida": False,
                    })
                    metodo_set.add("texto_nativo")
                    print(f"[OCR] pagina={i+1} metodo=texto_nativo qualidade={q_nativo}")
                    continue

                dpi = 350 if perfil_documento else (250 if q_nativo > 0.3 else 300)
                img = _render_pagina(page, dpi=dpi)
                if perfil_documento:
                    txt_ocr, q_ocr = _ocr_pagina_com_perfil_layout(img, perfil_documento, tipo_documento=tipo_documento)
                else:
                    txt_ocr, q_ocr = _ocr_pagina_com_perfis(img, tipo_documento=tipo_documento)
                    if tipo_documento == "holerite" and perfis_tipo:
                        texto_referencia = txt_ocr if txt_ocr.strip() else txt_nativo
                        perfil_texto, score_texto = encontrar_perfil_por_texto(tipo_documento, texto_referencia, limite=0.25)
                        if perfil_texto:
                            txt_modelo, q_modelo = _ocr_pagina_com_perfil_layout(img, perfil_texto, tipo_documento=tipo_documento)
                            if q_modelo > q_ocr or (q_modelo == q_ocr and len(txt_modelo) > len(txt_ocr)):
                                txt_ocr, q_ocr = txt_modelo, q_modelo
                                perfil_documento = perfil_texto
                                print(f"[OCR] perfil_holerite_texto={perfil_texto.get('id')} score={score_texto}")

                # tentativa extra em 400 apenas se continuar ruim
                if q_ocr < 0.55:
                    img2 = _render_pagina(page, dpi=400)
                    if perfil_documento:
                        txt2, q2 = _ocr_pagina_com_perfil_layout(img2, perfil_documento, tipo_documento=tipo_documento)
                    else:
                        txt2, q2 = _ocr_pagina_com_perfis(img2, tipo_documento=tipo_documento)
                    if q2 > q_ocr:
                        txt_ocr, q_ocr = txt2, q2

                final_txt = txt_ocr if q_ocr >= q_nativo else txt_nativo
                final_metodo = "tesseract" if q_ocr >= q_nativo else "texto_nativo"
                final_q = max(q_nativo, q_ocr)

                paginas_result.append({
                    "pagina": i + 1,
                    "texto": final_txt,
                    "metodo": final_metodo,
                    "qualidade": round(final_q, 4),
                    "rotacao_corrigida": False,
                })
                metodo_set.add(final_metodo)
                print(f"[OCR] pagina={i+1} metodo={final_metodo} qualidade={round(final_q,4)}")

    except Exception as exc:
        return {
            "texto": "",
            "metodo": "falha",
            "qualidade": 0.0,
            "precisa_ia": True,
            "motivo_ia": f"erro_extracao:{exc}",
            "paginas": [],
        }

    texto = "\n\f\n".join([p.get("texto", "") for p in paginas_result]).strip()
    qualidade_global = round(sum(p.get("qualidade", 0) for p in paginas_result) / max(1, len(paginas_result)), 4)

    if not paginas_result:
        metodo = "falha"
    elif metodo_set == {"texto_nativo"}:
        metodo = "texto_nativo"
    elif metodo_set == {"tesseract"}:
        metodo = "tesseract"
    else:
        metodo = "hibrido"

    precisa_ia, motivo_ia = deve_chamar_ia({"qualidade": qualidade_global, "texto": texto}, resultado_parser=None, tipo_documento=tipo_documento)

    resultado = {
        "texto": texto,
        "metodo": metodo,
        "qualidade": qualidade_global,
        "perfil_ocr": (perfil_documento or {}).get("id"),
        "precisa_ia": bool(precisa_ia),
        "motivo_ia": motivo_ia,
        "paginas": paginas_result,
        "tempo_processamento_s": round(time.time() - inicio, 3),
        "cache_hit": False,
    }

    _save_cache(key, resultado)
    return resultado


def extrair_texto_pdf(caminho_pdf: str) -> str:
    return extrair_documento_inteligente(caminho_pdf).get("texto", "")


def extrair_texto_pdf_folha(caminho_pdf: str) -> str:
    return extrair_documento_inteligente(caminho_pdf, tipo_documento="folha").get("texto", "")


def extrair_texto_pdf_inteligente(caminho_pdf: str) -> str:
    return extrair_documento_inteligente(caminho_pdf).get("texto", "")
