import re


def validar_secoes(texto: str) -> dict:
    texto_upper = texto.upper()

    return {
        "Relação de Trabalhadores": bool(re.search(r"TRABALHADOR", texto_upper)),
        "Relação de Categorias": bool(re.search(r"CATEGORIAS", texto_upper)),
        "Relação de Estabelecimentos": bool(re.search(r"ESTABELECIMENTOS?", texto_upper)),
        "Relação de Tipos de Valor": bool(re.search(r"TIPOS?\s+DE\s+VALOR", texto_upper)),
        "Relação de Tomadores": bool(re.search(r"TOMADORES?(?:\s+DE\s+SERVI[CÇ]O)?", texto_upper)),
    }
