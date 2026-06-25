import os

from utils.gemini.fgts import extrair_fgts
from utils.ocr import deve_chamar_ia, extrair_documento_inteligente, montar_payload_ia_economico
from utils.ocr.ocr_fgts import extrair_texto_fgts
from utils.validations import extrair_competencia, limpar
from validators.fgts.secoes import dividir_secoes
from validators.fgts.trabalhadores import extrair_trabalhadores


def normalizar_cnpj(valor):
    if not valor:
        return ""
    return "".join(filter(str.isdigit, valor))


def processar_fgts(caminho_relatorio, caminho_guia=None, cno_digitado=None, competencia_digitada=None):
    print("\n[FGTS] ================= FGTS SERVICE =================")

    ocr_relatorio = extrair_documento_inteligente(caminho_relatorio, tipo_documento="fgts", usar_ocr=True)
    texto_relatorio = limpar(ocr_relatorio.get("texto", ""))

    if not texto_relatorio:
        return {"status": "Reprovado", "mensagem": "Falha ao ler relatório FGTS.", "sucesso": False}

    secoes = dividir_secoes(texto_relatorio)
    bloco_trabalhadores = secoes.get("trabalhadores", "")
    trabalhadores = extrair_trabalhadores(bloco_trabalhadores)

    resultado_parser_local = {
        "campos": {
            "competencia": extrair_competencia(texto_relatorio),
            "cno": cno_digitado,
        },
        "inconclusivo": len(trabalhadores) == 0,
    }

    chamar_ia, motivo_ia = deve_chamar_ia(ocr_relatorio, resultado_parser_local, tipo_documento="fgts")
    print(f"[FGTS] IA fallback? {'sim' if chamar_ia else 'nao'} motivo={motivo_ia}")

    dados_relatorio = {}
    payload_ia = None
    if chamar_ia:
        payload_ia = montar_payload_ia_economico("fgts", ocr_relatorio, resultado_parser_local)
        try:
            dados_relatorio = extrair_fgts("\n".join([t.get("trecho", "") for t in payload_ia.get("trechos_relevantes", [])]) or texto_relatorio)
        except Exception as e:
            print(f"[FGTS] Erro Gemini fallback: {e}")
            dados_relatorio = {}

    if not isinstance(dados_relatorio, dict):
        dados_relatorio = {}

    tomadores = dados_relatorio.get("tomadores", [])
    if trabalhadores:
        if not tomadores:
            tomadores = [{"cnpj_ou_cno": cno_digitado or "", "colaboradores": trabalhadores}]
        else:
            for t in tomadores:
                t["colaboradores"] = trabalhadores

    dados_guia = {}
    if caminho_guia:
        texto_guia = limpar(extrair_texto_fgts(caminho_guia))
        if texto_guia:
            guia_local = {"campos": {"competencia": extrair_competencia(texto_guia)}}
            guia_ocr = extrair_documento_inteligente(caminho_guia, tipo_documento="fgts", usar_ocr=True)
            chama_guia_ia, _ = deve_chamar_ia(guia_ocr, guia_local, tipo_documento="fgts")
            if chama_guia_ia:
                try:
                    dados_guia = extrair_fgts(texto_guia)
                except Exception:
                    dados_guia = {}

    tomador_encontrado = None
    cno_digitado_norm = normalizar_cnpj(cno_digitado)
    for t in tomadores:
        cno_doc = normalizar_cnpj(t.get("cnpj_ou_cno"))
        if cno_digitado_norm and cno_digitado_norm in cno_doc:
            tomador_encontrado = t
            break

    colaboradores = tomador_encontrado.get("colaboradores", []) if tomador_encontrado else []

    texto_upper = texto_relatorio.upper()
    documentos_status = {
        "relacao_trabalhadores": "RELAÇÃO DE TRABALHADORES" in texto_upper or "RELAÃ‡ÃƒO DE TRABALHADORES" in texto_upper,
        "relacao_categorias": "RELAÇÃO DE CATEGORIAS" in texto_upper or "RELAÃ‡ÃƒO DE CATEGORIAS" in texto_upper,
        "relacao_estabelecimentos": "RELAÇÃO DE ESTABELECIMENTOS" in texto_upper or "RELAÃ‡ÃƒO DE ESTABELECIMENTOS" in texto_upper,
        "relacao_tipo_valor": "RELAÇÃO DE TIPOS DE VALOR" in texto_upper or "RELAÃ‡ÃƒO DE TIPOS DE VALOR" in texto_upper,
        "relacao_tomadores": "RELAÇÃO DE TOMADORES" in texto_upper or "RELAÇÃO DE TOMADORES DE SERVIÇO" in texto_upper or "RELAÃ‡ÃƒO DE TOMADORES" in texto_upper,
    }

    competencia_doc = dados_relatorio.get("competencia") or extrair_competencia(texto_relatorio)
    competencia_ok = True if not competencia_digitada else competencia_digitada == competencia_doc

    if not documentos_status["relacao_trabalhadores"]:
        status = "Reprovado"
        mensagem = "Documento não possui relação de trabalhadores."
    elif not tomador_encontrado:
        status = "Reprovado"
        mensagem = "Tomador não encontrado no documento."
    elif not colaboradores:
        status = "Parcial"
        mensagem = "Tomador encontrado, mas sem colaboradores."
    else:
        status = "Aprovado"
        mensagem = f"{len(colaboradores)} colaborador(es) encontrados."

    return {
        "status": status,
        "mensagem": mensagem,
        "sucesso": True,
        "dados": {
            "empresa": dados_relatorio.get("empresa"),
            "competencia": competencia_doc,
            "competencia_ok": competencia_ok,
            "tomador_encontrado": bool(tomador_encontrado),
            "cno_digitado": cno_digitado,
            "colaboradores": colaboradores,
            "documentos": documentos_status,
            "ocr_metodo": ocr_relatorio.get("metodo"),
            "ocr_qualidade": ocr_relatorio.get("qualidade"),
            "ia_fallback": chamar_ia,
            "ia_motivo": motivo_ia,
            "ia_payload": payload_ia,
        },
    }
