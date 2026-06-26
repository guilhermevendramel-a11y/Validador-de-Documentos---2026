import re
import unicodedata
from dataclasses import asdict, is_dataclass

from utils.gemini.folha import extrair_folha_inteligente
from utils.ocr import deve_chamar_ia, extrair_documento_inteligente, montar_payload_ia_economico
from validators.folha_pagamento.folha_model_extractor import extrair_folha_pagamento_de_texto as extrair_folha_modelo_de_texto
from validators.folha_pagamento.parser_folha_cabecalho_nome import extrair_dados_folha_cabecalho_nome, eh_layout_folha_cabecalho_nome
from validators.folha_pagamento.parser_folha_delphos import extrair_dados_folha_delphos, eh_layout_folha_delphos
from validators.folha_pagamento.parser_folha_femav import extrair_dados_folha_femav, eh_layout_folha_femav
from validators.folha_pagamento.parser_folha_analitica import extrair_dados_folha_analitica, eh_layout_folha_analitica
from validators.folha_pagamento.parser_espelho_resumo_folha import extrair_dados_espelho_resumo_folha, eh_layout_espelho_resumo_folha
from validators.folha_pagamento.parser_extrato_mensal import extrair_dados_extrato_mensal, eh_layout_extrato_mensal
from validators.folha_pagamento.parser_relacao_calculo import extrair_dados_relacao_calculo, eh_layout_relacao_calculo
from validators.folha_pagamento.parser_scivisual import extrair_dados_scivisual, eh_layout_scivisual
from validators.folha_pagamento.regras import (
    extrair_colaboradores,
    extrair_competencia_folha,
    extrair_empresa,
    nome_valido,
)
from validators.folha_pagamento.rules import validar_folha


def _normalizar_texto_ordem(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto).upper().strip()
    return texto


def _ordenar_colaboradores_por_texto(colaboradores, texto_base):
    texto_norm = _normalizar_texto_ordem(texto_base)
    ordenados = []
    for idx, item in enumerate(colaboradores or []):
        nome = item.get("nome") if isinstance(item, dict) else str(item)
        nome = (nome or "").strip()
        if not nome:
            continue
        nome_norm = _normalizar_texto_ordem(nome)
        m = re.search(rf"\b{re.escape(nome_norm)}\b", texto_norm)
        pos = m.start() if m else len(texto_norm) + idx
        ordenados.append((pos, idx, {"nome": nome}))

    ordenados.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ordenados]


def _fallback_dados_folha(empresa, competencia, colaboradores):
    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": [
            {
                "nome": item.get("nome") if isinstance(item, dict) else str(item),
            }
            for item in (colaboradores or [])
            if (item.get("nome") if isinstance(item, dict) else str(item))
        ],
    }


def _fallback_dados_modelo_folha(dados_modelo):
    dados_modelo = dados_modelo or {}
    colaboradores = []
    for item in dados_modelo.get("nomes") or []:
        nome = (item or "").strip()
        if nome:
            colaboradores.append({"nome": nome})
    return {
        "empresa": dados_modelo.get("razao_social") or "",
        "competencia": dados_modelo.get("competencia") or "",
        "colaboradores": colaboradores,
        "modelo": dados_modelo.get("modelo") or "",
        "confianca_modelo": dados_modelo.get("confianca_modelo"),
        "evidencias": dados_modelo.get("evidencias") or {},
        "avisos": dados_modelo.get("avisos") or [],
    }


def _mesclar_colaboradores(*listas):
    vistos = set()
    resultado = []
    for lista in listas:
        for item in lista or []:
            if isinstance(item, dict):
                nome = (item.get("nome") or "").strip()
                registro = {k: v for k, v in item.items() if k != "nome"}
            else:
                nome = str(item or "").strip()
                registro = {}
            if not nome:
                continue
            chave = nome.upper()
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append({"nome": nome, **registro})
    return resultado


def _empresa_parece_razao_social(valor, colaboradores):
    valor = (valor or "").strip()
    if not valor:
        return False
    empresa_norm = valor.upper()
    if any((c.get("nome") or "").strip().upper() == empresa_norm for c in (colaboradores or [])):
        return False
    indicadores_empresa = (
        "LTDA", "EIRELI", "EPP", "ME", "S/A", "SA", "EMPRESA", "SERVICOS", "SERVIÇOS",
        "CONSTRUCOES", "CONSTRUÇÕES", "LOCACOES", "LOCAÇÕES", "INDUSTRIA", "INDÚSTRIA",
        "COMERCIO", "COMÉRCIO", "CONSULTORIA", "ENGENHARIA", "MONTAGEM", "TRANSPORTES",
        "OBRAS", "MAQUINAS", "EQUIPAMENTOS", "HIDRAULICA", "HIDRÁULICA",
    )
    return any(ind in empresa_norm for ind in indicadores_empresa)


def _normalizar_saida_modelo_folha(dados_modelo):
    if not dados_modelo:
        return {}
    if is_dataclass(dados_modelo):
        return asdict(dados_modelo)
    if isinstance(dados_modelo, dict):
        return dados_modelo
    return {}


def processar_folha_pagamento(caminho_arquivo, competencia_esperada=None):
    ocr_result = extrair_documento_inteligente(caminho_arquivo, tipo_documento="folha", usar_ocr=True)
    texto = ocr_result.get("texto", "")

    if not texto or len(texto.strip()) < 50:
        return {
            "status": "Erro",
            "mensagem": "Falha no OCR",
            "empresa": None,
            "competencia": None,
            "competencia_ok": False,
            "colaboradores": [],
            "erros": ["OCR vazio"],
            "avisos": [],
        }

    texto_primeira_pagina = ""
    paginas_ocr = ocr_result.get("paginas") or []
    if paginas_ocr and isinstance(paginas_ocr, list):
        texto_primeira_pagina = (paginas_ocr[0] or {}).get("texto", "") if isinstance(paginas_ocr[0], dict) else ""

    dados_modelo = _normalizar_saida_modelo_folha(extrair_folha_modelo_de_texto(texto) if texto else {})
    dados_cabecalho = extrair_dados_folha_cabecalho_nome(texto) if eh_layout_folha_cabecalho_nome(texto) else {}
    dados_delphos = extrair_dados_folha_delphos(texto) if eh_layout_folha_delphos(texto) else {}
    dados_femav = extrair_dados_folha_femav(texto) if eh_layout_folha_femav(texto) else {}
    dados_analitica = extrair_dados_folha_analitica(texto) if eh_layout_folha_analitica(texto) else {}
    dados_espelho = extrair_dados_espelho_resumo_folha(texto) if eh_layout_espelho_resumo_folha(texto) else {}
    dados_extrato = extrair_dados_extrato_mensal(texto) if eh_layout_extrato_mensal(texto) else {}
    dados_relacao = extrair_dados_relacao_calculo(texto) if eh_layout_relacao_calculo(texto) else {}
    dados_scivisual = extrair_dados_scivisual(texto) if eh_layout_scivisual(texto) else {}

    competencia_doc = (
        dados_cabecalho.get("competencia")
        or
        dados_delphos.get("competencia")
        or
        dados_femav.get("competencia")
        or
        dados_analitica.get("competencia")
        or
        dados_espelho.get("competencia")
        or
        dados_extrato.get("competencia")
        or dados_relacao.get("competencia")
        or dados_scivisual.get("competencia")
        or dados_modelo.get("competencia")
        or extrair_competencia_folha(texto_primeira_pagina)
        or extrair_competencia_folha(texto)
    )
    empresa_ocr = (
        dados_cabecalho.get("empresa")
        or
        dados_delphos.get("empresa")
        or
        dados_femav.get("empresa")
        or
        dados_analitica.get("empresa")
        or
        dados_espelho.get("empresa")
        or
        dados_extrato.get("empresa")
        or dados_relacao.get("empresa")
        or dados_scivisual.get("empresa")
        or dados_modelo.get("razao_social")
        or extrair_empresa(texto)
    )
    colaboradores_modelo = _fallback_dados_modelo_folha(dados_modelo).get("colaboradores")
    colaboradores_parser = _mesclar_colaboradores(
        dados_cabecalho.get("colaboradores"),
        dados_delphos.get("colaboradores"),
        dados_femav.get("colaboradores"),
        dados_analitica.get("colaboradores"),
        dados_espelho.get("colaboradores"),
        dados_extrato.get("colaboradores"),
        dados_relacao.get("colaboradores"),
        dados_scivisual.get("colaboradores"),
        extrair_colaboradores(texto, empresa_ocr),
    )
    base_ocr = _mesclar_colaboradores(colaboradores_parser, colaboradores_modelo)
    colaboradores_paginas = []
    for pagina in paginas_ocr:
        if isinstance(pagina, dict):
            texto_pagina = pagina.get("texto", "")
            if texto_pagina:
                colaboradores_paginas.extend(extrair_colaboradores(texto_pagina, empresa_ocr))
    base_ocr = _mesclar_colaboradores(base_ocr, colaboradores_paginas)
    if not base_ocr:
        base_ocr = colaboradores_modelo or colaboradores_parser

    if not _empresa_parece_razao_social(empresa_ocr, base_ocr):
        empresa_ocr = ""

    parser_local = {
        "campos": {
            "competencia": bool(competencia_doc),
            "empresa": bool(empresa_ocr),
            "nome": bool(base_ocr),
        },
        "inconclusivo": not base_ocr or not competencia_doc or not empresa_ocr,
    }
    chamar_ia, motivo_ia = deve_chamar_ia(ocr_result, parser_local, tipo_documento="folha")

    payload_ia = montar_payload_ia_economico("folha", ocr_result, parser_local)
    dados_ia = {}
    if chamar_ia:
        try:
            texto_ia = "\n".join([t.get("trecho", "") for t in payload_ia.get("trechos_relevantes", [])]) or texto
            dados_ia = extrair_folha_inteligente(texto_ia)
        except Exception:
            dados_ia = {}

    if not isinstance(dados_ia, dict):
        dados_ia = {}

    if not dados_ia and base_ocr:
        dados_ia = _fallback_dados_folha(empresa_ocr, competencia_doc, base_ocr)

    colaboradores_ia = dados_ia.get("colaboradores") or []
    base = colaboradores_ia if colaboradores_ia else base_ocr

    nomes_vistos, lista_final = set(), []
    for c in base:
        nome = c.get("nome") if isinstance(c, dict) else str(c)
        nome = (nome or "").strip().upper()
        if nome_valido(nome, empresa_ocr) and nome not in nomes_vistos:
            nomes_vistos.add(nome)
            lista_final.append({"nome": nome})

    lista_final = _ordenar_colaboradores_por_texto(lista_final, texto)

    competencia_final = competencia_doc or dados_ia.get("competencia")
    competencia_ok = True if not competencia_esperada else bool(competencia_final) and competencia_final == competencia_esperada

    resultado_rules = validar_folha(dados_ia, competencia_esperada)

    if resultado_rules.get("status") == "Reprovado" and lista_final:
        status, mensagem = "Parcial", f"{len(lista_final)} colaborador(es)"
    elif resultado_rules.get("status") == "Reprovado":
        status, mensagem = "Reprovado", "Folha com inconsistências"
    elif resultado_rules.get("status") == "Parcial":
        status, mensagem = "Parcial", "Folha com pendências"
    else:
        status, mensagem = "Aprovado", f"{len(lista_final)} colaborador(es)"

    empresa_final = empresa_ocr or dados_ia.get("empresa")

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
        "ia_fallback": bool(chamar_ia),
        "ia_motivo": motivo_ia,
        "ia_payload": payload_ia,
        "folha_modelo": dados_modelo.get("modelo"),
        "folha_confianca_modelo": dados_modelo.get("confianca_modelo"),
        "folha_evidencias": dados_modelo.get("evidencias") or {},
        "folha_avisos": dados_modelo.get("avisos") or [],
    }
