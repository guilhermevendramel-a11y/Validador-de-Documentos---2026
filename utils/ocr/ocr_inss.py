import re

from utils.ocr import extrair_documento_inteligente


def normalizar_texto_ocr(texto):
    texto = (texto or "").upper()
    texto = texto.replace("|", "I").replace("O0", "00")
    return re.sub(r" +", " ", texto)


def extrair_competencia_do_texto(texto):
    texto_upper = normalizar_texto_ocr(texto)
    m_pa = re.search(r"PA[:\s]*(\d{2}/\d{4})", texto_upper)
    if m_pa:
        return m_pa.group(1)

    meses_map = {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "MARÇO": "03",
        "ABRIL": "04", "MAIO": "05", "JUNHO": "06", "JULHO": "07",
        "AGOSTO": "08", "SETEMBRO": "09", "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12"
    }
    regex_extenso = r"PER[ÍI]ODO\s+DE\s+APURA[CÇ][AÃ]O\s*\n?\s*([A-ZÇ]+)[/\s]*(\d{4})"
    m_ext = re.search(regex_extenso, texto_upper)
    if m_ext:
        nome_mes = m_ext.group(1)
        ano = m_ext.group(2)
        for mes_nome, mes_num in meses_map.items():
            if mes_nome in nome_mes:
                return f"{mes_num}/{ano}"

    datas_isoladas = re.findall(r"(?<!\d/)\b(\d{2}/\d{4})\b", texto_upper)
    return datas_isoladas[0] if datas_isoladas else None


def extrair_texto_inss(pdf_path):
    resultado = extrair_documento_inteligente(pdf_path, tipo_documento="inss", usar_ocr=True)
    texto = resultado.get("texto", "")
    comp = extrair_competencia_do_texto(texto)
    print(f"[INSS] metodo={resultado.get('metodo')} qualidade={resultado.get('qualidade')} competencia={comp}")
    return texto
