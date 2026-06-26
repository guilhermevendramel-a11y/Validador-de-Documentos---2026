import re
from typing import Any, Dict, List

from validators.holerite.engine_parser import engine_extracao, normalizar_texto

SEPARADOR_PAGINA = r"(?:\f|\n\s*[-=]{3,}\s*\n|\n\s*PAGINA\s+\d+\s*\n)"


def _split_blocos_comprovante(texto: str) -> List[str]:
    texto = normalizar_texto(texto)
    paginas = [p.strip() for p in re.split(SEPARADOR_PAGINA, texto, flags=re.IGNORECASE) if p.strip()] or [texto]
    blocos: List[str] = []
    for pg in paginas:
        starts = [m.start() for m in re.finditer(r"(?=BANCO\s+ITAU\s*-\s*COMPROVANTE\s+DE\s+TRANSFERENCIA|DADOS\s+DA\s+CONTA\s+CREDITADA\s*:)", pg, flags=re.IGNORECASE)]
        if not starts:
            blocos.append(pg)
            continue
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else len(pg)
            blocos.append(pg[s:e].strip())
    return blocos


def extrair_pagamentos(texto: str) -> List[Dict[str, Any]]:
    pagamentos: List[Dict[str, Any]] = []
    if not texto:
        return pagamentos
    for idx, bloco in enumerate(_split_blocos_comprovante(texto), start=1):
        dados = engine_extracao(bloco, tipo="comprovante")
        if dados.get("nome") and float(dados.get("valor_pago", 0.0) or 0.0) > 0:
            dados["pagina"] = idx
            dados["bloco"] = idx
            pagamentos.append(dados)
    return pagamentos
