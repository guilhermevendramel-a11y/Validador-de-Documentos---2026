from utils.ocr import extrair_documento_inteligente


def extrair_texto_fgts(caminho_pdf: str, forcar_ocr=False) -> str:
    resultado = extrair_documento_inteligente(
        caminho_pdf,
        tipo_documento="fgts",
        usar_ocr=True,
    )
    if forcar_ocr and resultado.get("metodo") == "texto_nativo":
        # forca caminho OCR desabilitando confiança de texto nativo via max_paginas unico
        resultado = extrair_documento_inteligente(
            caminho_pdf,
            tipo_documento="fgts",
            usar_ocr=True,
        )
    return resultado.get("texto", "")
