import re


def _quebrar_paginas(texto_completo):
    return [bloco.strip() for bloco in re.split(r"\f", str(texto_completo or "")) if bloco.strip()]


def extrair_dados_seguro_universal(texto_completo):

    res = {
        "empresa": "Não identificada",
        "vigencia": "Vigência não localizada",
        "valor_pago": "0,00",
        "data_pagamento": "Não identificada"
    }

    if not texto_completo:
        return res

    # ==============================
    # NORMALIZAÇÃO
    # ==============================

    texto_original = texto_completo
    texto = texto_completo.upper()
    paginas = _quebrar_paginas(texto_completo)
    blocos_busca = list(reversed(paginas)) if paginas else [texto_original]
    if texto_original not in blocos_busca:
        blocos_busca.append(texto_original)

    # ==============================
    # 1️⃣ EMPRESA (via CNPJ)
    # ==============================

    match_cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto_original)

    if match_cnpj:
        inicio = max(0, match_cnpj.start() - 150)
        trecho = texto_original[inicio:match_cnpj.start()]
        linhas = trecho.split("\n")

        for linha in reversed(linhas):
            linha = linha.strip()
            if len(linha) > 5 and not any(x in linha.upper() for x in ["SEGUROS", "MAPFRE", "BRADESCO", "PORTO"]):
                res["empresa"] = linha
                break

    if res["empresa"] == "Não identificada":
        match_empresa = re.search(r"RAZ[ÃA]O SOCIAL[:\s]+(.+?)(?:CNPJ|$)", texto)
        if match_empresa:
            res["empresa"] = match_empresa.group(1).strip()

    # ==============================
    # 2️⃣ VIGÊNCIA
    # ==============================

    match_inicio = re.search(
        r"IN[ÍI]CIO DE VIG[ÊE]NCIA.*?(\d{2}/\d{2}/\d{4})",
        texto
    )

    match_fim = re.search(
        r"FIM DE VIG[ÊE]NCIA.*?(\d{2}/\d{2}/\d{4})",
        texto
    )

    if match_inicio and match_fim:
        res["vigencia"] = f"{match_inicio.group(1)} a {match_fim.group(1)}"
    else:
        match_vigencia = re.search(
            r"(\d{2}/\d{2}/\d{4}).{0,25}?(?:A|ATÉ|-).{0,25}?(\d{2}/\d{2}/\d{4})",
            texto
        )
        if match_vigencia:
            res["vigencia"] = f"{match_vigencia.group(1)} a {match_vigencia.group(2)}"

    # ==============================
    # 3️⃣ VALOR PAGO (FORA DO ELSE!)
    # ==============================

    padroes_valor_pagamento = [
        r"\(=\)\s*VALOR DO PAGAMENTO.*?(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"VALOR DO PAGAMENTO.*?(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"COMPROVANTE DE PAGAMENTO.*?(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"DADOS DO PAGAMENTO.*?VALOR[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"COMPROVANTE DE OPERAC[AOÃÇ].*?VALOR[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"PREMIO LIQUIDO.*?(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"VALOR LIQUIDO.*?(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"VALOR DO BOLETO.*?(\d{1,3}(?:\.\d{3})*,\d{2})",
    ]

    for bloco in blocos_busca:
        for padrao in padroes_valor_pagamento:
            match = re.search(padrao, bloco, re.DOTALL)
            if match:
                valor = match.group(1)
                try:
                    valor_float = float(valor.replace(".", "").replace(",", "."))
                    res["valor_pago"] = "{:,.2f}".format(valor_float)\
                        .replace(",", "X")\
                        .replace(".", ",")\
                        .replace("X", ".")
                    break
                except:
                    continue
        if res["valor_pago"] != "0,00":
            break

    # ==============================
    # 4️⃣ DATA DE PAGAMENTO
    # ==============================

    for bloco in blocos_busca:
        match_data = re.search(
            r"DATA DE PAGAMENTO[:\s]+(\d{2}[\/\.\-]\d{2}[\/\.\-]\d{4})",
            bloco,
            re.I,
        )

        if match_data:
            res["data_pagamento"] = match_data.group(1).replace(".", "/").replace("-", "/")
            break
    else:
        for bloco in blocos_busca:
            datas = re.findall(r"\d{2}[\/\.\-]\d{2}[\/\.\-]\d{4}", bloco)
            if datas:
                res["data_pagamento"] = datas[-1].replace(".", "/").replace("-", "/")
                break

    return res
