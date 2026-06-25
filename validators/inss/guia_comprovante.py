import re

from utils.ocr.ocr_inss import extrair_competencia_do_texto


_SUFIXOS_EMPRESA = (
    "LTDA",
    "EIRELI",
    "ME",
    "EPP",
    "S/A",
    "S A",
    "SA",
    "LIMITADA",
    "SOCIEDADE",
    "CONSULTORIA",
    "SERVICOS",
    "SERVICOS TECNICOS",
    "SERVICOS TECNICOS LTDA",
)


def _normalizar_linha(texto):
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _parece_nome_empresa(texto):
    linha = _normalizar_linha(texto)
    if not linha or len(linha) < 5:
        return False
    if re.search(r"\d", linha):
        return False

    linha_u = linha.upper()
    if any(
        termo in linha_u
        for termo in [
            "VALOR",
            "COMPET",
            "RECIBO",
            "DCTF",
            "GUIA",
            "PAGAMENTO",
            "DATA",
            "AUTENTICA",
            "DOCUMENTO",
        ]
    ):
        return False

    return any(suf in linha_u for suf in _SUFIXOS_EMPRESA)


def _extrair_empresa_nome(texto):
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    texto_upper = texto.upper()

    rotulos = [
        r"RAZ[ÃA]O\s+SOCIAL[:\s]+(.+)",
        r"NOME\s+DO\s+CONTRIBUINTE[:\s]+(.+)",
        r"NOME\s+EMPRESARIAL[:\s]+(.+)",
        r"EMPRESA[:\s]+(.+)",
    ]

    for padrao in rotulos:
        m = re.search(padrao, texto_upper)
        if m:
            candidato = _normalizar_linha(m.group(1))
            if candidato and _parece_nome_empresa(candidato):
                return candidato

    m_cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)
    if m_cnpj:
        indice_linha = None
        for i, linha in enumerate(linhas):
            if m_cnpj.group() in linha:
                indice_linha = i
                break

        if indice_linha is not None:
            janela = linhas[max(0, indice_linha - 4) : indice_linha + 3]
            for candidato in janela:
                candidato = _normalizar_linha(candidato)
                if _parece_nome_empresa(candidato):
                    return candidato

    for linha in linhas:
        candidato = _normalizar_linha(linha)
        if _parece_nome_empresa(candidato):
            return candidato

    return None


def validar_guia_comprovante(texto: str, competencia_esperada: str):
    texto_upper = texto.upper()

    # ========================================================
    # 1. EMPRESA
    # ========================================================
    empresa_cnpj = None
    empresa_nome = _extrair_empresa_nome(texto)
    m_cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)
    if m_cnpj:
        empresa_cnpj = m_cnpj.group()

    # ========================================================
    # 2. COMPETENCIA
    # ========================================================
    competencia = extrair_competencia_do_texto(texto)

    if not competencia:
        meses_map = {
            "JANEIRO": "01",
            "FEVEREIRO": "02",
            "MARCO": "03",
            "ABRIL": "04",
            "MAIO": "05",
            "JUNHO": "06",
            "JULHO": "07",
            "AGOSTO": "08",
            "SETEMBRO": "09",
            "OUTUBRO": "10",
            "NOVEMBRO": "11",
            "DEZEMBRO": "12",
        }

        m_periodo = re.search(
            r"PER[ÃI]ODO\s+DE\s+APURA[Ã‡C][ÃƒA]O\s*\n?\s*([A-Z]+)/(\d{4})",
            texto_upper,
        )

        if m_periodo:
            mes_nome = m_periodo.group(1).strip()
            ano = m_periodo.group(2).strip()
            mes_num = meses_map.get(mes_nome)
            if mes_num:
                competencia = f"{mes_num}/{ano}"

    if not competencia:
        m_pa = re.search(r"PA:(\d{2}/\d{4})", texto_upper)
        if m_pa:
            competencia = m_pa.group(1)

    # ========================================================
    # 3. VALOR DA GUIA
    # ========================================================
    valor_guia = None

    m_total = re.search(
        r"VALOR\s+TOTAL\s+DO\s+DOCUMENTO\s*\n?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        texto_upper,
    )

    if m_total:
        valor_guia = m_total.group(1)
    else:
        m_generico = re.search(
            r"VALOR[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            texto_upper,
        )
        if m_generico:
            valor_guia = m_generico.group(1)

    # ========================================================
    # 4. DATA DE PAGAMENTO
    # ========================================================
    data_pagamento = None
    m_data = re.search(
        r"(DATA\s+D[EO]\s+PAGAMENTO|PAGO\s+EM|DATA\s+DE\s+D[Ã‰E]BITO|DATA/HORA\s+DA\s+OPERA[Ã‡C][ÃƒA]O)[^\d]*(\d{2}/\d{2}/\d{4})",
        texto_upper,
    )
    if m_data:
        data_pagamento = m_data.group(2)

    # ========================================================
    # 5. VALOR PAGO (COMPROVANTE)
    # ========================================================
    valor_pago = None
    padroes_comprovante = [
        r"VALOR\s+PAGO[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"VALOR\s+DA\s+TRANSA[Ã‡C][AÃƒ]O[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"VALOR\s+FINAL[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"VALOR\s+TOTAL[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
    ]
    for padrao in padroes_comprovante:
        m_pago = re.search(padrao, texto_upper)
        if m_pago:
            valor_pago = m_pago.group(1)
            break

    if not valor_pago:
        valor_pago = valor_guia

    pagamento_identificado = bool(valor_pago or data_pagamento)

    return {
        "empresa": empresa_nome or empresa_cnpj,
        "empresa_nome": empresa_nome,
        "cnpj": empresa_cnpj,
        "competencia": competencia,
        "valor_pago": valor_pago,
        "valor_comprovante": valor_pago,
        "valor_guia": valor_guia,
        "data_pagamento": data_pagamento,
        "pagamento_identificado": pagamento_identificado,
        "valores_coerentes": True if valor_pago == valor_guia else False,
        "valor": valor_guia or valor_pago,
        "erro": not bool(valor_guia and competencia),
    }
