import re
import utils.tesseract_config
from rapidfuzz import fuzz

from validators.inss.guia_comprovante import validar_guia_comprovante
from validators.inss.dctfweb import validar_dctfweb
from utils.ocr.ocr_inss import extrair_texto_inss


# ------------------------------------------------------------
# NORMALIZA VALOR
# ------------------------------------------------------------
def normalizar_valor(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)

    v = str(v).upper()
    for termo in ["R$", "TOTAL", "VALOR", "APURADO"]:
        v = v.replace(termo, "")
    v = v.strip()

    try:
        v = v.replace(".", "").replace(",", ".")
        return float(v)
    except Exception:
        return None


# ------------------------------------------------------------
# NORMALIZA COMPETÊNCIA
# ------------------------------------------------------------
def normalizar_competencia(texto):
    if not texto:
        return None

    texto = texto.lower()

    meses = {
        "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
        "abril": "04", "maio": "05", "junho": "06", "julho": "07",
        "agosto": "08", "setembro": "09", "outubro": "10",
        "novembro": "11", "dezembro": "12"
    }

    match = re.search(r"\d{2}/\d{4}", texto)
    if match:
        return match.group()

    for nome, numero in meses.items():
        if nome in texto:
            ano = re.search(r"\d{4}", texto)
            if ano:
                return f"{numero}/{ano.group()}"

    return None


# ------------------------------------------------------------
# 🔥 LIMPEZA DE NOME DE EMPRESA (NOVO)
# ------------------------------------------------------------
def limpar_nome_empresa(nome):
    if not nome:
        return ""

    nome = str(nome).upper()

    # remove CNPJ
    nome = re.sub(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", "", nome)

    # remove lixo comum OCR
    lixo = ["CNPJ", "|", ":", "-", ".", ",", "  "]
    for l in lixo:
        nome = nome.replace(l, " ")

    # remove sufixos
    sufixos = ["LTDA", "EIRELI", "ME", "EPP"]
    for s in sufixos:
        nome = nome.replace(s, " ")

    # normaliza espaços
    nome = re.sub(r"\s+", " ", nome).strip()

    return nome


# ------------------------------------------------------------
# 🔥 COMPARAÇÃO INTELIGENTE DE EMPRESA (FINAL)
# ------------------------------------------------------------
def comparar_empresa(e1, e2):
    if not e1 or not e2:
        return False

    e1_limpo = limpar_nome_empresa(e1)
    e2_limpo = limpar_nome_empresa(e2)

    # -----------------------------
    # 1. CNPJ (prioridade máxima)
    # -----------------------------
    cnpj1 = re.sub(r"\D", "", str(e1))
    cnpj2 = re.sub(r"\D", "", str(e2))

    if cnpj1 and cnpj2 and cnpj1 == cnpj2:
        print("🏢 Empresa OK por CNPJ")
        return True

    # -----------------------------
    # 2. CONTÉM (🔥 NOVO - ESSENCIAL)
    # -----------------------------
    if e1_limpo in e2_limpo or e2_limpo in e1_limpo:
        print("🏢 Empresa OK por inclusão")
        return True

    # -----------------------------
    # 3. FUZZY
    # -----------------------------
    score = fuzz.token_sort_ratio(e1_limpo, e2_limpo)

    print(f"🏢 Limpo Guia: {e1_limpo}")
    print(f"🏢 Limpo DCTF: {e2_limpo}")
    print(f"🔍 Similaridade: {score}")

    return score >= 70


# ============================================================
# VALIDATOR
# ============================================================

class INSSValidator:

    def analisar(self, guia_comprovante_pdf, dctfweb_pdf, competencia_esperada, dados_ia=None):

        print("\n🚀 ================= INSS VALIDATOR =================")

        # OCR
        texto_guia = extrair_texto_inss(guia_comprovante_pdf) or ""
        texto_dctf = extrair_texto_inss(dctfweb_pdf) or ""

        # Extração
        guia_parser = validar_guia_comprovante(texto_guia, competencia_esperada)
        guia = {**guia_parser, **dados_ia} if isinstance(dados_ia, dict) else guia_parser
        dctf = validar_dctfweb(texto_dctf, competencia_esperada) or {}

        # -------------------------
        # NORMALIZAÇÃO
        # -------------------------
        valor_guia = normalizar_valor(guia.get("valor_guia") or guia.get("valor"))
        valor_comprovante = normalizar_valor(guia.get("valor_comprovante") or guia.get("valor_pago"))
        valor_dctf = normalizar_valor(dctf.get("valor"))

        competencia_guia = normalizar_competencia(guia.get("competencia"))
        competencia_dctf = normalizar_competencia(dctf.get("competencia"))
        competencia_esperada_norm = normalizar_competencia(competencia_esperada)

        # -------------------------
        # EMPRESA (FINAL 🔥)
        # -------------------------
        empresa_guia_nome = guia.get("empresa")
        empresa_dctf_nome = dctf.get("empresa")

        cnpj_guia = guia.get("cnpj")
        cnpj_dctf = dctf.get("cnpj")

        if empresa_guia_nome and empresa_dctf_nome:
            empresa_ok = comparar_empresa(empresa_guia_nome, empresa_dctf_nome)
        else:
            empresa_ok = comparar_empresa(cnpj_guia, cnpj_dctf)

        empresa_guia = empresa_guia_nome or cnpj_guia
        empresa_dctf = empresa_dctf_nome or cnpj_dctf

        # -------------------------
        # VALIDAÇÕES
        # -------------------------
        confronto_ok = (
            valor_guia is not None and
            valor_dctf is not None and
            abs(valor_guia - valor_dctf) <= 0.02
        )

        comprovante_ok = (
            valor_guia is not None and
            valor_comprovante is not None and
            abs(valor_guia - valor_comprovante) <= 0.02
        )

        competencia_guia_ok = competencia_guia == competencia_esperada_norm
        competencia_dctf_ok = competencia_dctf == competencia_esperada_norm

        pagamento_ok = guia.get("pagamento_identificado") or valor_comprovante is not None

        declaracao_completa_ok = bool(dctf.get("declaracao_completa") or dctf.get("declaracao"))
        relatorio_debitos_ok = bool(dctf.get("relatorio_debitos") or dctf.get("resumo_debitos"))
        relatorio_creditos_ok = bool(dctf.get("relatorio_creditos"))
        recibo_dctf_ok = bool(dctf.get("recibo_entrega"))
        estrutura_dctf_ok = all([
            declaracao_completa_ok,
            relatorio_debitos_ok,
            relatorio_creditos_ok,
            recibo_dctf_ok,
        ])

        # -------------------------
        # ERROS
        # -------------------------
        erros = []
        avisos = []

        if not confronto_ok:
            erros.append(f"Valor guia ({valor_guia}) != DCTF ({valor_dctf})")

        if not comprovante_ok:
            erros.append(f"Valor guia ({valor_guia}) != comprovante ({valor_comprovante})")

        if not empresa_ok:
            erros.append("Empresa divergente entre Guia e DCTFWeb")

        if not competencia_guia_ok:
            erros.append("Competência Guia incorreta")

        if not competencia_dctf_ok:
            erros.append("Competência DCTF incorreta")

        if not declaracao_completa_ok:
            erros.append("DCTFWeb sem Declaração completa")

        if not relatorio_debitos_ok:
            erros.append("DCTFWeb sem Relatório de Débitos")

        if not relatorio_creditos_ok:
            erros.append("DCTFWeb sem Relatório de Créditos")

        if not recibo_dctf_ok:
            erros.append("DCTFWeb sem Recibo")

        if not pagamento_ok:
            avisos.append("Pagamento não identificado")

        validacoes = [
            {"item": "Valor Guia vs DCTF", "ok": confronto_ok},
            {"item": "Valor Guia vs Comprovante", "ok": comprovante_ok},
            {"item": "Empresa", "ok": empresa_ok},
            {"item": "Competência Guia", "ok": competencia_guia_ok},
            {"item": "Competência DCTF", "ok": competencia_dctf_ok},
            {"item": "Declaração completa DCTFWeb", "ok": declaracao_completa_ok},
            {"item": "Relatório de Débitos DCTFWeb", "ok": relatorio_debitos_ok},
            {"item": "Relatório de Créditos DCTFWeb", "ok": relatorio_creditos_ok},
            {"item": "Recibo DCTFWeb", "ok": recibo_dctf_ok},
            {"item": "Pagamento Identificado", "ok": bool(pagamento_ok)},
        ]

        # -------------------------
        # STATUS
        # -------------------------
        if erros:
            status = "Reprovado"
        elif avisos:
            status = "Parcial"
        else:
            status = "Aprovado"

        return {
            "status": status,
            "mensagem": "Validação concluída" if not erros else "Validação com inconsistências",

            "empresa": empresa_guia,
            "empresa_guia": empresa_guia,
            "empresa_dctf": empresa_dctf,

            "competencia": competencia_guia,
            "valor_inss": valor_guia,
            "data_pagamento": guia.get("data_pagamento"),

            "erros": erros,
            "avisos": avisos,

            "valor_guia": valor_guia,
            "valor_comprovante": valor_comprovante,
            "valor_dctf": valor_dctf,

            "empresa_ok": empresa_ok,
            "competencia_guia_ok": competencia_guia_ok,
            "competencia_dctf_ok": competencia_dctf_ok,
            "valor_ok": confronto_ok,
            "comprovante_ok": comprovante_ok,
            "pagamento_identificado": pagamento_ok,
            "estrutura_dctf_ok": estrutura_dctf_ok,
            "declaracao_completa_ok": declaracao_completa_ok,
            "relatorio_debitos_ok": relatorio_debitos_ok,
            "relatorio_creditos_ok": relatorio_creditos_ok,
            "recibo_dctf_ok": recibo_dctf_ok,
            "validacoes": validacoes
        }
