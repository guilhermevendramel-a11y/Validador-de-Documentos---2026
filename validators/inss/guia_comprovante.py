import re
from utils.ocr.ocr_inss import extrair_competencia_do_texto
from utils.validations import (
    extrair_valor,
    extrair_data_pagamento
)

# ============================================================
# VALIDAR GUIA + COMPROVANTE INSS (VERSÃO FINAL ULTRA-RESILIENTE 🚀)
# ============================================================

def validar_guia_comprovante(texto: str, competencia_esperada: str):
    texto_upper = texto.upper()
    
    # ========================================================
    # 1. EMPRESA (CNPJ)
    # ========================================================
    empresa = None
    m_cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)
    if m_cnpj:
        empresa = m_cnpj.group()

    # ========================================================
    # 2. 🔥 COMPETÊNCIA (ÂNCORA: "PERÍODO DE APURAÇÃO")
    # ========================================================
    competencia = extrair_competencia_do_texto(texto)

    if not competencia:
        meses_map = {
            'JANEIRO': '01', 'FEVEREIRO': '02', 'MARCO': '03', 'ABRIL': '04',
            'MAIO': '05', 'JUNHO': '06', 'JULHO': '07', 'AGOSTO': '08',
            'SETEMBRO': '09', 'OUTUBRO': '10', 'NOVEMBRO': '11', 'DEZEMBRO': '12'
        }

        # Busca o texto que vem logo após ou abaixo de "PERÍODO DE APURAÇÃO"
        # O padrão ([A-Z]+)/(\d{4}) captura "OUTUBRO/2025"
        m_periodo = re.search(r"PER[ÍI]ODO\s+DE\s+APURA[ÇC][ÃA]O\s*\n?\s*([A-Z]+)/(\d{4})", texto_upper)
        
        if m_periodo:
            mes_nome = m_periodo.group(1).strip()
            ano = m_periodo.group(2).strip()
            mes_num = meses_map.get(mes_nome)
            if mes_num:
                competencia = f"{mes_num}/{ano}"

    # Fallback: Tenta capturar o padrão "PA:MM/AAAA" que aparece na tabela de composição
    if not competencia:
        m_pa = re.search(r"PA:(\d{2}/\d{4})", texto_upper)
        if m_pa:
            competencia = m_pa.group(1)

    # ========================================================
    # 3. 🔥 VALOR DA GUIA (ÂNCORA: "VALOR TOTAL DO DOCUMENTO")
    # ========================================================
    valor_guia = None
    
    # No seu documento, o valor está logo abaixo ou após este rótulo
    m_total = re.search(r"VALOR\s+TOTAL\s+DO\s+DOCUMENTO\s*\n?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", texto_upper)
    
    if m_total:
        valor_guia = m_total.group(1)
    else:
        # Tenta buscar "VALOR:" seguido de quantia (comum no rodapé ou comprovante)
        m_generico = re.search(r"VALOR[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", texto_upper)
        if m_generico:
            valor_guia = m_generico.group(1)

    # ========================================================
    # 4. DATA DE PAGAMENTO
    # ========================================================
    data_pagamento = None
    m_data = re.search(
        r"(DATA\s+D[EO]\s+PAGAMENTO|PAGO\s+EM|DATA\s+DE\s+D[ÉE]BITO|DATA/HORA\s+DA\s+OPERA[ÇC][ÃA]O)[^\d]*(\d{2}/\d{2}/\d{4})",
        texto_upper
    )
    if m_data:
        data_pagamento = m_data.group(2)

    # ========================================================
    # 5. VALOR PAGO (COMPROVANTE)
    # ========================================================
    valor_pago = None
    padroes_comprovante = [
        r"VALOR\s+PAGO[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        r"VALOR\s+DA\s+TRANSA[ÇC][AÃ]O[:\s]+(?:R\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
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

    # ========================================================
    # RETORNO FINAL
    # ========================================================
    pagamento_identificado = bool(valor_pago or data_pagamento)
    
    return {
        "empresa": empresa,
        "competencia": competencia,
        "valor_pago": valor_pago,
        "valor_comprovante": valor_pago,
        "valor_guia": valor_guia,
        "data_pagamento": data_pagamento,
        "pagamento_identificado": pagamento_identificado,
        "valores_coerentes": True if valor_pago == valor_guia else False,
        "valor": valor_guia or valor_pago,
        "erro": not bool(valor_guia and competencia)
    }
