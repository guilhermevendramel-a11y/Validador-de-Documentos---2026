import re

# ==========================================================
# 🧹 LIMPEZA
# ==========================================================
def limpar_texto(texto):
    if not texto:
        return ""
    
    texto = texto.upper()
    texto = re.sub(r"[^A-ZÀ-Ÿ\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    
    return texto.strip()

# ==========================================================
# 🔥 VALIDAÇÃO
# ==========================================================
def nome_valido(nome):
    if not nome:
        return False

    nome = limpar_texto(nome)
    palavras = nome.split()

    bloqueados = [
        "EMPREGADOR", "EMPRESA", "CNPJ", "PONTO", "FOLHA", "HORAS",
        "BAIRRO", "CIDADE", "UF", "ASSINATURA", "RESUMO", "TOTAL",
        "SALARIO", "FUNCAO", "DATA", "MES", "ANO"
    ]

    if any(b in nome for b in bloqueados):
        return False

    if len(palavras) < 2:
        return False

    palavras_reais = [p for p in palavras if len(p) >= 3]
    if len(palavras_reais) < 2:
        return False

    return True

# ==========================================================
# 🧠 SEPARA POR FUNCIONÁRIO
# ==========================================================
def separar_blocos(texto):
    blocos = texto.split("FOLHA DE PONTO INDIVIDUAL DE TRABALHO")
    return [b.strip() for b in blocos if len(b.strip()) > 100]

# ==========================================================
# 🔍 EXTRAI NOME DO BLOCO
# ==========================================================
def extrair_nome_bloco(bloco):
    linhas = bloco.split("\n")

    candidatos = []

    for linha in linhas:
        linha = linha.strip()

        if nome_valido(linha):
            candidatos.append(linha)

    if not candidatos:
        return None

    # Prioriza nomes maiores (mais completos)
    return max(candidatos, key=lambda x: len(x.split())).title()

# ==========================================================
# 🚀 ENGINE PRINCIPAL (NOVO)
# ==========================================================
def engine_extrair_nomes(texto):
    if not texto:
        return []

    texto = texto.upper()

    # Ignorar páginas de assinatura
    if "RELATÓRIO DE ASSINATURAS" in texto:
        return []

    blocos = separar_blocos(texto)

    nomes = []

    for bloco in blocos:
        nome = extrair_nome_bloco(bloco)
        if nome:
            nomes.append(nome)

    return list(set(nomes))