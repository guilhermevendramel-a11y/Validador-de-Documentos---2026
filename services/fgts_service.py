import os
from utils.ocr.ocr_fgts import extrair_texto_fgts
from utils.gemini.fgts import extrair_fgts
from utils.validations import limpar, extrair_competencia

from validators.fgts.secoes import dividir_secoes
from validators.fgts.trabalhadores import extrair_trabalhadores


# ==========================================================
# 🔧 UTIL
# ==========================================================

def normalizar_cnpj(valor):
    if not valor:
        return ""
    return "".join(filter(str.isdigit, valor))


# ==========================================================
# 🚀 SERVICE PRINCIPAL
# ==========================================================

def processar_fgts(
    caminho_relatorio,
    caminho_guia=None,
    cno_digitado=None,
    competencia_digitada=None
):
    print("\n🚀 ================= FGTS SERVICE =================")

    # ======================================================
    # 1. OCR RELATÓRIO
    # ======================================================
    print("📄 [FGTS] Lendo relatório...")

    texto_relatorio = extrair_texto_fgts(caminho_relatorio)

    if not texto_relatorio:
        return {
            "status": "Reprovado",
            "mensagem": "Falha ao ler relatório FGTS.",
            "sucesso": False
        }

    texto_relatorio = limpar(texto_relatorio)

    # ======================================================
    # 2. PARSER ESTRUTURADO (PRINCIPAL)
    # ======================================================
    print("🧠 [FGTS] Usando parser estruturado...")

    secoes = dividir_secoes(texto_relatorio)
    bloco_trabalhadores = secoes.get("trabalhadores", "")

    trabalhadores = extrair_trabalhadores(bloco_trabalhadores)

    print(f"👥 Trabalhadores encontrados: {len(trabalhadores)}")

    # ======================================================
    # 3. FALLBACK GEMINI (APENAS APOIO)
    # ======================================================
    print("🤖 [FGTS] Executando Gemini (fallback)...")

    try:
        dados_relatorio = extrair_fgts(texto_relatorio)
    except Exception as e:
        print(f"❌ Erro Gemini: {e}")
        dados_relatorio = {}

    if not isinstance(dados_relatorio, dict):
        dados_relatorio = {}

    # ======================================================
    # 4. TOMADORES (PRIORIDADE PARSER)
    # ======================================================
    tomadores = dados_relatorio.get("tomadores", [])

    # 🔥 Parser SEMPRE manda
    if trabalhadores:
        print("🔥 [FGTS] Usando dados do parser (prioridade)")

        if not tomadores:
            tomadores = [{
                "cnpj_ou_cno": cno_digitado or "",
                "colaboradores": trabalhadores
            }]
        else:
            # injeta trabalhadores no tomador existente
            for t in tomadores:
                t["colaboradores"] = trabalhadores

    # ======================================================
    # 5. OCR GUIA (OPCIONAL)
    # ======================================================
    dados_guia = {}

    if caminho_guia:
        print("📄 [FGTS] Processando guia...")

        texto_guia = extrair_texto_fgts(caminho_guia)
        texto_guia = limpar(texto_guia)

        try:
            dados_guia = extrair_fgts(texto_guia)
        except:
            dados_guia = {}

    # ======================================================
    # 6. VALIDAR TOMADOR
    # ======================================================
    tomador_encontrado = None
    cno_digitado_norm = normalizar_cnpj(cno_digitado)

    for t in tomadores:
        cno_doc = normalizar_cnpj(t.get("cnpj_ou_cno"))

        # 🔥 comparação mais robusta
        if cno_digitado_norm and cno_digitado_norm in cno_doc:
            tomador_encontrado = t
            break

    # ======================================================
    # 7. COLABORADORES
    # ======================================================
    colaboradores = []

    if tomador_encontrado:
        colaboradores = tomador_encontrado.get("colaboradores", [])

    # ======================================================
    # 8. DETECÇÃO DE DOCUMENTOS (SEM IA)
    # ======================================================
    texto_upper = texto_relatorio.upper()

    documentos_status = {
        "relacao_trabalhadores": "RELAÇÃO DE TRABALHADORES" in texto_upper,
        "relacao_categorias": "RELAÇÃO DE CATEGORIAS" in texto_upper,
        "relacao_estabelecimentos": "RELAÇÃO DE ESTABELECIMENTOS" in texto_upper,
        "relacao_tipo_valor": "RELAÇÃO DE TIPOS DE VALOR" in texto_upper,
        "relacao_tomadores": "RELAÇÃO DE TOMADORES" in texto_upper,
    }

    # ======================================================
    # 9. COMPETÊNCIA
    # ======================================================
    competencia_doc = (
        dados_relatorio.get("competencia")
        or extrair_competencia(texto_relatorio)
    )

    competencia_ok = True
    if competencia_digitada:
        competencia_ok = competencia_digitada == competencia_doc

    # ======================================================
    # 10. STATUS FINAL
    # ======================================================
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

    print(f"✅ [FGTS] STATUS: {status}")
    print("================================================\n")

    # ======================================================
    # 11. RETORNO FINAL
    # ======================================================
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
            "documentos": documentos_status
        }
    }