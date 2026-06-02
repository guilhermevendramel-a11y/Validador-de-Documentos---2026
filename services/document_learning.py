import hashlib
import json
import os
import re
from datetime import datetime


LEARNING_PATH = os.path.join(os.getcwd(), "data", "document_learning.json")

ANCHOR_BY_DOC = {
    "cartao_ponto": ["PONTO", "COMPETENCIA", "ENTRADA", "SAIDA", "ASSINATURA"],
    "holerite": ["HOLERITE", "RECIBO", "LIQUIDO", "VENCIMENTOS", "DESCONTOS"],
    "fgts": ["FGTS", "TRABALHADOR", "TOMADOR", "ESTABELECIMENTO", "CNO"],
    "inss": ["DCTFWEB", "DARF", "SALDO A PAGAR", "PERIODO DE APURACAO", "CNPJ"],
    "folha": ["FOLHA", "PAGAMENTO", "PROVENTOS", "DESCONTOS", "LIQUIDO"],
}


def normalizar_texto(texto):
    texto = str(texto or "").upper()
    texto = re.sub(r"\d", "0", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def assinatura_layout(texto):
    normalizado = normalizar_texto(texto)
    recorte = normalizado[:3000]
    return hashlib.sha1(recorte.encode("utf-8", errors="ignore")).hexdigest()


def detectar_ancoras(texto, tipo_documento=None):
    normalizado = normalizar_texto(texto)
    candidatos = [
        "NOME DO FUNCIONARIO", "NOME DO FUNCIONÁRIO", "VALOR LIQUIDO", "VALOR LÍQUIDO",
        "DECLARO TER RECEBIDO", "TOTAL DE VENCIMENTOS", "TOTAL DE DESCONTOS",
        "ASSINATURA DO FUNCIONARIO", "ASSINATURA DO FUNCIONÁRIO", "CNPJ", "CPF",
        "FOLHA MENSAL", "COMPETENCIA", "COMPETÊNCIA", "DCTFWEB", "DARF", "FGTS",
        "TOMADOR", "ESTABELECIMENTO", "CNO", "SALDO A PAGAR",
    ]
    if tipo_documento and tipo_documento in ANCHOR_BY_DOC:
        candidatos.extend(ANCHOR_BY_DOC[tipo_documento])

    vistos = []
    for ancora in candidatos:
        if normalizar_texto(ancora) in normalizado and ancora not in vistos:
            vistos.append(ancora)
    return vistos


def carregar_base():
    if not os.path.exists(LEARNING_PATH):
        return {"layouts": []}
    try:
        with open(LEARNING_PATH, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except Exception:
        return {"layouts": []}


def salvar_base(base):
    os.makedirs(os.path.dirname(LEARNING_PATH), exist_ok=True)
    with open(LEARNING_PATH, "w", encoding="utf-8") as arquivo:
        json.dump(base, arquivo, ensure_ascii=False, indent=2)


def _score_layout(layout, tipo_documento, assinatura, ancoras):
    if layout.get("tipo_documento") != tipo_documento:
        return 0.0

    score = 0.0
    if layout.get("assinatura_layout") == assinatura or layout.get("assinatura") == assinatura:
        score += 0.35

    layout_ancoras = set(layout.get("ancoras_encontradas") or layout.get("ancoras") or [])
    ancoras_set = set(ancoras)
    if layout_ancoras:
        inter = len(layout_ancoras & ancoras_set)
        uniao = max(1, len(layout_ancoras | ancoras_set))
        score += 0.55 * (inter / uniao)

    score += min(0.10, float(layout.get("score_layout") or 0) * 0.10)
    return round(score, 4)


def encontrar_layout(tipo_documento, texto):
    base = carregar_base()
    assinatura = assinatura_layout(texto)
    ancoras = detectar_ancoras(texto, tipo_documento=tipo_documento)

    melhor = None
    melhor_score = 0.0
    for layout in base.get("layouts", []):
        s = _score_layout(layout, tipo_documento, assinatura, ancoras)
        if s > melhor_score:
            melhor = layout
            melhor_score = s

    if melhor and melhor_score >= 0.45:
        return melhor, melhor_score
    return None, 0.0


def aprender_documento(tipo_documento, texto, campos, origem=None):
    base = carregar_base()
    assinatura = assinatura_layout(texto)
    ancoras = detectar_ancoras(texto, tipo_documento=tipo_documento)
    agora = datetime.now().isoformat(timespec="seconds")

    campos = campos or {}
    campos_conhecidos = {
        "nome_colaborador": campos.get("nome_colaborador") or campos.get("nome_holerite") or campos.get("nome"),
        "empresa": campos.get("empresa"),
        "cnpj": campos.get("cnpj"),
        "competencia": campos.get("competencia"),
        "valor_liquido": campos.get("valor_liquido") or campos.get("valor_holerite"),
        "data_pagamento": campos.get("data_pagamento"),
        "cno": campos.get("cno"),
        "saldo_a_pagar": campos.get("saldo_a_pagar"),
        "assinatura": campos.get("assinatura"),
    }

    for layout in base.get("layouts", []):
        if layout.get("tipo_documento") == tipo_documento and (
            layout.get("assinatura_layout") == assinatura or layout.get("assinatura") == assinatura
        ):
            layout["ultimo_uso"] = agora
            exemplos_atual = layout.get("exemplos")
            if isinstance(exemplos_atual, list):
                exemplos_lista = exemplos_atual
                exemplos_count = len(exemplos_lista)
            else:
                exemplos_lista = []
                try:
                    exemplos_count = int(exemplos_atual or 0)
                except Exception:
                    exemplos_count = 0
            exemplos_lista.append(
                {
                    "origem": origem,
                    "data": agora,
                    "campos": campos_conhecidos,
                }
            )
            layout["exemplos"] = exemplos_lista
            layout["exemplos_count"] = exemplos_count + 1
            layout["campos_conhecidos"] = {**(layout.get("campos_conhecidos") or {}), **campos_conhecidos}
            layout["ancoras_encontradas"] = sorted(set((layout.get("ancoras_encontradas") or []) + ancoras))
            layout["score_layout"] = min(1.0, float(layout.get("score_layout") or 0.5) + 0.02)
            salvar_base(base)
            return layout, False

    nome_modelo = f"{tipo_documento}_{len(base.get('layouts', [])) + 1:03d}"
    layout = {
        "modelo": nome_modelo,
        "tipo_documento": tipo_documento,
        "assinatura_layout": assinatura,
        "assinatura": assinatura,
        "assinatura_layout_tipo": "hash_recorte",
        "ancoras_encontradas": ancoras,
        "campos_conhecidos": campos_conhecidos,
        "regex_por_campo": {},
        "exemplos": [
            {
                "origem": origem,
                "data": agora,
                "campos": campos_conhecidos,
            }
        ],
        "origem": origem,
        "criado_em": agora,
        "ultimo_uso": agora,
        "score_layout": 0.5,
    }

    base.setdefault("layouts", []).append(layout)
    salvar_base(base)
    return layout, True
