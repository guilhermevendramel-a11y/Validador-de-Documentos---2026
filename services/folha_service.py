import re

from utils.gemini.folha import extrair_folha_inteligente
from utils.ocr import deve_chamar_ia, extrair_documento_inteligente, montar_payload_ia_economico
from validators.folha_pagamento.rules import validar_folha


def extrair_competencia(texto):
    if not texto:
        return None
    texto = texto.upper()
    m = re.search(r"PER[ÍI]ODO\s*:\s*(\d{2})\/(\d{2})\/(\d{4})\s+A\s+(\d{2})\/(\d{2})\/(\d{4})", texto)
    if m:
        return f"{m.group(2)}/{m.group(3)}"
    m = re.search(r"\b(0[1-9]|1[0-2])/\d{4}\b", texto)
    return m.group() if m else None


def extrair_empresa(texto):
    if not texto:
        return None
    texto = texto.upper()
    m = re.search(r"RAZ[AÃ]O\s+SOCIAL[:\s]+([A-Z0-9 .&/-]{5,})", texto)
    if m:
        return m.group(1).strip()
    return None


def nome_valido(nome, empresa=None):
    if not nome:
        return False
    nome = nome.strip().upper()
    if len(nome) < 10 or re.search(r"\d", nome) or len(nome.split()) < 2:
        return False
    if empresa and nome == empresa:
        return False
    proibidas = ["FOLHA", "CNPJ", "PERIODO", "TOTAL", "DESCONTOS", "PROVENTOS", "EMPRESA"]
    return not any(p in nome for p in proibidas)


def extrair_colaboradores(texto, empresa=None):
    linhas = texto.split("\n")
    nomes = []
    for linha in linhas:
        linha = linha.strip().upper()
        if nome_valido(linha, empresa):
            nomes.append(linha)
    return nomes


def processar_folha_pagamento(caminho_arquivo, competencia_esperada=None):
    ocr_result = extrair_documento_inteligente(caminho_arquivo, tipo_documento="folha", usar_ocr=True)
    texto = ocr_result.get("texto", "")

    if not texto or len(texto.strip()) < 50:
        return {"status": "Erro", "mensagem": "Falha no OCR", "empresa": None, "competencia": None, "competencia_ok": False, "colaboradores": [], "erros": ["OCR vazio"], "avisos": []}

    competencia_doc = extrair_competencia(texto)
    empresa_ocr = extrair_empresa(texto)
    base_ocr = extrair_colaboradores(texto, empresa_ocr)

    parser_local = {
        "campos": {"competencia": competencia_doc, "empresa": empresa_ocr, "nome": base_ocr[0] if base_ocr else None},
        "inconclusivo": len(base_ocr) == 0,
    }
    chamar_ia, motivo_ia = deve_chamar_ia(ocr_result, parser_local, tipo_documento="folha")

    dados_ia = {}
    payload_ia = None
    if chamar_ia:
        payload_ia = montar_payload_ia_economico("folha", ocr_result, parser_local)
        try:
            dados_ia = extrair_folha_inteligente("\n".join([t.get("trecho", "") for t in payload_ia.get("trechos_relevantes", [])]) or texto)
        except Exception:
            dados_ia = {}
    if not isinstance(dados_ia, dict):
        dados_ia = {}

    colaboradores_ia = dados_ia.get("colaboradores") or []
    base = colaboradores_ia if colaboradores_ia else base_ocr

    nomes_vistos, lista_final = set(), []
    for c in base:
        nome = c.get("nome") if isinstance(c, dict) else str(c)
        nome = (nome or "").strip().upper()
        if nome_valido(nome, empresa_ocr) and nome not in nomes_vistos:
            nomes_vistos.add(nome)
            lista_final.append({"nome": nome})

    competencia_final = competencia_doc or dados_ia.get("competencia")
    competencia_ok = True if not competencia_esperada else bool(competencia_final) and competencia_final == competencia_esperada

    resultado_rules = validar_folha(dados_ia, competencia_esperada)

    if resultado_rules.get("status") == "Reprovado":
        status, mensagem = "Reprovado", "Folha com inconsistências"
    elif resultado_rules.get("status") == "Parcial":
        status, mensagem = "Parcial", "Folha com pendências"
    else:
        status, mensagem = "Aprovado", f"{len(lista_final)} colaborador(es)"

    empresa_final = dados_ia.get("empresa") or empresa_ocr

    return {
        "status": status,
        "mensagem": mensagem,
        "empresa": empresa_final,
        "competencia": competencia_final,
        "competencia_ok": competencia_ok,
        "colaboradores": lista_final,
        "erros": resultado_rules.get("erros", []),
        "avisos": resultado_rules.get("avisos", []),
        "ocr_metodo": ocr_result.get("metodo"),
        "ocr_qualidade": ocr_result.get("qualidade"),
        "ia_fallback": chamar_ia,
        "ia_motivo": motivo_ia,
        "ia_payload": payload_ia,
    }
