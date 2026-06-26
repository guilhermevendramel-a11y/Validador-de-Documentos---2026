import re
import unicodedata

from validators.folha_pagamento.regras import nome_valido


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _norm(texto):
    texto = _sem_acento(texto).upper()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _linhas(texto):
    return [re.sub(r"\s+", " ", str(linha or "")).strip() for linha in str(texto or "").splitlines() if str(linha or "").strip()]


def eh_layout_folha_femav(texto: str) -> bool:
    texto_norm = _norm(texto)
    return "FEMAV" in texto_norm and "N.REG" in texto_norm and "CPF" in texto_norm and "CBO" in texto_norm


def extrair_empresa_folha_femav(texto: str) -> str | None:
    linhas = _linhas(texto)
    for i, linha in enumerate(linhas[:12]):
        lu = _norm(linha)
        if lu == "EMPRESA:" and i + 1 < len(linhas):
            cand = re.sub(r"^\s*\d+\s*-\s*", "", linhas[i + 1]).strip()
            return cand
        if "EMPRESA:" in lu:
            cand = linha.split(":", 1)[1].strip()
            cand = re.sub(r"^\s*\d+\s*-\s*", "", cand).strip()
            if cand:
                return cand
    return None


def extrair_competencia_folha_femav(texto: str) -> str | None:
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
    m = re.search(r"COMPET[ÊE]NCIA:\s*([A-Z]+)/(\d{4})", texto_norm)
    if m:
        mes = meses.get(m.group(1), m.group(1))
        return f"{mes}/{m.group(2)}"
    m = re.search(r"COMPET[ÊE]NCIA:\s*(0[1-9]|1[0-2])/(\d{4})", texto_norm)
    if m:
        return f"{m.group(1)}/{m.group('y')}"
    m = re.search(r"\b([A-Z?-?]+)/(20\d{2})\b", texto_norm)
    if m and m.group(1) in meses:
        return f"{meses[m.group(1)]}/{m.group(2)}"
    return None


def _limpar_nome(candidato):
    candidato = str(candidato or "").strip()
    candidato = re.sub(r"^\s*[0O0-9.]{1,14}\s*", "", candidato)
    candidato = re.sub(r"\b(?:CBO|FUNCAO|FUNÇÃO|SALARIO|SALÁRIO|CONDIÇÃO|CONDIÇÃO|MENSAL|TIPO SALARIO|TIPO SALÁRIO|ADMISSAO|ADMISSÃO|BASE|LIQUIDO|LÍQUIDO)\b.*$", "", candidato, flags=re.I).strip(" -:|")
    candidato = re.split(r"\s+\d{6}\s+-", candidato, maxsplit=1)[0].strip()
    candidato = re.split(r"\s+(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\b", candidato, maxsplit=1)[0].strip()
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    return candidato


def extrair_colaboradores_folha_femav(texto: str, empresa: str | None = None) -> list[dict]:
    linhas = _linhas(texto)
    nomes = []

    def adicionar(candidato):
        candidato = _limpar_nome(candidato)
        if not candidato or len(candidato.split()) < 2:
            return
        if empresa and _norm(candidato) == _norm(empresa):
            return
        if nome_valido(candidato, empresa=empresa):
            titulo = re.sub(r"\s+", " ", candidato).strip().title()
            if all(_norm(n) != _norm(titulo) for n in nomes):
                nomes.append(titulo)

    for linha in linhas:
        lu = _norm(linha)
        if not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", linha):
            continue
        m = re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}\s+([A-ZÀ-Ü .'-]{3,}?)(?=\s+\d{6}\s+-|\s+\d{6}\b|\s+CBO\b)", linha, flags=re.I)
        if m:
            adicionar(m.group(1))

    return [{"nome": nome} for nome in nomes]


def extrair_dados_folha_femav(texto: str) -> dict:
    if not eh_layout_folha_femav(texto):
        return {}

    empresa = extrair_empresa_folha_femav(texto)
    competencia = extrair_competencia_folha_femav(texto)
    colaboradores = extrair_colaboradores_folha_femav(texto, empresa=empresa)

    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": colaboradores,
        "layout": "folha_femav",
    }
