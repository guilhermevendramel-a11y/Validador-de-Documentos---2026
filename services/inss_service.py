from utils.gemini.inss import extrair_inss_inteligente
from utils.ocr import deve_chamar_ia, extrair_documento_inteligente, montar_payload_ia_economico
from validators.inss.validator import INSSValidator


def processar_inss(caminho_guia, caminho_dctf, competencia_esperada):
    try:
        ocr_guia = extrair_documento_inteligente(caminho_guia, tipo_documento="inss", usar_ocr=True)
        texto_guia = ocr_guia.get("texto", "")
        if not texto_guia:
            return {"status": "Erro", "mensagem": "OCR não conseguiu extrair texto da guia", "erros": ["OCR falhou"]}

        parser_local = {"campos": {"competencia": competencia_esperada}, "inconclusivo": False}
        chamar_ia, motivo_ia = deve_chamar_ia(ocr_guia, parser_local, tipo_documento="inss")

        dados_guia = None
        payload_ia = None
        if chamar_ia:
            payload_ia = montar_payload_ia_economico("inss", ocr_guia, parser_local)
            dados_guia = extrair_inss_inteligente("\n".join([t.get("trecho", "") for t in payload_ia.get("trechos_relevantes", [])]) or texto_guia)
            if not isinstance(dados_guia, dict):
                dados_guia = None

        validador = INSSValidator()
        resultado = validador.analisar(caminho_guia, caminho_dctf, competencia_esperada, dados_ia=dados_guia)
        resultado["ocr_metodo"] = ocr_guia.get("metodo")
        resultado["ocr_qualidade"] = ocr_guia.get("qualidade")
        resultado["ia_fallback"] = chamar_ia
        resultado["ia_motivo"] = motivo_ia
        resultado["ia_payload"] = payload_ia
        return resultado

    except Exception as e:
        return {"status": "Erro", "mensagem": f"Erro ao processar INSS: {str(e)}", "erros": [str(e)]}
