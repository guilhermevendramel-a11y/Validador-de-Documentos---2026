import hashlib
import json
import os
import re
from datetime import datetime


LEARNING_PATH = os.path.join(os.getcwd(), "data", "document_learning.json")


def normalizar_texto(texto):
    texto = str(texto or "").upper()
    texto = re.sub(r"\d", "0", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def assinatura_layout(texto):
    normalizado = normalizar_texto(texto)
    recorte = normalizado[:3000]
    return hashlib.sha1(recorte.encode("utf-8", errors="ignore")).hexdigest()


def detectar_ancoras(texto):
    normalizado = normalizar_texto(texto)
    candidatos = [
        "NOME DO FUNCIONARIO",
        "NOME DO FUNCIONÁRIO",
        "VALOR LIQUIDO",
        "VALOR LÍQUIDO",
        "DECLARO TER RECEBIDO",
        "TOTAL DE VENCIMENTOS",
        "TOTAL DE DESCONTOS",
        "ASSINATURA DO FUNCIONARIO",
        "ASSINATURA DO FUNCIONÁRIO",
        "CNPJ",
        "CPF",
        "FOLHA MENSAL",
        "COMPETENCIA",
        "COMPETÊNCIA",
    ]
    return [ancora for ancora in candidatos if normalizar_texto(ancora) in normalizado]


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


def encontrar_layout(tipo_documento, texto):
    base = carregar_base()
    assinatura = assinatura_layout(texto)
    ancoras = set(detectar_ancoras(texto))

    melhor = None
    melhor_score = 0

    for layout in base.get("layouts", []):
        if layout.get("tipo_documento") != tipo_documento:
            continue

        if layout.get("assinatura") == assinatura:
            return layout, 1.0

        layout_ancoras = set(layout.get("ancoras") or [])
        if not layout_ancoras:
            continue

        score = len(ancoras & layout_ancoras) / max(len(layout_ancoras), 1)
        if score > melhor_score:
            melhor = layout
            melhor_score = score

    if melhor and melhor_score >= 0.7:
        return melhor, melhor_score

    return None, 0


def aprender_documento(tipo_documento, texto, campos, origem=None):
    base = carregar_base()
    assinatura = assinatura_layout(texto)
    ancoras = detectar_ancoras(texto)
    agora = datetime.now().isoformat(timespec="seconds")

    for layout in base.get("layouts", []):
        if layout.get("tipo_documento") == tipo_documento and layout.get("assinatura") == assinatura:
            layout["ultimo_uso"] = agora
            layout["exemplos"] = int(layout.get("exemplos") or 0) + 1
            layout["campos"] = {**(layout.get("campos") or {}), **(campos or {})}
            salvar_base(base)
            return layout, False

    nome_modelo = f"{tipo_documento}_{len(base.get('layouts', [])) + 1:03d}"
    layout = {
        "modelo": nome_modelo,
        "tipo_documento": tipo_documento,
        "assinatura": assinatura,
        "ancoras": ancoras,
        "campos": campos or {},
        "origem": origem,
        "criado_em": agora,
        "ultimo_uso": agora,
        "exemplos": 1,
    }

    base.setdefault("layouts", []).append(layout)
    salvar_base(base)
    return layout, True
