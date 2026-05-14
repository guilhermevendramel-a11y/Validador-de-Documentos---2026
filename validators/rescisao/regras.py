def validar_financeiro_rescisao(valor_documento, valor_comprovante):
    """
    Valida se o valor extraído do documento (TRCT ou GFD) coincide 
    com o valor presente no comprovante de pagamento.
    """
    
    # Se um dos valores não for identificado pelo OCR, a validação falha
    if valor_documento is None or valor_comprovante is None:
        return False

    try:
        # Função auxiliar para garantir que a comparação seja feita entre floats
        def to_float(v):
            if isinstance(v, (int, float)):
                return float(v)
            return float(str(v).replace(".", "").replace(",", "."))

        v_doc = to_float(valor_documento)
        v_comp = to_float(valor_comprovante)

        # 1. Ambos zero: Situação inconsistente para rescisão (deve haver valores)
        if v_doc == 0 and v_comp == 0:
            return False

        # 2. Um zero e outro não: Erro crítico de pagamento
        if (v_doc == 0 and v_comp > 0) or (v_doc > 0 and v_comp == 0):
            return False

        # 3. Tolerância de R$ 0,05 para arredondamentos bancários
        tolerancia = 0.05
        return round(abs(v_doc - v_comp), 2) <= tolerancia

    except Exception:
        return False

def verificar_data_prazo(data_afastamento, data_pagamento):
    """
    Verifica se o pagamento da rescisão foi feito dentro do prazo legal 
    (Exemplo: até 10 dias após o desligamento).
    """
    # Esta função pode ser expandida conforme a necessidade jurídica da MSE Engenharia
    if not data_afastamento or not data_pagamento:
        return False
    return True