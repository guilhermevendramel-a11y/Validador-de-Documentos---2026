def validar_cartao_ponto(colaboradores):
    print("\n[PONTO-RULES] =================")

    erros = []
    avisos = []

    if not colaboradores:
        erros.append("Nenhum colaborador encontrado no documento.")

    total = len(colaboradores)
    sem_assinatura = []
    assinatura_inconclusiva = []
    assinatura_fora_zona = []
    competencia_divergente = []
    sem_marcacao = []
    com_indicio_rasura = []
    sem_data = []

    for c in colaboradores:
        nome = c.get("nome", "Desconhecido")

        if not c.get("assinatura"):
            sem_assinatura.append(nome)
        elif c.get("assinatura_tipo") == "inconclusiva":
            assinatura_inconclusiva.append(nome)

        confianca = float(c.get("assinatura_confianca") or 0)
        if c.get("assinatura") and c.get("assinatura_origem") == "yolo" and confianca < 0.25:
            avisos.append(
                f"Colaborador {nome} possui assinatura detectada com baixa confianca YOLO: {round(confianca, 2)}."
            )

        if c.get("assinatura") and c.get("assinatura_tipo") == "manual/rubrica":
            zona = c.get("assinatura_zona")
            if zona and zona not in {"rodape", "meio"}:
                assinatura_fora_zona.append(nome)

        if c.get("competencia_ok") is False:
            competencia_divergente.append(f"{nome} ({c.get('competencia') or '-'})")

        if not c.get("marcacoes"):
            sem_marcacao.append(nome)
        if c.get("indicio_rasura_horario_britanico"):
            com_indicio_rasura.append(nome)

        if not c.get("datado"):
            sem_data.append(nome)

    if sem_assinatura:
        for nome in sem_assinatura:
            erros.append(f"Colaborador {nome} sem assinatura/rubrica identificada.")

    if assinatura_inconclusiva:
        for nome in assinatura_inconclusiva:
            avisos.append(f"Colaborador {nome} com assinatura inconclusiva.")

    if assinatura_fora_zona:
        for nome in assinatura_fora_zona:
            avisos.append(f"Colaborador {nome} possui assinatura detectada fora da zona esperada.")

    if competencia_divergente:
        erros.append("Competencia divergente para: " + ", ".join(competencia_divergente))

    if sem_marcacao:
        erros.append("Colaborador(es) sem marcacoes: " + ", ".join(sem_marcacao))
    if com_indicio_rasura:
        erros.append("Indicio de rasura por horario rigido (britanico): " + ", ".join(com_indicio_rasura))

    if sem_data:
        avisos.append("Colaborador(es) sem data: " + ", ".join(sem_data))

    if erros:
        status = "Reprovado"
    elif avisos:
        status = "Parcial"
    else:
        status = "Aprovado"

    print(f"[PONTO-RULES] STATUS={status}")
    return {
        "status": status,
        "erros": erros,
        "avisos": avisos,
        "resumo": {
            "total_colaboradores": total,
            "sem_assinatura": len(sem_assinatura),
            "assinatura_inconclusiva": len(assinatura_inconclusiva),
            "assinatura_fora_zona": len(assinatura_fora_zona),
            "competencia_divergente": len(competencia_divergente),
            "sem_marcacao": len(sem_marcacao),
            "com_indicio_rasura": len(com_indicio_rasura),
            "sem_data": len(sem_data),
        },
    }
