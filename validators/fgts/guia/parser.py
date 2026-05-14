import re
from utils.validations import extrair_valor, extrair_data_pagamento, extrair_competencia


def _valor_para_float(valor):
    if valor is None:
        return 0.0
    valor = str(valor).strip().replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return 0.0


def _linhas(texto):
    return [linha.strip() for linha in (texto or "").replace("\r", "").splitlines() if linha.strip()]


def _extrair_valor_por_rotulo(texto, rotulos):
    linhas = _linhas(texto)

    for indice, linha in enumerate(linhas):
        linha_up = linha.upper()
        if any(rotulo in linha_up for rotulo in rotulos):
            candidatos = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", linha)
            if candidatos:
                return candidatos[-1]

            for proxima in linhas[indice + 1:indice + 4]:
                candidatos_proxima = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", proxima)
                if candidatos_proxima:
                    return candidatos_proxima[-1]

    return None


def _extrair_empresa_por_linha(texto):
    linhas = _linhas(texto)

    for indice, linha in enumerate(linhas):
        linha_up = linha.upper()

        if "NOME/RAZÃO SOCIAL DO EMPREGADOR" in linha_up or "NOME/RAZAO SOCIAL DO EMPREGADOR" in linha_up:
            if indice + 1 < len(linhas):
                return linhas[indice + 1].strip()

        match = re.search(r"(?:NOME DO PAGADOR|NOME DO DEVEDOR):\s*([A-Z0-9 .&/-]{5,})", linha, re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()

    return None


def _extrair_competencia_guia(texto):
    linhas = _linhas(texto)

    for indice, linha in enumerate(linhas):
        if "COMPETÊNCIA" in linha.upper() or "COMPETENCIA" in linha.upper():
            trecho = "\n".join(linhas[indice:indice + 10])
            match = re.search(r"\b(0[1-9]|1[0-2])\s*/\s*(20\d{2})\b", trecho)
            if match:
                return f"{match.group(1)}/{match.group(2)}"

    return extrair_competencia(texto)


def _extrair_data_pagamento_guia(texto):
    match = re.search(r"Pagamento efetuado em\s*(\d{2}/\d{2}/\d{4})", texto or "", re.IGNORECASE)
    if match:
        return match.group(1)
    return extrair_data_pagamento(texto)


def extrair_resumo_guia_comprovante(texto):
    valor_guia = _extrair_valor_por_rotulo(
        texto,
        [
            "VALOR A RECOLHER",
            "TOTAL DA GUIA",
        ],
    )
    valor_comprovante = _extrair_valor_por_rotulo(
        texto,
        [
            "VALOR FINAL",
            "VALOR DA TRANSAÇÃO",
            "VALOR DA TRANSACAO",
            "VALOR DO DOCUMENTO",
        ],
    )
    valor = valor_guia or valor_comprovante or extrair_valor(texto)

    return {
        "empresa": _extrair_empresa_por_linha(texto) or _extrair_empresa_bancaria(texto),
        "competencia": _extrair_competencia_guia(texto),
        "data_pagamento": _extrair_data_pagamento_guia(texto),
        "valor_guia": _valor_para_float(valor_guia or valor),
        "valor_guia_formatado": valor_guia or valor,
        "valor_comprovante": _valor_para_float(valor_comprovante or valor),
        "valor_comprovante_formatado": valor_comprovante or valor,
        "valor_total": _valor_para_float(valor),
        "valor_total_formatado": valor,
    }


def extrair_dados_guia(texto):
    """Extrai dados do Comprovante ou Guia tratando máscaras bancárias."""
    # O GFD (Identificador) é o elo de ligação para evitar o 'Pendente'
    gfd_match = re.search(r"(\d{16}-\d)", texto)
    
    return {
        "empresa": _extrair_empresa_bancaria(texto),
        "competencia": extrair_competencia(texto),
        # Garante que pegamos o valor pago real do comprovante
        "valor_pago": extrair_valor(texto),
        "data_pagamento": extrair_data_pagamento(texto),
        "gfd": gfd_match.group(1) if gfd_match else None
    }

def _extrair_empresa_bancaria(texto):
    """Captura o nome da empresa mesmo com asteriscos do banco."""
    # Busca após rótulos comuns em comprovantes do Santander/Caixa
    padroes = [
        r"PAGADOR[:\s]+([A-Z0-9 \-\.\*]{5,})",
        r"DEVEDOR[:\s]+([A-Z0-9 \-\.\*]{5,})",
        r"NOME/RAZÃO SOCIAL[:\s]+([A-Z0-9 \-\.\*]{5,})"
    ]
    for p in padroes:
        m = re.search(p, texto.upper())
        if m: return m.group(1).strip()
    return None
