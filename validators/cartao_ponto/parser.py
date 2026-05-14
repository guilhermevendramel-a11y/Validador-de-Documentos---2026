import re

# ============================================================
# 🔧 NORMALIZAÇÃO
# ============================================================
def limpar_texto(texto):
    if not texto:
        return ""
    texto = texto.upper()
    texto = re.sub(r"\r", "\n", texto)
    texto = re.sub(r"\n+", "\n", texto)
    return texto


# ============================================================
# 🧠 SEPARAR POR FUNCIONÁRIO (MESMA LÓGICA DO ENGINE)
# ============================================================
def separar_blocos(texto):
    partes = texto.split("FOLHA DE PONTO INDIVIDUAL DE TRABALHO")

    blocos = []

    for parte in partes:
        parte = parte.strip()
        if len(parte) < 100:
            continue

        bloco = "FOLHA DE PONTO INDIVIDUAL DE TRABALHO\n" + parte
        blocos.append(bloco)

    return blocos


# ============================================================
# 👤 EXTRAIR NOME (ROBUSTO)
# ============================================================
def extrair_nome(texto):
    linhas = texto.split("\n")

    for linha in linhas:
        linha = linha.strip()

        if (
            len(linha.split()) >= 2
            and len(linha) > 10
            and not re.search(r"\d", linha)
            and not any(x in linha for x in [
                "FOLHA", "PONTO", "EMPRESA", "CNPJ", "HORAS", "TOTAL"
            ])
        ):
            return linha.title()

    return None


# ============================================================
# 📅 COMPETÊNCIA
# ============================================================
def extrair_competencia(texto):
    meses = {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "ABRIL": "04",
        "MAIO": "05", "JUNHO": "06", "JULHO": "07", "AGOSTO": "08",
        "SETEMBRO": "09", "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12"
    }

    match = re.search(
        r"(JANEIRO|FEVEREIRO|MARCO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\s+(\d{4})",
        texto
    )

    if match:
        return f"{meses[match.group(1)]}/{match.group(2)}"

    return None


# ============================================================
# 🕒 EXTRAIR REGISTROS (FORMATO REAL DO SEU PDF)
# ============================================================
def extrair_registros(texto):
    registros = re.findall(
        r"(\d{1,2})\s+(\d{2}:\d{2})\s+(\d{2}:\d{2})\s+(\d{2}:\d{2})\s+(\d{2}:\d{2})",
        texto
    )

    resultado = []

    for dia, e1, s1, e2, s2 in registros:
        resultado.append({
            "dia": int(dia),
            "entrada_manha": e1,
            "saida_manha": s1,
            "entrada_tarde": e2,
            "saida_tarde": s2
        })

    return resultado


# ============================================================
# ⏱️ CALCULAR HORAS
# ============================================================
def calcular_horas(registros):
    total_min = 0

    for r in registros:
        try:
            h1, m1 = map(int, r["entrada_manha"].split(":"))
            h2, m2 = map(int, r["saida_manha"].split(":"))

            h3, m3 = map(int, r["entrada_tarde"].split(":"))
            h4, m4 = map(int, r["saida_tarde"].split(":"))

            total_min += (h2*60+m2) - (h1*60+m1)
            total_min += (h4*60+m4) - (h3*60+m3)

        except:
            continue

    return round(total_min / 60, 2)


# ============================================================
# 🔥 PARSER PRINCIPAL (MULTI FUNCIONÁRIO)
# ============================================================
def parse_cartao_ponto(texto):

    texto = limpar_texto(texto)

    blocos = separar_blocos(texto)

    colaboradores = []

    for bloco in blocos:

        nome = extrair_nome(bloco)
        competencia = extrair_competencia(bloco)
        registros = extrair_registros(bloco)
        horas = calcular_horas(registros)

        if nome and registros:
            colaboradores.append({
                "nome": nome,
                "competencia": competencia,
                "dias_trabalhados": len(registros),
                "horas_total": horas,
                "registros": registros
            })

    return colaboradores