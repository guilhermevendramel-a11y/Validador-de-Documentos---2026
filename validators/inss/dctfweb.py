import re


# ============================================================
# NORMALIZA VALOR
# ============================================================
def normalizar_valor(valor):
    if not valor:
        return None

    try:
        valor = str(valor).replace(".", "").replace(",", ".")
        return float(valor)
    except:
        return None


# ============================================================
# EXTRAIR EMPRESA (NOME + CNPJ SEPARADOS 🔥)
# ============================================================
def extrair_empresa_nome(texto):
    texto_upper = texto.upper()

    # PRIORIDADE → Nome do Contribuinte (DCTF padrão)
    match = re.search(r"NOME\s+DO\s+CONTRIBUINTE\s*(.+)", texto_upper)
    if match:
        nome = match.group(1).strip()

        # corta lixo depois (ex: quebra de linha OCR)
        nome = re.split(r"\n|\r", nome)[0]
        return nome

    # fallback
    match = re.search(
        r"(RAZ[AÃ]O\s+SOCIAL|NOME\s+EMPRESARIAL)[:\s]+([A-Z0-9 \-\.]{5,})",
        texto_upper
    )
    if match:
        return match.group(2).strip()

    return None


def extrair_cnpj(texto):
    match = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)
    if match:
        return match.group()
    return None


# ============================================================
# VALIDAR DCTFWEB
# ============================================================
def validar_dctfweb(texto: str, competencia_esperada: str):

    texto_upper = texto.upper()

    # ============================================================
    # EMPRESA (CORRIGIDO 🔥🔥🔥)
    # ============================================================
    empresa_nome = extrair_empresa_nome(texto)
    cnpj = extrair_cnpj(texto)

    # 👉 NÃO misturar mais nome com CNPJ
    empresa = empresa_nome  # agora sempre nome quando possível

    # ============================================================
    # COMPETÊNCIA
    # ============================================================
    competencia = None

    m = re.search(
        r"(PER[IÍ]ODO\s+DE\s+APURA[CÇ][AÃ]O)[^\d]*(\d{2}/\d{4})",
        texto_upper
    )
    if m:
        competencia = m.group(2)

    if not competencia:
        m = re.search(r"\b\d{2}/\d{4}\b", texto_upper)
        if m:
            competencia = m.group()

    # ============================================================
    # VALOR (MANTIDO - JÁ ESTAVA ÓTIMO 🔥)
    # ============================================================
    valor = None

    m_total_duplo = re.search(
        r"TOTAL\s*R?\$?\s*([\d\.,]+)\s*R?\$?\s*([\d\.,]+)",
        texto_upper
    )

    if m_total_duplo:
        valor = m_total_duplo.group(2)

    if not valor:
        valores_total = re.findall(
            r"\bTOTAL\b\s*R?\$?\s*([\d\.,]+)",
            texto_upper
        )
        if valores_total:
            valor = valores_total[-1]

    if not valor:
        valores_saldo = re.findall(
            r"SALDO\s+A\s+PAGAR\s*R?\$?\s*([\d\.,]+)",
            texto_upper
        )
        if valores_saldo:
            valor = valores_saldo[-1]

    valor_float = normalizar_valor(valor)

    # ============================================================
    # SEÇÕES
    # ============================================================
    secoes = {
        "recibo_entrega": bool(re.search(r"RECIBO\s+DE\s+ENTREGA|RECIBO\s+DA\s+DCTFWEB", texto_upper)),
        "relatorio_debitos": bool(re.search(r"RELAT[ÓO]RIO\s+DE\s+D[ÉE]BITOS|RESUMO\s+DE\s+D[EÉ]BITOS", texto_upper)),
        "relatorio_creditos": bool(re.search(r"RELAT[ÓO]RIO\s+DE\s+CR[ÉE]DITOS|RESUMO\s+DE\s+CR[EÉ]DITOS", texto_upper)),
        "declaracao_completa": bool(re.search(r"DECLARA[CÇ][AÃ]O\s+COMPLETA|DECLARA[CÇ][AÃ]O\s+DE\s+D[ÉE]BITOS\s+E\s+CR[ÉE]DITOS|DCTFWEB", texto_upper))
    }

    # ============================================================
    # FLAGS
    # ============================================================
    recibo_zerado = valor_float == 0 if valor_float is not None else False
    debitos_identificados = valor_float is not None and valor_float > 0
    situacao_concluida = secoes["recibo_entrega"]

    # ============================================================
    # ERRO FINAL
    # ============================================================
    erro = (
        competencia != competencia_esperada
        or not situacao_concluida
    )

    # ============================================================
    # DEBUG (AJUDA MUITO)
    # ============================================================
    print("🏢 DCTF Nome:", empresa_nome)
    print("🏢 DCTF CNPJ:", cnpj)

    # ============================================================
    # RETORNO
    # ============================================================
    return {
        "erro": erro,

        "empresa": empresa,     # 🔥 AGORA É NOME
        "cnpj": cnpj,           # 🔥 SEPARADO

        "competencia": competencia,

        "valor": valor,
        "valor_float": valor_float,

        "recibo_entrega": secoes["recibo_entrega"],
        "relatorio_debitos": secoes["relatorio_debitos"],
        "relatorio_creditos": secoes["relatorio_creditos"],
        "declaracao_completa": secoes["declaracao_completa"],
        "resumo_debitos": secoes["relatorio_debitos"],
        "declaracao": secoes["declaracao_completa"],

        "recibo_zerado": recibo_zerado,

        "debitos_identificados": debitos_identificados,
        "situacao_concluida": situacao_concluida
    }
