import re


def extrair_dados_va(texto_completo):

    resultado = {
        "colaboradores": [],
        "soma_extraida": 0.0,
        "total_documento": 0.0
    }

    if not texto_completo:
        return resultado

    # ==============================
    # 1️⃣ NORMALIZAÇÃO
    # ==============================

    texto = texto_completo.upper()
    texto = re.sub(r'\s+', ' ', texto)
    texto = texto.replace(" R$", "\nR$")

    total = 0.0

    # ==============================
    # 2️⃣ ENCONTRAR TODOS OS CPFs
    # ==============================

    padrao_cpf = r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}'
    cpfs = list(re.finditer(padrao_cpf, texto))

    for cpf_match in cpfs:

        inicio = cpf_match.start()

        # ==============================
        # 3️⃣ BUSCAR NOME ANTES DO CPF
        # ==============================

        trecho_antes = texto[max(0, inicio - 200):inicio]

        nome_match = re.findall(
            r'([A-ZÀ-Ú]{3,}(?:\s+[A-ZÀ-Ú]{2,}){1,6})',
            trecho_antes
        )

        if not nome_match:
            continue

        nome = nome_match[-1].strip()

        if any(x in nome for x in [
            "RESULTADO",
            "PEDIDO",
            "PAGAMENTO",
            "VALOR",
            "STATUS",
            "PRODUTO",
            "EMPRESA"
        ]):
            continue

        # ==============================
        # 4️⃣ BUSCAR VALOR APÓS O CPF
        # ==============================

        trecho_depois = texto[inicio:inicio + 400]

        valores = re.findall(
            r'R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2})',
            trecho_depois
        )

        if not valores:
            continue

        # pegar primeiro valor plausível
        valor_float = None

        for v in valores:
            try:
                vf = float(v.replace(".", "").replace(",", "."))
                if 10 <= vf <= 5000:  # filtro inteligente
                    valor_float = vf
                    break
            except:
                continue

        if not valor_float:
            continue

        total += valor_float

        resultado["colaboradores"].append({
            "nome": nome,
            "valor": round(valor_float, 2)
        })

    resultado["soma_extraida"] = round(total, 2)

    # ==============================
    # 5️⃣ TOTAL DO DOCUMENTO
    # ==============================

    todos_valores = re.findall(
        r'R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2})',
        texto
    )

    valores_convertidos = []

    for v in todos_valores:
        try:
            valores_convertidos.append(
                float(v.replace(".", "").replace(",", "."))
            )
        except:
            continue

    if valores_convertidos:
        resultado["total_documento"] = max(valores_convertidos)

    return resultado