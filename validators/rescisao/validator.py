import os
from utils.ocr import extrair_texto_pdf_inteligente
from validators.rescisao.trct_logic import extrair_dados_trct
from validators.rescisao.gfd_logic import extrair_dados_gfd

class RescisaoValidator:
    def analisar(self, caminho_pdf, nome_esperado):
        texto_completo = extrair_texto_pdf_inteligente(caminho_pdf) or ""
        texto_upper = texto_completo.upper()

        dados_trct = extrair_dados_trct(texto_completo)
        dados_gfd = extrair_dados_gfd(texto_completo)

        # 1. Validação Nominal
        nome_ok = nome_esperado.upper() in texto_upper

        # 2. Batimento Financeiro Inteligente (Contagem de Ocorrências)
        # Se o valor aparece 2+ vezes, assumimos que há o documento e o comprovante 
        trct_ok = False
        if dados_trct["valor_formatado"]:
            trct_ok = texto_completo.count(dados_trct["valor_formatado"]) >= 2

        gfd_ok = False
        if dados_gfd["valor_formatado"]:
            gfd_ok = texto_completo.count(dados_gfd["valor_formatado"]) >= 2

        # 3. Busca por Palavras-Chave (Genérica e com Acentos) [cite: 333, 370]
        aso_ok = any(x in texto_upper for x in ["ASO", "DEMISSIONAL", "SAÚDE", "SAUDE"])
        aviso_ok = any(x in texto_upper for x in ["AVISO PRÉVIO", "AVISO PREVIO", "DISPENSA", "DEMISSÃO"])
        ponto_ok = any(x in texto_upper for x in ["PONTO", "CARTÃO", "CARTAO", "MARCAÇÃO", "MARCACAO"])

        validacoes = [
            {"item": f"Colaborador: {nome_esperado}", "ok": nome_ok},
            {"item": f"TRCT: Valor ({dados_trct['valor_formatado'] or '---'}) vs Comprovante", "ok": trct_ok},
            {"item": f"GFD: Valor ({dados_gfd['valor_formatado'] or '---'}) vs Comprovante", "ok": gfd_ok},
            {"item": "ASO Demissional", "ok": aso_ok},
            {"item": "Aviso/Pedido de Demissão", "ok": aviso_ok},
            {"item": "Cartão de Ponto", "ok": ponto_ok}
        ]

        status = "Aprovado" if all(v["ok"] for v in validacoes) else "Reprovado"

        return {
            "status": status,
            "mensagem": "Kit validado com sucesso" if status == "Aprovado" else "Existem pendências no Kit",
            "validacoes": validacoes
        }