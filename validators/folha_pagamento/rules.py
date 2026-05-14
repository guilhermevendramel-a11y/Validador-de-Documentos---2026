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
    total_ia = normalizar_valor(dados_ia.get("valor_total_folha"))

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
    # 4. VALORES
    # ============================================================
    soma_calculada = 0
    colaboradores_com_valor = 0

    for c in colaboradores:
        salario = normalizar_valor(c.get("salario_base"))
        liquido = normalizar_valor(c.get("liquido"))

        if liquido:
            soma_calculada += liquido
            colaboradores_com_valor += 1

        elif salario:
            soma_calculada += salario
            colaboradores_com_valor += 1

        else:
            avisos.append(f"Sem valores: {c.get('nome')}")

    # ============================================================
    # 5. TOTAL DA FOLHA
    # ============================================================
    if total_ia is None:
        avisos.append("Total da folha não identificado")

    elif soma_calculada > 0:
        diferenca = abs(soma_calculada - total_ia)

        if diferenca > 2:
            erros.append(
                f"Total divergente (Calculado: {round(soma_calculada,2)} vs Documento: {total_ia})"
            )

    # ============================================================
    # 🔥 6. FILTRO INTELIGENTE (REGRA FINAL)
    # ============================================================

    avisos_relevantes = []

    for a in avisos:

        # ❌ ignora avisos da IA
        if "IA" in a:
            continue

        # ❌ ignora total da folha (não crítico)
        if "Total da folha" in a:
            continue

        avisos_relevantes.append(a)

    # ============================================================
    # 🚀 7. STATUS FINAL
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
            "total_calculado": round(soma_calculada, 2),
            "total_documento": total_ia,
            "colaboradores_processados": len(colaboradores),
            "colaboradores_com_valor": colaboradores_com_valor
        }
    }