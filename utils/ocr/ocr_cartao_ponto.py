from utils.ocr import extrair_documento_inteligente


def extrair_paginas_cartao_ponto(caminho_pdf: str):
    resultado = extrair_documento_inteligente(
        caminho_pdf,
        tipo_documento="cartao_ponto",
        usar_ocr=True,
    )
    paginas = resultado.get("paginas", [])
    return [{"pagina": p.get("pagina"), "texto": p.get("texto", "")} for p in paginas]
