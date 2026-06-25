def normalizar_valor(v):
    try:
        if v is None:
            return None

        if isinstance(v, str):
            v = v.replace(".", "").replace(",", ".")

        return float(v)
    except:
        return None


def validar_folha(dados_ia, competencia_esperada=None):

    erros = []
    avisos = []

    if not isinstance(dados_ia, dict):
        dados_ia = {}

    empresa = dados_ia.get("empresa")
    competencia = dados_ia.get("competencia")
    colaboradores = dados_ia.get("colaboradores") or []

    # ============================================================
    # 1. EMPRESA (IA = opcional)
    # ============================================================
    if not empresa:
        avisos.append("Empresa não identificada via IA")

    # ============================================================
    # 2. COMPETÊNCIA (SÓ DIVERGÊNCIA REPROVA)
    # ============================================================
    if not competencia:
        avisos.append("Competência não identificada via IA")

    elif competencia_esperada and competencia != competencia_esperada:
        erros.append(f"Competência divergente ({competencia} != {competencia_esperada})")

    # ============================================================
    # 3. COLABORADORES (IA opcional)
    # ============================================================
    if not colaboradores:
        avisos.append("IA não identificou colaboradores")

    nomes_vazios = [c for c in colaboradores if not c.get("nome")]
    if nomes_vazios:
        avisos.append("Existem colaboradores sem nome")

    # ============================================================
    # 🔥 4. FILTRO INTELIGENTE (REGRA FINAL)
    # ============================================================

    avisos_relevantes = []

    for a in avisos:

        # ❌ ignora avisos da IA
        if "IA" in a:
            continue

        avisos_relevantes.append(a)

    # ============================================================
    # 🚀 5. STATUS FINAL
    # ============================================================
    if erros:
        status = "Reprovado"

    elif avisos_relevantes:
        status = "Parcial"

    else:
        status = "Aprovado"

    return {
        "status": status,
        "erros": erros,
        "avisos": avisos,
        "resumo": {
            "empresa": empresa,
            "competencia": competencia,
            "colaboradores_processados": len(colaboradores),
        }
    }
