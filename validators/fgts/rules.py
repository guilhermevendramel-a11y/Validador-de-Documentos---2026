def normalizar_doc(doc):
    if not doc:
        return ""
    return "".join(filter(str.isdigit, str(doc)))


def validar_fgts(relatorio, guia, comprovante, competencia_input, tomador_input=None):

    erros = []
    avisos = []

    # =========================================
    # 1. DOCUMENTOS DETECTADOS (IA)
    # =========================================
    docs = relatorio.get("documentos_detectados", {})

    if not docs.get("relacao_trabalhadores"):
        erros.append("Relatório sem Relação de Trabalhadores")

    if not docs.get("relacao_categorias"):
        erros.append("Relatório sem Relação de Categorias")

    if not docs.get("relacao_estabelecimentos"):
        erros.append("Relatório sem Relação de Estabelecimentos")

    if not docs.get("relacao_tipo_valor"):
        erros.append("Relatório sem Relação de Tipos de Valor")

    if not docs.get("relacao_tomadores"):
        erros.append("Relatório sem Relação de Tomadores")

    # =========================================
    # 2. EMPRESA
    # =========================================
    if not relatorio.get("empresa"):
        erros.append("Empresa não identificada no relatório")

    if not guia.get("empresa"):
        erros.append("Empresa não identificada na guia")

    if relatorio.get("empresa") and guia.get("empresa"):
        if relatorio["empresa"].strip().upper() != guia["empresa"].strip().upper():
            erros.append("Empresa divergente entre relatório e guia")

    # =========================================
    # 3. COMPETÊNCIA
    # =========================================
    comp_rel = relatorio.get("competencia")
    comp_guia = guia.get("competencia")

    if not comp_rel:
        erros.append("Competência não encontrada no relatório")

    if not comp_guia:
        erros.append("Competência não encontrada na guia")

    if comp_rel and competencia_input:
        if comp_rel != competencia_input:
            erros.append(f"Competência do relatório divergente ({comp_rel})")

    if comp_guia and competencia_input:
        if comp_guia != competencia_input:
            erros.append(f"Competência da guia divergente ({comp_guia})")

    # =========================================
    # 4. VALOR TOTAL
    # =========================================
    valor_rel = relatorio.get("valor_total", 0)
    valor_guia = guia.get("valor_total", 0)

    if not valor_guia:
        erros.append("Valor total da guia não identificado")

    if valor_rel and valor_guia:
        if abs(float(valor_rel) - float(valor_guia)) > 1:
            erros.append("Valor total divergente entre relatório e guia")

    # =========================================
    # 5. DATA PAGAMENTO
    # =========================================
    if not guia.get("data_pagamento"):
        avisos.append("Data de pagamento não identificada")

    # =========================================
    # 6. TOMADOR + COLABORADORES
    # =========================================
    tomadores = relatorio.get("tomadores", [])

    if not tomadores:
        erros.append("Nenhum tomador encontrado no relatório")

    tomador_encontrado = False
    total_colaboradores = 0

    tomador_input_norm = normalizar_doc(tomador_input)

    for t in tomadores:
        cno = normalizar_doc(t.get("cnpj_ou_cno"))

        if tomador_input_norm:
            if tomador_input_norm in cno:
                tomador_encontrado = True
                total_colaboradores += len(t.get("colaboradores", []))
        else:
            total_colaboradores += len(t.get("colaboradores", []))

    if tomador_input_norm and not tomador_encontrado:
        erros.append("Tomador informado não encontrado no relatório")

    if total_colaboradores == 0:
        erros.append("Nenhum colaborador encontrado para o tomador")

    # =========================================
    # 7. STATUS FINAL
    # =========================================
    if erros:
        status = "Reprovado"
    elif avisos:
        status = "Parcial"
    else:
        status = "Aprovado"

    print("\n🧠 ================= FGTS RULES =================")
    print(f"📊 STATUS: {status}")
    print("================================================\n")

    return {
        "status": status,
        "erros": erros,
        "avisos": avisos
    }