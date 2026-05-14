import re


def extrair_colaboradores(texto):
    linhas = texto.split("\n")
    colaboradores = []

    for linha in linhas:
        linha = linha.strip().upper()

        # 🚫 ignora lixo
        if any(x in linha for x in [
            "FOLHA", "CNPJ", "PERÍODO", "ENDEREÇO",
            "RAZÃO SOCIAL", "LOCAL", "SALÁRIO",
            "INSS", "TOTAL", "ARREDONDAMENTO"
        ]):
            continue

        # 👤 nome válido (regra simples)
        if len(linha) > 10 and " " in linha:

            # evita números
            if re.search(r"\d", linha):
                continue

            colaboradores.append({
                "nome": linha,
                "competencia": None,
                "competencia_ok": True
            })

    return colaboradores