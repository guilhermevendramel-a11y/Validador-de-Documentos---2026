from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz

from validators.holerite.engine_parser import normalizar_nome


def _prefixo_forte(nome_a: str, nome_b: str) -> bool:
    if not nome_a or not nome_b:
        return False
    menor, maior = (nome_a, nome_b) if len(nome_a) <= len(nome_b) else (nome_b, nome_a)
    return len(menor) >= 18 and maior.startswith(menor)


def encontrar_pagamento(nome_funcionario: str, pagamentos: List[Dict[str, Any]]) -> Dict[str, Any]:
    nome_base = normalizar_nome(nome_funcionario)
    melhor_score = 0.0
    melhor_pagamento: Optional[Dict[str, Any]] = None
    melhor_nome = ""

    for pagamento in pagamentos:
        nome_pagamento = normalizar_nome(pagamento.get("nome", ""))
        if not nome_pagamento:
            continue
        score = max(float(fuzz.token_set_ratio(nome_base, nome_pagamento)), float(fuzz.token_sort_ratio(nome_base, nome_pagamento)))
        if _prefixo_forte(nome_base, nome_pagamento):
            score = max(score, 90.0)
        if score > melhor_score:
            melhor_score = score
            melhor_pagamento = pagamento
            melhor_nome = pagamento.get("nome", "")

    return {"pagamento": melhor_pagamento if melhor_score >= 85 else None, "score_nome": round(melhor_score, 2), "nome_comprovante": melhor_nome}


def aplicar_regras_holerite(dados_funcionario: Dict[str, Any], pagamentos: List[Dict[str, Any]]) -> Dict[str, Any]:
    valor_liquido = float(dados_funcionario.get("valor_liquido", 0.0) or 0.0)
    achado = encontrar_pagamento(dados_funcionario.get("nome", ""), pagamentos)
    pagamento = achado["pagamento"]
    assinatura_ok = bool(dados_funcionario.get("assinatura") is True or dados_funcionario.get("assinatura_presente") is True)
    data_ok = bool(
        dados_funcionario.get("data_assinatura")
        or dados_funcionario.get("data_assinatura_extraida")
        or dados_funcionario.get("data_recibo")
    )

    if not pagamento:
        return {"status": "Reprovado", "nome_comprovante": achado["nome_comprovante"], "score_nome": achado["score_nome"], "valor_pago": 0.0, "diferenca": round(valor_liquido, 2), "motivo": "Pagamento nao encontrado ou nome abaixo do score minimo (85)", "data_pagamento": None}

    valor_pago = float(pagamento.get("valor_pago", 0.0) or 0.0)
    diferenca = round(valor_pago - valor_liquido, 2)

    if abs(diferenca) <= 0.01:
        competencia_ok = bool(dados_funcionario.get("competencia"))
        status = "Aprovado" if (competencia_ok and assinatura_ok and data_ok) else "Reprovado"
        motivo = "Nome, valor, assinatura e data conferem" if status == "Aprovado" else "Nome e valor conferem, mas faltam competencia/data/assinatura"
        return {"status": status, "nome_comprovante": achado["nome_comprovante"], "score_nome": achado["score_nome"], "valor_pago": valor_pago, "diferenca": 0.0, "motivo": motivo, "data_pagamento": pagamento.get("data_pagamento")}

    return {"status": "Reprovado", "nome_comprovante": achado["nome_comprovante"], "score_nome": achado["score_nome"], "valor_pago": valor_pago, "diferenca": diferenca, "motivo": "Diferenca entre holerite e pagamento acima de R$ 0,01", "data_pagamento": pagamento.get("data_pagamento")}
