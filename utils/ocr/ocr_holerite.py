from utils.ocr import extrair_documento_inteligente


def extrair_texto_holerite(path):
    return extrair_documento_inteligente(path, tipo_documento="holerite", usar_ocr=True).get("texto", "")
