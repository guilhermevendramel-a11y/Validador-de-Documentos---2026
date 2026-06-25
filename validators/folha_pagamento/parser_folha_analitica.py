import re
import unicodedata

from validators.folha_pagamento.regras import nome_valido


STOPWORDS_EMPRESA = {
    "FOLHA",
    "PAGAMENTO",
    "ANALITICA",
    "ANALÍTICA",
    "RESUMO",
    "LIQUIDO",
    "LÍQUIDO",
    "SALARIO",
    "SALÁRIO",
    "TOTAL",
    "BASE",
    "INSS",
    "FGTS",
    "IRRF",
    "FUNCAO",
    "FUNÇÃO",
    "ADMISSAO",
    "ADMISSÃO",
    "DEPIR",
    "DEP SF",
    "PAGINA",
    "PÁGINA",
    "DPTO",
    "DEPARTAMENTO",
    "END",
    "END.",
    "CNPJ",
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


def eh_layout_folha_analitica(texto: str) -> bool:
    texto_norm = _norm(texto)
    if "FOLHA DE PAGAMENTO ANALITICA" in texto_norm or "FOLHA DE PAGAMENTO ANALÍTICA" in texto_norm:
        return True
    if "RESUMO DO LIQUIDO" in texto_norm and "FUNCAO" in texto_norm:
        return True
    if "ADMISSAO :" in texto_norm and "RESUMO DO LIQUIDO" in texto_norm and "EMPRESA :" in texto_norm:
        return True
    return False


def _limpar_empresa(candidato):
    candidato = str(candidato or "").strip()
    candidato = re.sub(r"^\s*\d+\s*[-??]?\s*", "", candidato)
    candidato = re.sub(r"\s*\(\s*\d[\d./-]*\s*\)\s*$", "", candidato).strip()
    candidato = re.sub(r"\s{2,}", " ", candidato).strip(" -:|")
    m = re.search(r"(.+?\b(?:LTDA|LIMITADA|EIRELI|EPP|ME|S\.A|SA)\b)", candidato, flags=re.I)
    if m:
        candidato = m.group(1).strip()
    candidato = re.sub(r"\bCNPJ\b.*$", "", candidato, flags=re.I).strip(" -:|")
    candidato = re.sub(r"\bEND\.?\b.*$", "", candidato, flags=re.I).strip(" -:|")
    candidato = re.sub(r"\bPAG(?:INA|\.|.?GINA|\.?GINA|INA)\b.*$", "", candidato, flags=re.I).strip(" -:|")
    candidato = re.sub(r"\s+\(\s*\d+\s*\)\s*$", "", candidato).strip(" -:|")
    candidato = re.sub(r"\s{2,}", " ", candidato).strip(" -:|")
    return candidato


def extrair_empresa_folha_analitica(texto: str) -> str | None:
    linhas = _linhas(texto)

    for i, linha in enumerate(linhas[:20]):
        lu = _norm(linha)
        if "EMPRESA" not in lu:
            continue
        candidatos = []
        if ":" in linha:
            candidatos.append(linha.split(":", 1)[1].strip())
        if "-" in linha:
            candidatos.append(linha.split("-", 1)[1].strip())
        candidatos.append(linha)
        candidatos.extend(linhas[i + 1:i + 3])
        for cand in candidatos:
            cand = _limpar_empresa(cand)
            cand_norm = _norm(cand)
            if not cand or len(cand) < 4:
                continue
            if re.search(r"\d", cand) and not any(suf in cand_norm for suf in (" LTDA", " EIRELI", " EPP", " ME ", " LIMITADA")):
                continue
            if any(stop in cand_norm for stop in STOPWORDS_EMPRESA):
                continue
            if any(suf in cand_norm for suf in (" LTDA", " LIMITADA", " EIRELI", " EPP", " ME ", " S A", " S.A")):
                return cand
            if len(cand.split()) >= 2 and not re.search(r"\b\w+/\w+\b", cand):
                return cand

    for linha in linhas[:20]:
        cand = _limpar_empresa(linha)
        cand_norm = _norm(cand)
        if any(stop in cand_norm for stop in STOPWORDS_EMPRESA):
            continue
        if any(suf in cand_norm for suf in (" LTDA", " LIMITADA", " EIRELI", " EPP", " ME ", " S A", " S.A")):
            return cand

    return None


def extrair_competencia_folha_analitica(texto: str) -> str | None:
    texto_norm = _norm(texto)
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

    m = re.search(r"\bREF\.?:?\s*(\d{2})/(\d{2})/(\d{4})\s+A\s+(\d{2})/(\d{2})/(\d{4})", texto_norm)
    if m and m.group(3) == m.group(6):
        return f"{m.group(2)}/{m.group(3)}"

    m = re.search(r"\b([A-Z]+)\s+DE\s+(20\d{2})\b", texto_norm)
    if m and m.group(1) in meses:
        return f"{meses[m.group(1)]}/{m.group(2)}"

    m = re.search(r"\b(0[1-9]|1[0-2])/(20\d{2})\b", texto_norm)
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    m = re.search(r"\b([A-Z]+)/(20\d{2})\b", texto_norm)
    if m and m.group(1) in meses:
        return f"{meses[m.group(1)]}/{m.group(2)}"

    return None


def _limpar_nome(candidato):
    candidato = str(candidato or "").strip()
    candidato = re.sub(r"^\s*[0O0-9]{1,7}\s+", "", candidato)
    candidato = re.sub(r"\s+(?:O|0|1|2)\s*$", "", candidato, flags=re.I).strip()
    candidato = re.sub(
        r"\b(?:FUNCAO|FUNÇÃO|ADMISSAO|ADMISSÃO|DEPIR|DEPSF|DEP\.?\s*IR|DEP\.?\s*SF|LIVRO|FOLHA|BASE|TOTAL|RESUMO|LIQUIDO|LÍQUIDO|INSS|FGTS|IRRF)\b.*$",
        "",
        candidato,
        flags=re.I,
    ).strip(" -:|")
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    return candidato


def extrair_colaboradores_folha_analitica(texto: str, empresa: str | None = None) -> list[dict]:
    linhas = _linhas(texto)
    nomes = []

    def adicionar(candidato):
        candidato = _limpar_nome(candidato)
        if not candidato:
            return
        if len(candidato.split()) < 2:
            return
        if empresa and _norm(candidato) == _norm(empresa):
            return
        if nome_valido(candidato, empresa=empresa):
            titulo = re.sub(r"\s+", " ", candidato).strip().title()
            if all(_norm(n) != _norm(titulo) for n in nomes):
                nomes.append(titulo)

    for linha in linhas:
        lu = _norm(linha)
        if not lu:
            continue
        if "EMPRESA" in lu or "FOLHA DE PAGAMENTO ANALITICA" in lu:
            continue
        if any(rot in lu for rot in ("RESUMO DO LIQUIDO", "TOTAL LIQUIDO", "BASE INSS", "BASE FGTS", "BASE IRRF")):
            continue
        if not re.match(r"^[0O0-9]{1,7}\s+[A-Z?-?]", linha):
            continue
        if not any(anchor in lu for anchor in ("FUN", "LIVRO", "ADMISS", "DEPIR", "DEPSF")):
            continue

        candidato = re.sub(r"^\s*[0O0-9]{1,7}\s+", "", linha).strip()
        candidato = re.split(r"\s+(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\b", candidato, maxsplit=1)[0].strip()
        adicionar(candidato)

    return [{"nome": nome} for nome in nomes]


def extrair_dados_folha_analitica(texto: str) -> dict:
    if not eh_layout_folha_analitica(texto):
        return {}

    empresa = extrair_empresa_folha_analitica(texto)
    competencia = extrair_competencia_folha_analitica(texto)
    colaboradores = extrair_colaboradores_folha_analitica(texto, empresa=empresa)

    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": colaboradores,
        "layout": "folha_analitica",
    }
