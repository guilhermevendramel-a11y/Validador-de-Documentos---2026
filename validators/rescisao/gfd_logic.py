import re

def extrair_dados_gfd(texto):
    """
    Extrai o valor a recolher da Guia do FGTS Digital (GFD).
    """
    dados = {"valor_gfd": None, "valor_formatado": None}
    
    # Busca o valor total da guia baseado no termo padrão 'Valor a recolher' 
    padrao_valor = r"Valor\s+a\s+recolher\s*([\d.,]+)"
    match_valor = re.search(padrao_valor, texto, re.IGNORECASE)
    
    if match_valor:
        valor_str = match_valor.group(1)
        dados["valor_formatado"] = valor_str
        try:
            dados["valor_gfd"] = float(valor_str.replace('.', '').replace(',', '.'))
        except ValueError:
            dados["valor_gfd"] = None
            
    return dados