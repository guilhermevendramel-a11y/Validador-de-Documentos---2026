import re

def extrair_trabalhadores(texto: str) -> list:

    trabalhadores = []
    tomador_atual = None
    capturar = False

    for linha in texto.splitlines():

        l = linha.strip()
        l_upper = l.upper()

        # Detecta tomador (flexível)
        m_tomador = re.search(r"(CNO|CNPJ)[\s:]*([\d./-]+)", l_upper)
        if m_tomador:
            tomador_atual = m_tomador.group(2)
            capturar = True
            continue

        # Para quando acabar bloco
        if "TOTAL" in l_upper and "TOMADOR" in l_upper:
            capturar = False

        if not capturar:
            continue

        # Ignora lixo
        if any(x in l_upper for x in [
            "CPF", "CATEGORIA", "REMUNERA", "VALOR", "JUROS", "MULTA"
        ]):
            continue

        # 🔥 EXTRAÇÃO FLEXÍVEL (FUNCIONA COM OCR)
        match = re.search(r"\d{2}/\d{4}\s+([A-ZÁÉÍÓÚÃÕÇ ]{5,})", l_upper)

        if match:
            nome = match.group(1).strip()

            if len(nome.split()) >= 2:
                trabalhadores.append({
                    "nome": nome.title(),
                    "tomador": tomador_atual
                })

    return trabalhadores