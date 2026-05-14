import re

def extrair_dados_trct(texto):
    """
    Extrai o Valor Líquido do TRCT de forma genérica.
    """
    dados = {"valor_liquido": None, "valor_formatado": None}
    
    # Busca o padrão 'VALOR LÍQUIDO' e captura o número que vem depois
    padrao_valor = r"VALOR\s+LÍQUIDO\s*(?:R\$\s*)?([\d.,]+)"
    match_valor = re.search(padrao_valor, texto, re.IGNORECASE)
    
    if match_valor:
        valor_str = match_valor.group(1)
        dados["valor_formatado"] = valor_str
        # Converte para float (ex: 4.327,20 -> 4327.20) para permitir batimentos
        try:
            dados["valor_liquido"] = float(valor_str.replace('.', '').replace(',', '.'))
        except ValueError:
            dados["valor_liquido"] = None
            
    return dados