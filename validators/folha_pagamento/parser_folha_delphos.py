import re
import unicodedata

from validators.folha_pagamento.regras import nome_valido


BLOCKLIST = {
    "GFIP",
    "VAL",
    "DEV",
    "REND",
    "RAIS",
    "BAS",
    "BASE",
    "TOTAL",
    "SALARIO",
    "LIQUIDO",
    "INSS",
    "FGTS",
    "TOTAIS",
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


def eh_layout_folha_delphos(texto: str) -> bool:
    texto_norm = _norm(texto)
    return "DELPHOS" in texto_norm and "REGISTRO" in texto_norm and "CARGO" in texto_norm and "CPF" in texto_norm


def extrair_empresa_folha_delphos(texto: str) -> str | None:
    linhas = _linhas(texto)
    for linha in linhas[:12]:
        lu = _norm(linha)
        if "DELPHOS" in lu and "LTDA" in lu:
            cand = re.sub(r"^\s*\d+\s*", "", linha).strip()
            cand = re.sub(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b.*$", "", cand, flags=re.I).strip(" -:|")
            if cand:
                return cand
    return None


def extrair_competencia_folha_delphos(texto: str) -> str | None:
    texto_norm = _norm(texto)
    m = re.search(r"\b(0[1-9]|1[0-2])/(20\d{2})\b", texto_norm)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def _limpar_nome(candidato):
    candidato = str(candidato or "").strip()
    candidato = re.sub(r"^\s*\d{3,6}-?\d*\s+", "", candidato)
    candidato = re.split(r"\s+\d{3}\.\d{3}\.\d{3}-\d{2}\b", candidato, maxsplit=1)[0].strip()
    partes = [p for p in candidato.split() if p]
    if len(partes) >= 3:
        candidato = " ".join(partes[:-1])
    candidato = re.sub(
        r"\b(VIGIA|MOTORISTA|CARGO|CPF|CCUSTO|SALARIO|SALARIO|GRUPO|ADMISSAO|ADMISSAO|DEPIR|DEPSF|VENCIMENTOS|DESCONTOS|TOTAL|LIQUIDO)\b.*$",
        "",
        candidato,
        flags=re.I,
    ).strip(" -:|")
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    return candidato


def extrair_colaboradores_folha_delphos(texto: str, empresa: str | None = None) -> list[dict]:
    linhas = _linhas(texto)
    nomes = []

    def adicionar(candidato):
        candidato = _limpar_nome(candidato)
        if not candidato or len(candidato.split()) < 2:
            return
        if empresa and _norm(candidato) == _norm(empresa):
            return
        if any(token in BLOCKLIST for token in _norm(candidato).replace(".", " ").split()):
            return
        if nome_valido(candidato, empresa=empresa):
            titulo = re.sub(r"\s+", " ", candidato).strip().title()
            if all(_norm(n) != _norm(titulo) for n in nomes):
                nomes.append(titulo)

    for linha in linhas:
        if not re.match(r"^\d{3,6}-?\d*\s+[A-ZÀ-Ü]", linha):
            continue
        if "DELPHOS" in _norm(linha):
            continue
        candidato = re.sub(r"^\s*\d{3,6}-?\d*\s+", "", linha).strip()
        candidato = re.split(r"\s+\d{3}\.\d{3}\.\d{3}-\d{2}\b", candidato, maxsplit=1)[0].strip()
        adicionar(candidato)

    return [{"nome": nome} for nome in nomes]


def extrair_dados_folha_delphos(texto: str) -> dict:
    if not eh_layout_folha_delphos(texto):
        return {}

    empresa = extrair_empresa_folha_delphos(texto)
    competencia = extrair_competencia_folha_delphos(texto)
    colaboradores = extrair_colaboradores_folha_delphos(texto, empresa=empresa)

    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": colaboradores,
        "layout": "folha_delphos",
    }
