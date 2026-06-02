import re


def extrair_dados_trct(texto):
    """
    Extrai dados-chave do TRCT:
    - Valor liquido
    - Causa do afastamento
    - Tipo de desligamento inferido (pedido_demissao ou dispensa)
    """
    dados = {
        "valor_liquido": None,
        "valor_formatado": None,
        "causa_afastamento": "",
        "cod_afastamento": "",
        "tipo_desligamento": "indefinido",
    }

    if not texto:
        return dados

    # Busca o padrao 'VALOR LIQUIDO' e captura o numero que vem depois
    padrao_valor = r"VALOR\s+L[ÍI]QUIDO\s*(?:R\$\s*)?([\d.,]+)"
    match_valor = re.search(padrao_valor, texto, re.IGNORECASE)

    if match_valor:
        valor_str = match_valor.group(1)
        dados["valor_formatado"] = valor_str
        try:
            dados["valor_liquido"] = float(valor_str.replace('.', '').replace(',', '.'))
        except ValueError:
            dados["valor_liquido"] = None

    # Tenta extrair a causa do afastamento em uma linha do TRCT
    padrao_causa = r"CAUSA\s+DO\s+AFASTAMENTO[:\s\-]*([^\n\r]+)"
    match_causa = re.search(padrao_causa, texto, re.IGNORECASE)
    if match_causa:
        dados["causa_afastamento"] = match_causa.group(1).strip()

    # Tenta extrair codigo de afastamento (ex.: RA1, PD0)
    padrao_cod_afast = r"COD\.\s*AFASTAMENTO[:\s\-]*([A-Z0-9]{2,4})"
    match_cod = re.search(padrao_cod_afast, texto, re.IGNORECASE)
    if match_cod:
        dados["cod_afastamento"] = match_cod.group(1).strip().upper()

    texto_base = f"{dados['causa_afastamento']} {texto}".upper()
    cod_afastamento = dados["cod_afastamento"]

    chaves_pedido = [
        "PEDIDO DE DEMISSAO",
        "DEMISSAO A PEDIDO",
        "INICIATIVA DO EMPREGADO",
        "RESCISAO A PEDIDO",
        "PELO EMPREGADO",
    ]
    chaves_dispensa = [
        "DISPENSA SEM JUSTA CAUSA",
        "DISPENSA",
        "DEMISSAO SEM JUSTA CAUSA",
        "INICIATIVA DO EMPREGADOR",
        "RESCISAO SEM JUSTA CAUSA",
        "MANDADO EMBORA",
        "PELO EMPREGADOR",
        "EXTINCAO NORMAL DO CONTRATO DE TRABALHO POR PRAZO DETERMINADO",
        "EXTINÇÃO NORMAL DO CONTRATO DE TRABALHO POR PRAZO DETERMINADO",
        "TERMINO DE CONTRATO DE EXPERIENCIA",
        "TÉRMINO DE CONTRATO DE EXPERIÊNCIA",
    ]

    if any(chave in texto_base for chave in chaves_pedido):
        dados["tipo_desligamento"] = "pedido_demissao"
    elif any(chave in texto_base for chave in chaves_dispensa):
        dados["tipo_desligamento"] = "dispensa"
    elif cod_afastamento in {"PD0", "PD1", "PD2", "PD3"}:
        # Codigos PD* tipicamente ligados a encerramento de contrato por prazo determinado
        dados["tipo_desligamento"] = "dispensa"

    return dados
