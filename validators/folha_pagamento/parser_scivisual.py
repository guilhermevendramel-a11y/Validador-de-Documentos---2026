import re
import unicodedata

from validators.folha_pagamento.regras import nome_valido


BLOCKLIST_EMPRESA = {
    "RESUMO",
    "FOLHA",
    "PAGAMENTO",
    "FOLHA ANALITICA",
    "ANALITICA",
    "PRATICE",
    "PRACTICE",
    "SCI",
    "VISUAL",
    "TOTAL",
    "FUNCIONARIO",
    "FUNCIONARIOS",
    "SOCIOS",
    "AUTONOMOS",
    "SALARIO",
    "BASE",
    "VENCIMENTOS",
    "DESCONTOS",
    "LIQUIDO",
}

BLOCKLIST_COLABORADOR = {
    "RESUMO",
    "FOLHA",
    "PAGAMENTO",
    "RAZAO SOCIAL",
    "RAZAO SOCIAL:",
    "EMPRESA",
    "EMPRESA:",
    "LOCAL",
    "CENTRO DE CUSTO",
    "CNPJ",
    "CNPJ/CEI",
    "INSCRICAO",
    "PERIODO",
    "ADMISSAO",
    "SITUACAO",
    "ATIVO",
    "INATIVO",
    "FUNCIONARIO",
    "FUNCIONÁRIOS",
    "FUNCAO",
    "FUNÇÃO",
    "SALARIO",
    "BASE",
    "VENCIMENTOS",
    "DESCONTOS",
    "LIQUIDO",
    "TOTAL",
    "TOTAIS",
    "GERAL",
    "LICENCIADO",
    "SISTEMA",
    "SCI",
    "VISUAL",
    "PRACTICE",
    "PRATICE",
    "RESUMO POR FUNCIONARIOS",
    "RESUMO POR FUNCIONÁRIOS",
    "RESUMO POR FUNCIONARIOS, SOCIOS E AUTONOMOS DO MES",
    "RESUMO POR FUNCIONÁRIOS, SÓCIOS E AUTÔNOMOS DO MÊS",
}


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _norm(texto):
    texto = _sem_acento(texto).upper()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _linhas(texto):
    return [re.sub(r"\s+", " ", str(linha or "")).strip() for linha in str(texto or "").splitlines() if str(linha or "").strip()]


def eh_layout_scivisual(texto: str) -> bool:
    texto_norm = _norm(texto)
    if "SCI VISUAL PRACTICE" in texto_norm:
        return True
    if "FOLHA ANALITICA" in texto_norm:
        return True
    if "RESUMO POR FUNCIONARIOS" in texto_norm or "RESUMO POR FUNCIONÁRIOS" in texto_norm:
        return True
    if "EMP-FIL:" in texto_norm or "RAZAO SOCIAL:" in texto_norm or "RAZAO SOCIAL:" in texto_norm:
        return True
    if "CÓD. NOME DO FUNCIONÁRIO" in texto_norm or "COD. NOME DO FUNCIONARIO" in texto_norm:
        return True
    return False


def _parece_empresa(candidato):
    candidato = re.sub(r"^\s*\d+(?:[-./]\d+)?\s*[-–—]\s*", "", str(candidato or "").strip())
    candidato = re.sub(r"\s{2,}", " ", candidato).strip(" -:|")
    if len(candidato) < 4 or re.search(r"\d", candidato):
        return False
    norm = _norm(candidato)
    if any(b in norm for b in BLOCKLIST_EMPRESA):
        return False
    if any(suf in norm for suf in (" LTDA", " LIMITADA", " EIRELI", " EPP", " ME ", " S A", " S.A")):
        return True
    if len(norm.split()) >= 2:
        return True
    return False


def _limpar_nome(candidato):
    candidato = re.sub(r"^\s*\d+(?:[-./]\d+)?\s*[-.:|)]*\s*", "", str(candidato or "").strip())
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    candidato = re.sub(
        r"\b(ADMISS[AÃ]O|SITUA[CÇ][AÃ]O|CARGO|FUN[CÇ][AÃ]O|SAL[AÃ]RIO|DEP\.?\s*IR|DEP\.?\s*SF|COD\.?|C[ÓO]D\.?|EMP-FIL|CNPJ|CPF|ATIVO|INATIVO|PROVENTOS|DESCONTOS|L[IÍ]QUIDO|BASE|TOTAL|RESUMO)\b.*$",
        "",
        candidato,
        flags=re.I,
    ).strip(" -:|")
    candidato = re.sub(r"(?<=\d)(?=[A-ZÀ-Ü])", " ", candidato)
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    return candidato


def extrair_empresa_scivisual(texto: str) -> str | None:
    linhas = _linhas(texto)

    for i, linha in enumerate(linhas[:25]):
        lu = _norm(linha)
        if any(rot in lu for rot in ("RAZAO SOCIAL", "RAZAO SOCIAL", "EMPRESA", "EMP-FIL")):
            candidatos = []
            if ":" in linha:
                candidatos.append(linha.split(":", 1)[1].strip())
            elif "-" in linha:
                candidatos.append(linha.split("-", 1)[1].strip())
            else:
                candidatos.append(linha)
            candidatos.extend(linhas[i + 1:i + 4])
            for cand in candidatos:
                cand = _limpar_nome(cand)
                cand = re.sub(r"^\s*\d+(?:-\d+)?\s*", "", cand)
                cand = re.sub(r"\s*\(\s*\d[\d./-]*\s*\)\s*$", "", cand).strip()
                cand = re.sub(r"\bCNPJ.*$", "", cand, flags=re.I).strip()
                if _parece_empresa(cand):
                    return cand

    for linha in linhas[:20]:
        cand = _limpar_nome(linha)
        cand = re.sub(r"^\s*\d+(?:-\d+)?\s*", "", cand)
        cand = re.sub(r"\s*\(\s*\d[\d./-]*\s*\)\s*$", "", cand).strip()
        if _parece_empresa(cand):
            return cand

    for linha in linhas[:30]:
        if "LTDA" in _norm(linha) or "LIMITADA" in _norm(linha) or "EIRELI" in _norm(linha):
            cand = _limpar_nome(linha)
            if _parece_empresa(cand):
                return cand
    return None


def extrair_competencia_scivisual(texto: str) -> str | None:
    linhas = _linhas(texto)
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
    for linha in linhas[:20]:
        lu = _norm(linha)
        m = re.search(r"PER[IÍ]ODO DE:\s*(\d{2})/(\d{2})/(\d{4})\s+A\s+(\d{2})/(\d{2})/(\d{4})", lu)
        if m and m.group(3) == m.group(6):
            return f"{m.group(2)}/{m.group(3)}"
        m = re.fullmatch(r"(0[1-9]|1[0-2])/(20\d{2})", lu)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        m = re.search(r"\b([A-Z]+)\s*/\s*(20\d{2})\b", lu)
        if m and m.group(1) in meses:
            return f"{meses[m.group(1)]}/{m.group(2)}"
        m = re.search(r"\b([A-Z]+)\s+DE\s+(20\d{2})\b", lu)
        if m and m.group(1) in meses:
            return f"{meses[m.group(1)]}/{m.group(2)}"
    return None


def _eh_linha_cabecalho_ou_resumo(linha_norm):
    return any(
        b in linha_norm
        for b in (
            "RESUMO",
            "TOTAIS",
            "TOTAL",
            "SALARIO BASE",
            "VENCIMENTOS",
            "DESCONTOS",
            "BASE INSS",
            "BASE FGTS",
            "BASE IRRF",
            "SITUACOES",
            "SITUACAOES",
            "FUNCIONARIO",
            "FUNCIONÁRIOS",
            "CÓD. NOME DO FUNCIONÁRIO",
            "COD. NOME DO FUNCIONARIO",
            "RAZAO SOCIAL",
            "RAZAO SOCIAL",
            "CENTRO DE CUSTOS",
            "EMPRESA",
            "EMP-FIL",
            "SCI VISUAL PRACTICE",
        )
    )


def _extrair_candidatos_por_linhas(linhas, empresa=None):
    nomes = []

    def adicionar(nome):
        nome = _limpar_nome(nome)
        if not nome:
            return
        if empresa and _norm(nome) == _norm(empresa):
            return
        if nome_valido(nome, empresa=empresa):
            titulo = re.sub(r"\s+", " ", nome).strip().title()
            if all(_norm(c) != _norm(titulo) for c in nomes):
                nomes.append(titulo)

    for idx, linha in enumerate(linhas):
        lu = _norm(linha)
        if not lu:
            continue

        # nome em bloco tipo "Funcionario 177821 MARCELO MOLINARI Salario Mes ..."
        m = re.search(r"\bFUNCIONARIO\s+\d+\s+(.+?)(?=\s+SALARIO|\s+CPF|\s+FUNC[AÃ]O|\s+ADMIS|$)", lu)
        if m:
            adicionar(m.group(1))
            continue

        if _eh_linha_cabecalho_ou_resumo(lu):
            continue

        # nome em linhas tipo "1219 ANDERSON RODRIGUES SILVA"
        if re.match(r"^\d{3,7}\s+[A-ZÀ-Ü]", linha):
            cand = re.sub(r"^\s*\d+\s+", "", linha).strip()
            cand = re.sub(r"(?<=\d)(?=[A-ZÀ-Ü])", " ", cand)
            cand = _limpar_nome(cand)
            janela = " ".join(linhas[idx + 1:idx + 6])
            if any(tok in _norm(janela) for tok in ("EMPR.", "EMPR:", "ADM", "CARGO", "SITUA")):
                adicionar(cand)
                continue

        # nomes em linhas soltas de tabelas/resumos
        cand = _limpar_nome(linha)
        if len(cand.split()) >= 2 and len(cand.split()) <= 6:
            if any(ch.isdigit() for ch in cand):
                cand = re.sub(r"(?<=\d)(?=[A-ZÀ-Ü])", " ", cand)
                cand = _limpar_nome(cand)
            if _eh_linha_cabecalho_ou_resumo(_norm(cand)):
                continue
            if nome_valido(cand, empresa=empresa):
                adicionar(cand)

    return [{"nome": n} for n in nomes]


def extrair_dados_scivisual(texto: str) -> dict:
    if not eh_layout_scivisual(texto):
        return {}

    linhas = _linhas(texto)
    empresa = extrair_empresa_scivisual(texto)
    competencia = extrair_competencia_scivisual(texto)
    colaboradores = _extrair_candidatos_por_linhas(linhas, empresa=empresa)

    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": colaboradores,
        "layout": "scivisual",
    }
