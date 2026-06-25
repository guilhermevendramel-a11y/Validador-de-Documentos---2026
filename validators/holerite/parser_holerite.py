import re
from typing import Any, Dict, List

from validators.holerite.engine_parser import engine_extracao, normalizar_nome, normalizar_texto

SEPARADOR_PAGINA = r"(?:\f|\n\s*[-=]{3,}\s*\n|\n\s*PAGINA\s+\d+\s*\n)"


def _split_blocos_holerite(texto: str) -> List[str]:
    texto = normalizar_texto(texto)
    paginas = [p.strip() for p in re.split(SEPARADOR_PAGINA, texto, flags=re.IGNORECASE) if p.strip()] or [texto]
    blocos: List[str] = []
    regex_titulos = r"(?=(?:RECIBO\s+DE\s+PAGAMENTO\s+DE\s+SALARIO|RECIBO\s+DE\s+PAGAMENTO|RECIBO\s+DE\s+SALARIO|DEMONSTRATIVO|HOLERITE|ADIANTAMENTO))"
    regex_nomes = r"(?=(?:NOME\s+(?:DO\s+)?(?:FUNCIONARIO|FUNCIONÁRIO|COLABORADOR|EMPREGADO)|(?:CODIGO\s+)?NOME\s+DO\s+(?:FUNCIONARIO|FUNCIONÁRIO|COLABORADOR|EMPREGADO)))"
    for pg in paginas:
        starts = [m.start() for m in re.finditer(regex_titulos, pg, flags=re.IGNORECASE)]
        if not starts:
            starts = [m.start() for m in re.finditer(regex_nomes, pg, flags=re.IGNORECASE)]
        if not starts:
            blocos.append(pg)
            continue
        starts_ordenados = sorted(set(starts))
        for i, s in enumerate(starts_ordenados):
            e = starts_ordenados[i + 1] if i + 1 < len(starts_ordenados) else len(pg)
            prev = pg[:s]
            header = "\n".join(prev.splitlines()[-2:])
            blocos.append((header + "\n" + pg[s:e]).strip())
    return blocos


def extrair_funcionarios(texto: str) -> List[Dict[str, Any]]:
    funcionarios: List[Dict[str, Any]] = []
    if not texto:
        return funcionarios
    vistos = set()
    for idx, bloco in enumerate(_split_blocos_holerite(texto), start=1):
        dados = engine_extracao(bloco, tipo="holerite")
        nome = dados.get("nome")
        valor = float(dados.get("valor_liquido", 0.0) or 0.0)
        if not nome or valor <= 0:
            continue
        chave = (normalizar_nome(nome), round(valor, 2))
        if chave in vistos:
            continue
        vistos.add(chave)
        dados["pagina"] = idx
        dados["bloco"] = idx
        funcionarios.append(dados)
    return funcionarios
