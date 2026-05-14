def validar_cartao_ponto(colaboradores):
    print("\n🧠 ================= PONTO RULES =================")

    erros = []
    avisos = []

    if not colaboradores:
        erros.append("Nenhum colaborador encontrado no documento")

    total = len(colaboradores)

    sem_assinatura = []
    sem_marcacao = []
    sem_data = []

    for c in colaboradores:
        nome = c.get("nome", "Desconhecido")

        if not c.get("assinatura"):
            sem_assinatura.append(nome)

        if not c.get("marcacoes"):
            sem_marcacao.append(nome)

        if not c.get("datado"):
            sem_data.append(nome)

    # ======================================================
    # REGRAS
    # ======================================================

    if sem_assinatura:
        erros.append(f"Colaborador(es) sem assinatura: {', '.join(sem_assinatura)}")

    if sem_marcacao:
        erros.append(f"Colaborador(es) sem marcações: {', '.join(sem_marcacao)}")

    if sem_data:
        avisos.append(f"Colaborador(es) sem data: {', '.join(sem_data)}")

    # ======================================================
    # STATUS FINAL
    # ======================================================
    if erros:
        status = "Reprovado"
    elif avisos:
        status = "Parcial"
    else:
        status = "Aprovado"

    print(f"📊 STATUS: {status}")
    print("================================================\n")

    return {
        "status": status,
        "erros": erros,
        "avisos": avisos,
        "resumo": {
            "total_colaboradores": total,
            "sem_assinatura": len(sem_assinatura),
            "sem_marcacao": len(sem_marcacao),
            "sem_data": len(sem_data)
        }
    }