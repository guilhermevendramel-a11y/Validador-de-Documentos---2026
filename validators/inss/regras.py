# ============================================================
# REGRAS INSS (AUDITORIA COMPLETA)
# ============================================================

def normalizar_valor(valor):
    if not valor:
        return None

    try:
        valor = str(valor).replace(".", "").replace(",", ".")
        return float(valor)
    except:
        return None


# ------------------------------------------------------------
# 🔥 DETECTA JUROS / MULTA (NOVO)
# ------------------------------------------------------------
def identificar_pagamento_atraso(texto_guia):
    if not texto_guia:
        return False

    texto = texto_guia.upper()

    palavras_chave = [
        "JUROS",
        "MULTA",
        "ENCARGOS",
        "ACRÉSCIMOS",
        "ACRESCIMOS",
        "MORA",
        "SELIC"
    ]

    return any(p in texto for p in palavras_chave)


# ------------------------------------------------------------
# 🔥 VALIDA VALORES COM INTELIGÊNCIA (NOVO)
# ------------------------------------------------------------
def validar_valores_com_atraso(valor_guia, valor_dctf, texto_guia, tolerancia=0.01):

    v_guia = normalizar_valor(valor_guia)
    v_dctf = normalizar_valor(valor_dctf)

    if v_guia is None or v_dctf is None:
        return False, False

    # ✔ valores iguais
    if abs(v_guia - v_dctf) <= tolerancia:
        return True, False

    # 🔥 guia maior → pode ser atraso
    if v_guia > v_dctf:
        tem_juros = identificar_pagamento_atraso(texto_guia)

        if tem_juros:
            return True, True  # válido com juros

    return False, False


# ------------------------------------------------------------
# 🔥 VALIDA ESTRUTURA DA DCTFWEB
# ------------------------------------------------------------
def validar_estrutura_dctf(dctf):

    # compatível com seu novo dctfweb.py
    return (
        dctf.get("recibo_entrega") and
        dctf.get("resumo_debitos")
    )


# ------------------------------------------------------------
# 🔥 DETECTA DCTF ZERADA
# ------------------------------------------------------------
def dctf_zerada(valor_dctf):
    v = normalizar_valor(valor_dctf)
    return v == 0.0


# ------------------------------------------------------------
# 🔥 REGRA PRINCIPAL (CÉREBRO)
# ------------------------------------------------------------
def validar_inss_regras(guia, dctf):

    erros = []
    avisos = []

    valor_guia = guia.get("valor")
    valor_dctf = dctf.get("valor")

    texto_guia = guia.get("texto", "")  # 🔥 IMPORTANTE

    # ========================================================
    # 🔥 REGRA 1: DCTF ZERADA
    # ========================================================
    if dctf_zerada(valor_dctf):
        return {
            "status": "Aprovado",
            "erros": [],
            "avisos": ["DCTFWeb zerada - guia não obrigatória"],
            "detalhes": {
                "dctf_zerada": True
            }
        }

    # ========================================================
    # 🔥 REGRA 2: VALORES (COM JUROS 🔥)
    # ========================================================
    valor_ok, com_juros = validar_valores_com_atraso(
        valor_guia,
        valor_dctf,
        texto_guia
    )

    if not valor_ok:
        erros.append("Valor da guia incompatível com a DCTFWeb")
    elif com_juros:
        avisos.append("Pagamento em atraso com juros/multa identificado")

    # ========================================================
    # 🔥 REGRA 3: ESTRUTURA DCTF
    # ========================================================
    if not validar_estrutura_dctf(dctf):
        erros.append("DCTFWeb incompleta (faltam seções obrigatórias)")

    # ========================================================
    # 🔥 REGRA 4: PAGAMENTO
    # ========================================================
    if not guia.get("pagamento_identificado"):
        avisos.append("Pagamento não identificado")

    # ========================================================
    # 🔥 STATUS FINAL
    # ========================================================
    if erros:
        status = "Reprovado"
    elif avisos:
        status = "Parcial"
    else:
        status = "Aprovado"

    return {
        "status": status,
        "erros": erros,
        "avisos": avisos,
        "detalhes": {
            "valores_ok": valor_ok,
            "com_juros": com_juros,
            "estrutura_ok": validar_estrutura_dctf(dctf),
            "dctf_zerada": dctf_zerada(valor_dctf)
        }
    }