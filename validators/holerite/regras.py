import unicodedata
from rapidfuzz import fuzz


# ---------------------------------------------------------
# NORMALIZA NOME
# ---------------------------------------------------------
def normalizar_nome(nome):

    if not nome:
        return ""

    nome = nome.upper()

    nome = unicodedata.normalize("NFKD", nome)
    nome = nome.encode("ASCII", "ignore").decode("ASCII")

    nome = " ".join(nome.split())

    return nome


# ---------------------------------------------------------
# BUSCAR PAGAMENTO MAIS PROXIMO
# ---------------------------------------------------------
def encontrar_pagamento(nome_funcionario, pagamentos):

    nome_base = normalizar_nome(nome_funcionario)

    melhor_score = 0
    melhor_pagamento = None

    for pagamento in pagamentos:

        nome_pagamento = normalizar_nome(pagamento.get("nome", ""))

        score = fuzz.token_sort_ratio(nome_base, nome_pagamento)

        if score > melhor_score:
            melhor_score = score
            melhor_pagamento = pagamento

    if melhor_score >= 85:
        return melhor_pagamento

    return None


# ---------------------------------------------------------
# REGRA PRINCIPAL
# ---------------------------------------------------------
def aplicar_regras_holerite(dados_funcionario, pagamentos):

    nome = dados_funcionario.get("nome")

    valor_liquido = float(dados_funcionario.get("valor_liquido", 0.0))

    pagamento = encontrar_pagamento(nome, pagamentos)

    if not pagamento:

        return {
            "status": "Reprovado",
            "valor_pago": 0.0,
            "diferenca": valor_liquido,
            "motivo": "Pagamento não encontrado"
        }

    valor_pago = float(pagamento.get("valor_pago", 0.0))

    diferenca = round(valor_pago - valor_liquido, 2)

    if abs(diferenca) < 0.01:

        return {
            "status": "Aprovado",
            "valor_pago": valor_pago,
            "diferenca": 0.0,
            "motivo": "Valor confere"
        }

    return {
        "status": "Reprovado",
        "valor_pago": valor_pago,
        "diferenca": diferenca,
        "motivo": "Diferença entre holerite e pagamento"
    }