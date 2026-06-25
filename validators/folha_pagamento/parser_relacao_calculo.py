import re
import unicodedata

from validators.folha_pagamento.regras import nome_valido


BLOCKLIST_EMPRESA = {
    "EXTRATO",
    "MENSAL",
    "RELACAO",
    "CALCULO",
    "PERIODO",
    "RESUMO",
    "CONTRATO",
    "CONTRATOS",
    "ANALITICO",
    "TOTAL",
    "HORAS",
    "SEMANAIS",
    "FGTS",
    "PIS",
    "INSS",
    "IRRF",
    "SALDO",
    "FUNCAO",
    "FUNC",
    "FUNC: ",
}

BLOCKLIST_COLABORADOR = {
    "ADM",
    "CARGO",
    "SITUACAO",
    "TRABALHANDO",
    "DEMITIDO",
    "CONTRATO",
    "CONTRATOS",
    "ANALITICO",
    "RESUMO",
    "HORAS",
    "SEMANAIS",
    "PROVENTOS",
    "DESCONTOS",
    "LIQUIDO",
    "BASE",
    "PIS",
    "FGTS",
    "INSS",
    "IRRF",
    "DIRETORES",
    "AUTONOMOS",
    "TRIBUTOS",
    "COOPERATIVAS",
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


def eh_layout_relacao_calculo(texto: str) -> bool:
    texto_norm = _norm(texto)
    if "RELACAO DE CALCULO" not in texto_norm:
        return False
    if "FUNC:" not in texto_norm and "TOTAL EMPRESA" not in texto_norm:
        return False
    return any(rot in texto_norm for rot in ("ANALITICO CONTRATOS", "RESUMO CONTRATO", "RESUMO FGTS DIGITAL"))


def _limpar_empresa(candidato):
    candidato = re.sub(r"^\s*\d+\s*[-–—]\s*", "", str(candidato or "").strip())
    candidato = re.sub(r"\b\d{2}/\d{2}/\d{4}\b.*$", "", candidato).strip()
    candidato = re.sub(r"\bP[AÁ]G\.?:?\s*\d+\b.*$", "", candidato, flags=re.I).strip()
    candidato = re.sub(r"\bTELEFONE\b.*$", "", candidato, flags=re.I).strip()
    candidato = re.sub(r"\bENDERE[CÇ]O\b.*$", "", candidato, flags=re.I).strip()
    candidato = re.sub(r"\bBAIRRO\b.*$", "", candidato, flags=re.I).strip()
    candidato = re.sub(r"\bMUNIC[IÍ]PIO\b.*$", "", candidato, flags=re.I).strip()
    candidato = re.sub(r"\bCNPJ/CPF\b.*$", "", candidato, flags=re.I).strip()
    candidato = re.sub(r"\s{2,}", " ", candidato).strip(" -:|")
    return candidato


def _parece_empresa(candidato):
    candidato = _limpar_empresa(candidato)
    if len(candidato) < 4 or re.search(r"\d", candidato):
        return False

    candidato_norm = _norm(candidato)
    if any(b in candidato_norm for b in BLOCKLIST_EMPRESA):
        return False
    if any(suf in candidato_norm for suf in (" LTDA", " LIMITADA", " EIRELI", " S A", " S.A", " EPP", " ME ")):
        return True
    if " - " in candidato and len(candidato.split()) >= 2:
        return True
    return len(candidato.split()) >= 2


def extrair_empresa_relacao_calculo(texto: str) -> str | None:
    linhas = _linhas(texto)

    for i, linha in enumerate(linhas[:12]):
        lu = _norm(linha)
        if not any(rot in lu for rot in ("EMPRESA", "ESTABELECIMENTO", "RAZAO SOCIAL", "RAZAO")):
            continue

        candidatos = []
        if ":" in linha:
            candidatos.append(linha.split(":", 1)[1].strip())
        elif "-" in linha:
            candidatos.append(linha.split("-", 1)[1].strip())
        else:
            candidatos.append(linha)

        candidatos.extend(linhas[i + 1:i + 4])

        for candidato in candidatos:
            candidato = _limpar_empresa(candidato)
            if _parece_empresa(candidato):
                return candidato

    for linha in linhas[:15]:
        candidato = _limpar_empresa(linha)
        if _parece_empresa(candidato):
            return candidato

    return None


def extrair_competencia_relacao_calculo(texto: str) -> str | None:
    linhas = _linhas(texto)
    for linha in linhas[:20]:
        lu = _norm(linha)
        m = re.search(r"PERIODO\s*:\s*\d{2}/(\d{2})/(\d{4})\s+A\s+\d{2}/(\d{2})/(\d{4})", lu)
        if m and m.group(2) == m.group(4):
            return f"{m.group(3)}/{m.group(4)}"

        m = re.search(r"PERIODO\s*:\s*(\d{2})/(\d{2})/(\d{4})\s+A\s+(\d{2})/(\d{2})/(\d{4})", lu)
        if m and m.group(3) == m.group(6):
            return f"{m.group(5)}/{m.group(6)}"

        m = re.search(r"\b([A-Z]+)\s+DE\s+(20\d{2})\b", lu)
        if m:
            meses = {
                "JANEIRO": "01",
                "FEVEREIRO": "02",
                "MARCO": "03",
                "MARÇO": "03",
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


def _limpar_nome_colaborador(candidato):
    candidato = re.sub(r"^\s*\d+\s*[-.:|)]*\s*", "", str(candidato or "").strip())
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    candidato = re.sub(
        r"\b(ADM|CARGO|SITUACAO|TRABALHANDO|DEMITIDO|C.H.M|SALARIO|CBO|SIND|F\.REG|FILIAL|ORGANOGRAMA)\b.*$",
        "",
        candidato,
        flags=re.I,
    ).strip(" -:|")
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    return candidato


def extrair_colaboradores_relacao_calculo(texto: str, empresa=None) -> list[dict]:
    texto_norm = _norm(texto)
    candidatos = []

    for m in re.finditer(r"FUNC:\s*(?:\d+\s+)?(.{3,80}?)\s+ADM\b", texto_norm):
        nome = _limpar_nome_colaborador(m.group(1))
        if nome and nome_valido(nome, empresa) and _norm(nome) not in {_norm(c["nome"]) for c in candidatos}:
            candidatos.append({"nome": re.sub(r"\s+", " ", nome).strip().title()})

    if candidatos:
        return candidatos

    linhas = _linhas(texto)
    for i, linha in enumerate(linhas):
        lu = _norm(linha)
        if lu != "FUNC:" and not lu.startswith("FUNC:"):
            continue

        janela = linhas[i + 1:i + 6]
        if not janela:
            continue

        if re.fullmatch(r"\d+", _norm(janela[0])):
            janela = janela[1:]

        for prox in janela:
            candidato = _limpar_nome_colaborador(prox)
            if not candidato:
                continue
            if _norm(candidato) in BLOCKLIST_COLABORADOR:
                continue
            if nome_valido(candidato, empresa):
                nome = re.sub(r"\s+", " ", candidato).strip().title()
                if _norm(nome) not in {_norm(c["nome"]) for c in candidatos}:
                    candidatos.append({"nome": nome})
                break

    return candidatos


def extrair_dados_relacao_calculo(texto: str) -> dict:
    if not eh_layout_relacao_calculo(texto):
        return {}

    empresa = extrair_empresa_relacao_calculo(texto)
    competencia = extrair_competencia_relacao_calculo(texto)
    colaboradores = extrair_colaboradores_relacao_calculo(texto, empresa=empresa)

    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": colaboradores,
        "layout": "relacao_calculo",
    }
