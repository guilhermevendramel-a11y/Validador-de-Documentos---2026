import re
import unicodedata


def normalizar_valor(valor):
    if not valor:
        return None

    try:
        valor = str(valor).replace(".", "").replace(",", ".")
        return float(valor)
    except Exception:
        return None


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _normalizar_texto(texto):
    linhas_norm = []
    for linha in _sem_acento(texto).upper().splitlines():
        linha = re.sub(r"[^A-Z0-9/,\.\-\s]+", " ", linha)
        linha = re.sub(r"\s+", " ", linha).strip()
        if linha:
            linhas_norm.append(linha)
    return "\n".join(linhas_norm)


def _extrair_empresa_nome(texto):
    texto_upper = _sem_acento(texto).upper()
    linhas = [l.strip() for l in texto_upper.splitlines() if l.strip()]

    for linha in linhas:
        if "NOME DO CONTRIBUINTE" in linha:
            candidato = linha.split("NOME DO CONTRIBUINTE", 1)[1].strip()
            candidato = re.split(
                r"\s+(?:CNPJ|PERIODO|PERIODO DE APURACAO|NUMERO DO RECIBO|N[ºO]|VALOR|SALDO|RECIBO|DCTFWEB)\b",
                candidato,
            )[0].strip()
            candidato = re.sub(r"\s+", " ", candidato).strip(" -:;")
            if candidato:
                return candidato

    for linha in linhas:
        if any(rot in linha for rot in ["RAZAO SOCIAL", "NOME EMPRESARIAL"]):
            candidato = re.split(
                r"\s+(?:CNPJ|PERIODO|PERIODO DE APURACAO|NUMERO DO RECIBO|N[ºO]|VALOR|SALDO|RECIBO|DCTFWEB)\b",
                linha.split(":", 1)[-1] if ":" in linha else linha,
            )[0].strip()
            candidato = re.sub(r"\s+", " ", candidato).strip(" -:;")
            if candidato:
                return candidato

    return None


def extrair_cnpj(texto):
    match = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)
    if match:
        return match.group()
    return None


def _extrair_valores_monetarios(texto):
    return [m.group(1) for m in re.finditer(r"([\d]{1,3}(?:\.\d{3})*,\d{2})", texto or "")]


def _melhor_valor_linha(linha):
    valores = _extrair_valores_monetarios(linha)
    if not valores:
        return None
    melhores = [normalizar_valor(v) for v in valores]
    melhores = [v for v in melhores if v is not None]
    if not melhores:
        return None
    return max(melhores)


def _extrair_valor_dctf(texto):
    texto_norm = _normalizar_texto(texto)
    linhas = [l.strip() for l in texto_norm.splitlines() if l.strip()]

    prioridades = [
        ["TOTALIZA", "TRIBUTOS APURADOS", "TOTAL R"],
        ["VALOR TOTAL DO DEBITO", "VALOR TOTAL DO DÉBITO"],
        ["VALOR TOTAL DO DOCUMENTO"],
        ["TOTAL A PAGAR"],
    ]

    for grupos in prioridades:
        for idx, linha in enumerate(linhas):
            linha_u = linha.upper()
            if not any(g in linha_u for g in grupos):
                continue
            candidatos = [linha]
            if idx + 1 < len(linhas):
                candidatos.append(f"{linha} {linhas[idx + 1]}")
            for trecho in candidatos:
                valor = _melhor_valor_linha(trecho)
                if valor is not None:
                    return valor

    for idx, linha in enumerate(linhas):
        linha_u = linha.upper()
        if "SALDO A PAGAR" not in linha_u:
            continue
        valor = _melhor_valor_linha(linha)
        if valor is None and idx + 1 < len(linhas):
            valor = _melhor_valor_linha(f"{linha} {linhas[idx + 1]}")
        if valor is not None:
            return valor

    for linha in linhas[::-1]:
        if "TOTAL" in linha.upper():
            valor = _melhor_valor_linha(linha)
            if valor is not None:
                return valor

    return None


def validar_dctfweb(texto: str, competencia_esperada: str):
    texto_norm = _normalizar_texto(texto)

    empresa_nome = _extrair_empresa_nome(texto)
    cnpj = extrair_cnpj(texto)
    empresa = empresa_nome

    competencia = None
    m = re.search(r"PERIODO\s+DE\s+APURACAO\s*(\d{2}/\d{4})", texto_norm)
    if m:
        competencia = m.group(1)
    if not competencia:
        m = re.search(r"\b\d{2}/\d{4}\b", texto_norm)
        if m:
            competencia = m.group()

    valor_float = _extrair_valor_dctf(texto)
    valor = None
    if valor_float is not None:
        valor = f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    secoes = {
        "recibo_entrega": bool(re.search(r"RECIBO\s+DE\s+ENTREGA", texto_norm)),
        "relatorio_debitos": bool(
            re.search(r"RELATORIO\s+(?:RESUMO\s+)?DE\s+DEBITOS|RESUMO\s+DE\s+DEBITOS|DEBITOS\s+APURADOS", texto_norm)
        ),
        "relatorio_creditos": bool(
            re.search(r"RELATORIO\s+(?:RESUMO\s+DE\s+)?CREDITOS|RESUMO\s+DE\s+CREDITOS|CREDITOS\s+VINCULAVEIS", texto_norm)
        ),
        "declaracao_completa": bool(
            re.search(
                r"DECLARACAO\s+COMPLETA|DCTFWEB",
                texto_norm,
            )
        ),
    }

    recibo_zerado = valor_float == 0 if valor_float is not None else False
    debitos_identificados = valor_float is not None and valor_float > 0
    situacao_concluida = secoes["recibo_entrega"]
    erro = competencia != competencia_esperada or not situacao_concluida

    print("DCTF Nome:", empresa_nome)
    print("DCTF CNPJ:", cnpj)

    return {
        "erro": erro,
        "empresa": empresa,
        "empresa_nome": empresa,
        "cnpj": cnpj,
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
        "situacao_concluida": situacao_concluida,
    }
