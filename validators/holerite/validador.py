from typing import Dict, List

from validators.holerite.parser_comprovante import extrair_pagamentos
from validators.holerite.parser_holerite import extrair_funcionarios
from validators.holerite.regras import aplicar_regras_holerite


def _fmt_brl(valor: float) -> str:
    txt = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {txt}"


def validar_holerite_e_pagamento(texto_holerite: str, textos_comprovantes: List[str]) -> Dict:
    try:
        lista_dados = extrair_funcionarios(texto_holerite)
        comprovantes_detectados = []
        for texto in textos_comprovantes:
            comprovantes_detectados.extend(extrair_pagamentos(texto))

        colaboradores_processados = []
        total_holerites = 0.0
        total_pago_banco = sum(float(c.get("valor_pago", 0.0) or 0.0) for c in comprovantes_detectados)
        status_rank = {"Aprovado": 0, "Parcial": 1, "Reprovado": 2}
        status_geral = "Aprovado"
        matches = []

        empresa = "---"
        for d in lista_dados:
            if d.get("empresa") and d.get("empresa") != "---":
                empresa = d["empresa"]
                break

        for dados in lista_dados:
            nome = (dados.get("nome") or "NAO IDENTIFICADO").upper()
            valor_liquido = float(dados.get("valor_liquido", 0.0) or 0.0)
            total_holerites += valor_liquido
            resultado = aplicar_regras_holerite(dados, comprovantes_detectados)

            if status_rank[resultado["status"]] > status_rank[status_geral]:
                status_geral = resultado["status"]

            colaboradores_processados.append({
                "nome": nome,
                "nome_comprovante": (resultado.get("nome_comprovante") or "---").upper(),
                "score_nome": resultado.get("score_nome", 0),
                "competencia": dados.get("competencia") or "---",
                "tipo_documento": dados.get("tipo_documento") or "holerite",
                "nome_colaborador": dados.get("nome_colaborador") or dados.get("nome"),
                "assinatura": dados.get("assinatura"),
                "assinatura_presente": dados.get("assinatura_presente", dados.get("assinatura")),
                "tipo_assinatura": dados.get("tipo_assinatura"),
                "local_assinatura_detectado": dados.get("local_assinatura_detectado"),
                "confianca_valor_liquido": dados.get("confianca_valor_liquido", 0.0),
                "confianca_assinatura": dados.get("confianca_assinatura", 0.0),
                "valor_liquido": _fmt_brl(valor_liquido),
                "valor_liquido_extraido": dados.get("valor_liquido_extraido", valor_liquido),
                "valor_pago": _fmt_brl(float(resultado.get("valor_pago", 0.0) or 0.0)),
                "diferenca": _fmt_brl(float(resultado.get("diferenca", 0.0) or 0.0)),
                "valor_status": "Confere" if abs(float(resultado.get("diferenca", 0.0) or 0.0)) <= 0.01 else "Divergente",
                "prazo_status": "OK" if dados.get("competencia") else "Pendente",
                "datado": "Sim" if (dados.get("data_assinatura") or dados.get("data_recibo") or dados.get("data_assinatura_extraida")) else "Nao",
                "data_assinatura_extraida": dados.get("data_assinatura_extraida"),
                "local_assinatura": dados.get("local_assinatura_detectado"),
                "evidencias": dados.get("evidencias", []),
                "pendencias": dados.get("pendencias", []),
                "status_final": dados.get("status_final"),
                "status": resultado.get("status"),
                "motivo": resultado.get("motivo"),
                "data_pagamento": resultado.get("data_pagamento"),
            })

            matches.append({
                "nome_holerite": nome,
                "nome_comprovante": resultado.get("nome_comprovante"),
                "score_nome": resultado.get("score_nome"),
                "valor_liquido": valor_liquido,
                "valor_pago": float(resultado.get("valor_pago", 0.0) or 0.0),
                "motivo": resultado.get("motivo"),
                "status": resultado.get("status"),
            })

        return {
            "status": status_geral,
            "mensagem": "Analise nominal concluida!",
            "empresa": empresa,
            "resumo": {
                "total_holerite": _fmt_brl(total_holerites),
                "total_pago": _fmt_brl(total_pago_banco),
                "diferenca": _fmt_brl(round(total_holerites - total_pago_banco, 2)),
            },
            "colaboradores": colaboradores_processados,
            "debug": {
                "total_holerites_detectados": len(lista_dados),
                "total_comprovantes_detectados": len(comprovantes_detectados),
                "holerites_detectados": lista_dados,
                "comprovantes_detectados": comprovantes_detectados,
                "matches": matches,
            },
        }
    except Exception as e:
        return {"status": "Erro", "mensagem": str(e), "colaboradores": [], "debug": {"total_holerites_detectados": 0, "total_comprovantes_detectados": 0, "holerites_detectados": [], "comprovantes_detectados": [], "matches": []}}
