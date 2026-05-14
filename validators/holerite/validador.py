from typing import List, Dict

from validators.holerite.parser_holerite import extrair_funcionarios
from validators.holerite.parser_comprovante import extrair_pagamentos
from validators.holerite.regras import aplicar_regras_holerite


def validar_holerite_e_pagamento(texto_holerite: str, textos_comprovantes: List[str]) -> Dict:

    try:

        # ================================
        # 1️⃣ Extrair dados do holerite
        # ================================
        lista_dados = extrair_funcionarios(texto_holerite)

        # ================================
        # 2️⃣ Extrair comprovantes
        # ================================
        comprovantes_detectados = []

        for texto in textos_comprovantes:
            comprovantes_detectados.extend(extrair_pagamentos(texto))

        # ================================
        # 3️⃣ Inicializar variáveis
        # ================================
        colaboradores_processados = []
        status_geral = "Aprovado"

        total_holerites = 0.0
        total_pago_banco = sum(c.get("valor_pago", 0.0) for c in comprovantes_detectados)

        # ================================
        # 4️⃣ Loop nos colaboradores
        # ================================
        for dados in lista_dados:

            nome = dados.get("nome", "NÃO IDENTIFICADO")

            valor_liquido = dados.get("valor_liquido", 0.0)

            total_holerites += valor_liquido

            resultado_regras = aplicar_regras_holerite(
                dados,
                comprovantes_detectados
            )

            if resultado_regras.get("status") == "Reprovado":
                status_geral = "Reprovado"

            colaboradores_processados.append({

                "nome": nome.upper(),

                "competencia": dados.get("competencia", "---"),

                "assinatura": "OK" if dados.get("assinatura") else "Pendente",

                "valor_liquido": f"R$ {valor_liquido:.2f}".replace(".", ","),

                "valor_pago": f"R$ {resultado_regras.get('valor_pago', 0):.2f}".replace(".", ","),

                "diferenca": f"R$ {resultado_regras.get('diferenca', 0):.2f}".replace(".", ","),

                "valor_status": "Confere"
                if resultado_regras.get("status") == "Aprovado"
                else "Divergente",

                "prazo_status": "OK",

                "datado": "Sim"

            })

        # ================================
        # 5️⃣ Retorno final
        # ================================
        return {

            "status": status_geral,

            "mensagem": "Análise nominal concluída!",

            "empresa": "EJ.C SOLUTIONS LTDA",

            "resumo": {

                "total_holerite": f"R$ {total_holerites:.2f}".replace(".", ","),

                "total_pago": f"R$ {total_pago_banco:.2f}".replace(".", ","),

                "diferenca": f"R$ {abs(total_holerites - total_pago_banco):.2f}".replace(".", ",")

            },

            "colaboradores": colaboradores_processados
        }

    except Exception as e:

        print(f"❌ ERRO: {str(e)}")

        return {
            "status": "Erro",
            "mensagem": str(e),
            "colaboradores": []
        }