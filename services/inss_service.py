import os

from utils.ocr.ocr_inss import extrair_texto_inss
from utils.gemini.inss import extrair_inss_inteligente
from validators.inss.validator import INSSValidator


def processar_inss(caminho_guia, caminho_dctf, competencia_esperada):
    """
    Serviço responsável por processar a validação do INSS
    seguindo o padrão dos outros services (holerite, fgts, etc).
    """

    try:
        # -------------------------
        # 1. OCR
        # -------------------------
        texto_guia = extrair_texto_inss(caminho_guia)

        if not texto_guia:
            return {
                "status": "Erro",
                "mensagem": "OCR não conseguiu extrair texto da guia",
                "erros": ["OCR falhou"]
            }

        # -------------------------
        # 2. IA (Gemini)
        # -------------------------
        dados_guia = extrair_inss_inteligente(texto_guia)

        # Proteção contra retorno inválido
        if not isinstance(dados_guia, dict):
            print("⚠️ Dados IA inválidos, usando fallback...")
            dados_guia = None

        print("🧠 Dados IA:", dados_guia)

        # -------------------------
        # 3. Validação
        # -------------------------
        validador = INSSValidator()

        resultado = validador.analisar(
            caminho_guia,
            caminho_dctf,
            competencia_esperada,
            dados_ia=dados_guia
        )

        return resultado

    except Exception as e:
        print(f"❌ ERRO NO SERVICE INSS: {e}")

        return {
            "status": "Erro",
            "mensagem": f"Erro ao processar INSS: {str(e)}",
            "erros": [str(e)]
        }