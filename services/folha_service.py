import re
from utils.ocr.ocr_folha import extrair_texto_folha
from utils.gemini.folha import extrair_folha_inteligente
from validators.folha_pagamento.rules import validar_folha


# ============================================================
# 🔹 COMPETÊNCIA
# ============================================================
def extrair_competencia(texto):
    if not texto:
        return None

    texto = texto.upper()

    # Prioriza "Período: DD/MM/AAAA a DD/MM/AAAA" para não confundir
    # com data de emissão/impressão do relatório.
    m = re.search(
        r"PER[ÍI]ODO\s*:\s*(\d{2})\/(\d{2})\/(\d{4})\s+A\s+(\d{2})\/(\d{2})\/(\d{4})",
        texto,
    )
    if m:
        mes_inicio, ano_inicio = m.group(2), m.group(3)
        return f"{mes_inicio}/{ano_inicio}"

    m = re.search(r"EXTRATO\s+MENSAL\s*\n\s*(0[1-9]|1[0-2])\/\d{4}\b", texto)
    if m:
        return re.search(r"(0[1-9]|1[0-2])\/\d{4}", m.group()).group()

    m = re.search(r"\b(0[1-9]|1[0-2])\/\d{4}\b", texto)
    if m:
        return m.group()

    return None


# ============================================================
# 🔹 EMPRESA
# ============================================================
def extrair_empresa(texto):
    if not texto:
        return None

    texto = texto.upper()
    linhas = texto.split("\n")

    padroes = [
        r"RAZ[AÃ]O\s+SOCIAL[:\s]+([A-Z0-9 .&/-]{5,})",
        r"EMPRESA[:\s]+([A-Z0-9 .&/-]{5,})",
    ]

    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            empresa = re.split(r"CNPJ|COMPET[ÊE]NCIA|FOLHA", match.group(1))[0].strip()
            if len(empresa.split()) >= 2:
                return empresa

    for i, linha in enumerate(linhas):
        if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", linha.strip()) and i + 1 < len(linhas):
            possivel = re.sub(r"^\d+\s*-\s*", "", linhas[i + 1].strip())
            if len(possivel) > 5 and len(possivel.split()) >= 2:
                return possivel

        if "CNPJ" in linha and i > 0:
            possivel = linhas[i - 1].strip()
            if len(possivel) > 5 and len(possivel.split()) >= 2:
                return possivel

    return None


# ============================================================
# 🔥 FILTRO DE NOMES (VERSÃO DEFINITIVA)
# ============================================================
def nome_valido(nome, empresa=None):
    if not nome:
        return False

    nome = nome.strip().upper()

    # 🔥 remove OCR bug (R E S U M O → RESUMO)
    nome_sem_espaco = nome.replace(" ", "")

    if len(nome) < 10:
        return False

    # ❌ não pode ter número
    if re.search(r"\d", nome):
        return False

    # precisa ter pelo menos 2 palavras
    if len(nome.split()) < 2:
        return False

    # ❌ remove empresa
    if empresa and nome == empresa:
        return False

    # 🔥 palavras proibidas (com e sem espaço)
    proibidas = [
        "FOLHA", "CNPJ", "PERIODO", "ENDERECO",
        "RAZAO", "LOCAL", "SALARIO", "INSS",
        "TOTAL", "ARREDONDAMENTO", "DATA",
        "FUNCAO", "CARGO", "ADMISSAO", "SITUACAO",
        "PROVENTOS", "DESCONTOS", "BASE",
        "FGTS", "LANCAMENTOS", "TERCEIROS",
        "PIS", "IRRF", "OCORRENCIA", "RESUMO",
        "INSCRICAO", "EMPRESA", "VALOR",
        "TOPOGRAFIA", "AUXILIAR", "DEDUCAO",
        "FPAS", "RUA", "JD", "BAIRRO",
        "JARDIM", "ANALITICO", "ANALÍTICO", "CONTRATO",
        "CONTRATOS", "NORMAIS", "DIURNAS", "ENCANADOR",
        "DEPENDENTE", "DEPENDENTES", "TIPO", "CALCULO",
        "CÁLCULO", "DEBITO", "DÉBITO", "APURADO",
        "RETENCAO", "RETENÇÃO", "SALDO", "PAGAR",
        "CHECK", "PERÍODO", "PERIODO"
    ]

    if any(p in nome for p in proibidas):
        return False

    if any(p in nome_sem_espaco for p in proibidas):
        return False

    # apenas letras
    if not re.match(r"^[A-ZÁÉÍÓÚÃÕÇ ]+$", nome):
        return False

    return True


# ============================================================
# 🔹 EXTRAIR COLABORADORES (OCR)
# ============================================================
def extrair_colaboradores(texto, empresa=None):
    linhas = texto.split("\n")
    nomes = []

    for i, linha in enumerate(linhas):
        linha = linha.strip().upper()
        match = re.match(r"^\d{3,6}\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{5,})$", linha)
        if not match:
            continue

        janela = "\n".join(linhas[i + 1:i + 8]).upper()
        if "EMPR" not in janela or "CPF" not in janela:
            continue

        nome = match.group(1).strip()
        if nome_valido(nome, empresa):
            nomes.append(nome)

    if nomes:
        return nomes

    for linha in linhas:
        linha = linha.strip().upper()

        if nome_valido(linha, empresa):
            nomes.append(linha)

    return nomes


# ============================================================
# 🚀 SERVICE PRINCIPAL
# ============================================================
def processar_folha_pagamento(caminho_arquivo, competencia_esperada=None):

    print("\n🚀 ===== PROCESSANDO FOLHA =====")

    # ======================================================
    # 1. OCR
    # ======================================================
    texto = extrair_texto_folha(caminho_arquivo)

    if not texto or len(texto.strip()) < 50:
        return {
            "status": "Erro",
            "mensagem": "Falha no OCR",
            "empresa": None,
            "competencia": None,
            "competencia_ok": False,
            "colaboradores": [],
            "erros": ["OCR vazio"],
            "avisos": []
        }

    # ======================================================
    # 2. EXTRAÇÃO BASE
    # ======================================================
    competencia_doc = extrair_competencia(texto)
    empresa_ocr = extrair_empresa(texto)

    print("📅 Competência:", competencia_doc)
    print("🏢 Empresa:", empresa_ocr)

    # ======================================================
    # 3. GEMINI
    # ======================================================
    try:
        dados_ia = extrair_folha_inteligente(texto)
        if not isinstance(dados_ia, dict):
            dados_ia = {}
    except Exception as e:
        print("❌ Erro IA:", e)
        dados_ia = {}

    colaboradores_ia = dados_ia.get("colaboradores") or []

    # ======================================================
    # 4. BASE (IA OU OCR)
    # ======================================================
    base = colaboradores_ia if colaboradores_ia else extrair_colaboradores(texto, empresa_ocr)

    # ======================================================
    # 5. NORMALIZAÇÃO FINAL
    # ======================================================
    nomes_vistos = set()
    lista_final = []

    for c in base:

        nome = c.get("nome") if isinstance(c, dict) else str(c)
        nome = (nome or "").strip().upper()

        if not nome_valido(nome, empresa_ocr):
            continue

        if nome not in nomes_vistos:
            nomes_vistos.add(nome)
            lista_final.append({"nome": nome})

    print("👥 FINAL:", lista_final)

    # ======================================================
    # 6. COMPETÊNCIA FINAL
    # ======================================================
    competencia_final = competencia_doc or dados_ia.get("competencia")

    competencia_ok = True
    if competencia_esperada and competencia_final:
        competencia_ok = competencia_final == competencia_esperada

    # ======================================================
    # 7. RULES
    # ======================================================
    resultado_rules = validar_folha(dados_ia, competencia_esperada)

    # ======================================================
    # 8. STATUS FINAL
    # ======================================================
    if resultado_rules.get("status") == "Reprovado":
        status = "Reprovado"
        mensagem = "Folha com inconsistências"

    elif resultado_rules.get("status") == "Parcial":
        status = "Parcial"
        mensagem = "Folha com pendências"

    else:
        status = "Aprovado"
        mensagem = f"{len(lista_final)} colaborador(es)"

    # ======================================================
    # 9. RETORNO FINAL
    # ======================================================
    empresa_final = dados_ia.get("empresa") or empresa_ocr
    if empresa_final and len(str(empresa_final).split()) < 2:
        empresa_final = empresa_ocr

    return {
        "status": status,
        "mensagem": mensagem,
        "empresa": empresa_final,
        "competencia": competencia_final,
        "competencia_ok": competencia_ok,
        "colaboradores": lista_final,
        "erros": resultado_rules.get("erros", []),
        "avisos": resultado_rules.get("avisos", [])
    }
