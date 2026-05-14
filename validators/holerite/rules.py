from rapidfuzz import fuzz


def _normalizar_nome(nome):
    if not nome:
        return ""
    return " ".join(str(nome).upper().split())


def validar_holerite(dados, competencia_esperada=None):

    erros = []
    avisos = []

    nome_h = dados.get("nome_holerite")
    nome_c = dados.get("nome_comprovante")

    valor_h = dados.get("valor_holerite")
    valor_c = dados.get("valor_comprovante")

    competencia = dados.get("competencia")

    # =========================
    # NOME
    # =========================
    if not nome_h or not nome_c:
        erros.append("Nome não identificado")

    elif fuzz.token_set_ratio(_normalizar_nome(nome_h), _normalizar_nome(nome_c)) < 85:
        erros.append("Nome divergente")

    # =========================
    # VALOR
    # =========================
    if not valor_h or not valor_c:
        erros.append("Valor não identificado")

    elif abs(valor_h - valor_c) > 1:
        erros.append("Valor divergente")

    # =========================
    # COMPETÊNCIA
    # =========================
    if not competencia:
        avisos.append("Competência não identificada")

    elif competencia_esperada and competencia != competencia_esperada:
        erros.append("Competência divergente")

    # =========================
    # STATUS
    # =========================
    if erros:
        status = "Reprovado"
    elif avisos:
        status = "Parcial"
    else:
        status = "Aprovado"

    return {
        "status": status,
        "erros": erros,
        "avisos": avisos,
        "dados": dados
    }
