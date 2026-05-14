import re

# ============================================================
# EXTRAIR EMPRESA
# ============================================================
def extrair_empresa(texto: str) -> str | None:
    # Busca por rótulos comuns de folha
    m = re.search(r"EMPRESA:\s*(.+)", texto.upper())
    if m:
        return m.group(1).strip()
    return None

# ============================================================
# EXTRAIR COMPETÊNCIA
# ============================================================
def extrair_competencia_folha(texto: str) -> str | None:
    # Busca padrão MM/AAAA
    m = re.search(r"COMPET[EÊ]NCIA:\s*(\d{2}/\d{4})", texto.upper())
    if m:
        return m.group(1)
    return None

# ============================================================
# EXTRAIR COLABORADORES (NOMES + STATUS)
# ============================================================
def extrair_colaboradores(texto: str) -> list[dict]:
    colaboradores = set()
    # Regex ajustada para capturar nomes após o código do empregado (EMPR.:)
    padrao = re.compile(r"EMPR\.:\s*\d*\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{10,})")

    for match in padrao.findall(texto.upper()):
        nome = match.strip()
        # Filtro: pelo menos 2 nomes e sem palavras irrelevantes
        if len(nome.split()) >= 2 and "PAGINA" not in nome:
            colaboradores.add(nome.title())

    # Retorna lista estruturada para a tabela do frontend
    return [{"nome": n, "status": "✔ OK"} for n in sorted(colaboradores)]