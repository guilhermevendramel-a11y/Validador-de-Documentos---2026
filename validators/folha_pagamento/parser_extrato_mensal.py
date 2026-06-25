import re
import unicodedata

from validators.folha_pagamento.regras import nome_valido


FIM_LAYOUT = (
    "RESUMO POR RUBRICAS DO SERVICO",
    "TOTAIS POR CENTRO DE CUSTOS",
    "APURACAO TRIBUTOS FEDERAIS",
    "APURACAO TRIBUTOS",
    "SALDO A COMPENSAR",
    "SALDO A RECOLHER",
    "SALDO REMANESCENTE",
)

IGNORAR_LINHAS = (
    "SISTEMA LICENCIADO",
    "USUARIO:",
    "USUÁRIO:",
    "ASSINATURA",
    "DATA DE PAGAMENTO",
    "DATA DE PAGAMENTO :",
    "RELACAO DE CALCULO",
    "RELACAO DE CÁLCULO",
    "EXTRATO MENSAL",
    "EMPRESA:",
    "COMPETENCIA:",
    "CÁLCULO:",
    "CALCULO:",
    "FOLHA MENSAL",
    "RESUMO CONTRATO",
    "RESUMO FGTS DIGITAL",
    "TOTAL EMPRESA",
    "TOTAL GERAL",
    "TOTAL:",
)


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _norm(texto):
    texto = _sem_acento(texto).upper()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _linhas(texto):
    return [re.sub(r"\s+", " ", str(linha or "")).strip() for linha in str(texto or "").splitlines() if str(linha or "").strip()]


def eh_layout_extrato_mensal(texto: str) -> bool:
    texto_norm = _norm(texto)
    if "EXTRATO MENSAL" not in texto_norm:
        return False
    return "MATR. E-SOCIAL" in texto_norm or "MATR. ESOCIAL" in texto_norm or "FUNC:" in texto_norm


def _parece_empresa(candidato: str) -> bool:
    candidato = re.sub(r"^\s*\d+\s*[-–—]\s*", "", str(candidato or "").strip())
    candidato = re.sub(r"\s{2,}", " ", candidato).strip(" -:|")
    if len(candidato) < 4 or re.search(r"\d", candidato):
        return False
    norm = _norm(candidato)
    if any(b in norm for b in FIM_LAYOUT):
        return False
    if any(ign in norm for ign in ("SISTEMA LICENCIADO", "RESUMO", "TOTAL", "EXTRATO MENSAL")):
        return False
    palavras = norm.split()
    if len(palavras) < 2:
        return False
    if not any(suf in norm for suf in (" LTDA", " LIMITADA", " EIRELI", " EPP", " ME ", " CONSTRUCOES", " LOCACOES")):
        return len(palavras) >= 2
    return True


def extrair_empresa_extrato_mensal(texto: str) -> str | None:
    linhas = _linhas(texto)
    for linha in linhas[:25]:
        lu = _norm(linha)
        if "SISTEMA LICENCIADO" in lu:
            continue
        m = re.match(r"^\d+\s*-\s*(.+)$", linha)
        if m:
            candidato = m.group(1).strip()
            if _parece_empresa(candidato):
                return candidato
    for linha in linhas[:25]:
        if any(rot in _norm(linha) for rot in ("EMPRESA", "RAZAO SOCIAL", "ESTABELECIMENTO")):
            partes = [linha]
            if ":" in linha:
                partes.insert(0, linha.split(":", 1)[1].strip())
            for cand in partes:
                if _parece_empresa(cand):
                    return re.sub(r"^\s*\d+\s*-\s*", "", cand).strip()
    return None


def extrair_competencia_extrato_mensal(texto: str) -> str | None:
    linhas = _linhas(texto)
    for linha in linhas[:15]:
        lu = _norm(linha)
        m = re.fullmatch(r"(0[1-9]|1[0-2])/(20\d{2})", lu)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        m = re.search(r"\b(0[1-9]|1[0-2])/(20\d{2})\b", lu)
        if m and not re.search(r"\b\d{2}/\d{2}/20\d{2}\b", lu):
            if not any(rot in lu for rot in ("EMISSAO", "HORAS", "PAGINA")):
                return f"{m.group(1)}/{m.group(2)}"
        m = re.search(r"\b([A-Z]+)\s*/\s*(20\d{2})\b", lu)
        if m:
            meses = {
                "JANEIRO": "01",
                "FEVEREIRO": "02",
                "MARCO": "03",
                "MARÇO": "03",
                "ABRIL": "04",
                "MAIO": "05",
                "JUNHO": "06",
                "JULHO": "07",
                "AGOSTO": "08",
                "SETEMBRO": "09",
                "OUTUBRO": "10",
                "NOVEMBRO": "11",
                "DEZEMBRO": "12",
            }
            mes = meses.get(m.group(1))
            if mes:
                return f"{mes}/{m.group(2)}"
        m = re.search(r"\b([A-Z]+)\s+DE\s+(20\d{2})\b", lu)
        if m:
            meses = {
                "JANEIRO": "01",
                "FEVEREIRO": "02",
                "MARCO": "03",
                "MARÇO": "03",
                "ABRIL": "04",
                "MAIO": "05",
                "JUNHO": "06",
                "JULHO": "07",
                "AGOSTO": "08",
                "SETEMBRO": "09",
                "OUTUBRO": "10",
                "NOVEMBRO": "11",
                "DEZEMBRO": "12",
            }
            mes = meses.get(m.group(1))
            if mes:
                return f"{mes}/{m.group(2)}"
    return None


def _linha_nome_valida(linha: str, empresa: str | None = None) -> bool:
    lu = _norm(linha)
    if not re.match(r"^\d{3,7}\s+[A-ZÀ-Ü]", linha, flags=re.I):
        return False
    if any(ign in lu for ign in IGNORAR_LINHAS):
        return False
    if any(fim in lu for fim in FIM_LAYOUT):
        return False
    if "SISTEMA LICENCIADO" in lu:
        return False
    candidato = re.sub(r"^\s*\d+\s+", "", linha).strip()
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    if not candidato:
        return False
    if empresa and _norm(candidato) == _norm(empresa):
        return False
    return nome_valido(candidato, empresa=empresa)


def extrair_colaboradores_extrato_mensal(texto: str, empresa: str | None = None) -> list[dict]:
    linhas = _linhas(texto)
    colaboradores = []
    bloquear = False

    for idx, linha in enumerate(linhas):
        lu = _norm(linha)

        if any(fim in lu for fim in FIM_LAYOUT):
            bloquear = True
            continue

        if bloquear:
            continue

        if any(ign in lu for ign in IGNORAR_LINHAS):
            continue

        if _linha_nome_valida(linha, empresa=empresa):
            candidato = re.sub(r"^\s*\d+\s+", "", linha).strip()
            candidato = re.sub(r"\s{2,}", " ", candidato).strip()

            janela = linhas[idx + 1: idx + 7]
            tem_ancora = any(
                re.match(r"^(EMPR|ADM|CPF|SITUACAO|CARGO|FILIAL|C\.B\.O|CBO|DEPTO|CC)\b", _norm(prox))
                for prox in janela
            )
            if not tem_ancora:
                continue

            nome = re.sub(r"\s+", " ", candidato).strip().title()
            if all(_norm(c["nome"]) != _norm(nome) for c in colaboradores):
                colaboradores.append({"nome": nome})

    return colaboradores


def extrair_dados_extrato_mensal(texto: str) -> dict:
    if not eh_layout_extrato_mensal(texto):
        return {}

    empresa = extrair_empresa_extrato_mensal(texto)
    competencia = extrair_competencia_extrato_mensal(texto)
    colaboradores = extrair_colaboradores_extrato_mensal(texto, empresa=empresa)

    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": colaboradores,
        "layout": "extrato_mensal",
    }
