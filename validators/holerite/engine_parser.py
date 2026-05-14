import re

def normalizar_valor(valor):
    if not valor:
        return 0.0
    try:
        # Remove caracteres indesejados mantendo a estrutura numérica
        v = re.sub(r"[^\d,\.]", "", str(valor))
        # Converte formato brasileiro (1.552,00) para float (1552.0)
        if "," in v and "." in v:
            v = v.replace(".", "").replace(",", ".")
        elif "," in v:
            v = v.replace(",", ".")
        return float(v)
    except:
        return 0.0

def buscar_com_padroes(texto, padroes):
    for padrao in padroes:
        # DOTALL permite que o '.' encontre quebras de linha em tabelas OCR
        match = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip(), padrao
    return None, None

def extrair_nome(texto):
    # Padrões com lookahead para interromper a leitura ao chegar em termos do sistema
    padroes = [
        r"NOME\s+FAVORECIDO\s+([A-Z\s]+?)(?=\s{2}|FINALIDADE|NÚMERO|CPF|$)",
        r"NOME\s*[:\-]?\s*([A-Z\s]+?)(?=\s{2}|CBO|ADMISSÃO|AUXILIAR|$)",
        r"\d{2,}\s+([A-Z\s]{10,})" 
    ]
    nome, padrao = buscar_com_padroes(texto, padroes)
    if nome:
        # Limpa sufixos de títulos de documentos que o OCR anexa ao nome
        nome = re.sub(r"(RECIBO DE PAGAMENTO|MENSAL|HOLERITE|DEMONSTRATIVO).*", "", nome, flags=re.IGNORECASE).strip()
    return nome, padrao

def extrair_valor(texto):
    # PRIORIDADE: Captura o valor exato após a indicação de Total Líquido no Holerite
    # O padrão '->' é crucial para o seu modelo de PDF
    padroes = [
        r"TOTAL\s+L[ÍI]QUIDO\s*[-—>]*\s*([\d\.,]+)", 
        r"VALOR\s+L[ÍI]QUIDO\s*[:\-]?\s*([\d\.,]+)",
        # No comprovante, o valor vem antes de 'DATA TRANSFERÊNCIA' e evita telefones 0800
        r"VALOR\s*[\n\r]*\s*([\d\.,]+)(?=\s*DATA\s*TRANSFER[ÊE]NCIA)", 
        r"L[ÍI]QUIDO\s*[:\-]?\s*([\d\.,]+)"
    ]
    valor_str, padrao = buscar_com_padroes(texto, padroes)
    return normalizar_valor(valor_str), padrao

def extrair_data(texto):
    padroes = [
        r"DATA\s+(?:TRANSFER[ÊE]NCIA|PAGAMENTO)\s*[:\-]?\s*([\d/]+)",
        r"DATA\s+LIMITE\s+PARA\s+PAGAMENTO\s*[:\-]?\s*([\d/]+)",
        r"(\d{2}/\d{2}/\d{4})"
    ]
    return buscar_com_padroes(texto, padroes)

def extrair_empresa(texto):
    # Localiza o nome antes do CNPJ ou na primeira linha
    match = re.search(r"^([A-Z\s\-]{5,})", texto) 
    if match and "RECIBO" not in match.group(1):
        return match.group(1).strip()
    
    match_cnpj = re.search(r"([A-Z\s\-]{5,})\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)
    if match_cnpj:
        return match_cnpj.group(1).strip()
    return None

def engine_extracao(texto):
    resultado = {}
    score = 0
    texto_limpo = re.sub(r"\s+", " ", texto.upper())

    nome, padrao_nome = extrair_nome(texto_limpo)
    if nome:
        resultado["nome"] = nome
        score += 30

    valor, padrao_valor = extrair_valor(texto_limpo)
    if valor > 0:
        resultado["valor"] = valor
        score += 40

    data, padrao_data = extrair_data(texto_limpo)
    if data:
        resultado["data"] = data
        score += 20

    empresa = extrair_empresa(texto_limpo)
    if empresa:
        resultado["empresa"] = empresa
        score += 10

    resultado["confianca"] = score
    resultado["debug"] = {"padrao_nome": padrao_nome, "padrao_valor": padrao_valor, "padrao_data": padrao_data}
    return resultado