from utils.ocr import extrair_documento_inteligente


def extrair_texto_folha(caminho_pdf: str) -> str:
    return extrair_documento_inteligente(caminho_pdf, tipo_documento="folha", usar_ocr=True).get("texto", "")
