import re
import unicodedata

from validators.folha_pagamento.regras import nome_valido


STOPWORDS_EMPRESA = {
    "EXTRATO",
    "MENSAL",
    "FOLHA",
    "PAGAMENTO",
    "RESUMO",
    "ESPELHO",
    "REFERENTE",
    "MES",
    "MES DE",
    "CNPJ",
    "CPF",
    "PAGINA",
    "HORAS",
    "EMISSAO",
    "NOME",
    "COLABORADOR",
    "COLABORADORES",
    "FUNCIONARIO",
    "FUNCIONARIOS",
    "SF",
    "IR",
    "PROVENTOS",
    "DESCONTOS",
    "ADMISSAO",
    "SALARIO",
}

IGNORAR_NOMES = {
    "TOTAL",
    "PROVENTOS",
    "DESCONTOS",
    "LIQUIDO",
    "BASE",
    "INSS",
    "FGTS",
    "IRRF",
    "SALARIO",
    "SALARIO BASE",
    "SALARIO MENSALISTA",
    "SALARIO PRO-LABORE",
    "REEMBOLSO",
    "RECARGA",
    "CELULAR",
    "DIA",
    "DIAS",
    "HORAS",
    "MENSAIS",
    "MENSAL",
    "ADIANTAMENTO",
    "CREDITO",
    "TRABALHADOR",
    "FALTAS",
    "INFORMADA",
    "SISTEMA",
    "LICENCIADO",
    "ESCRITORIO",
    "CONTABILIDADE",
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


def eh_layout_espelho_resumo_folha(texto: str) -> bool:
    texto_norm = _norm(texto)
    if "ESPELHO E RESUMO DA FOLHA MENSAL" in texto_norm:
        return True
    if "NOME DO COLABORADOR" in texto_norm and "TOTAL DE PROVENTOS" in texto_norm:
        return True
    return False


def _limpar_empresa(candidato):
    candidato = str(candidato or "").strip()
    candidato = re.sub(r"^\s*\d+\s*[-–—]\s*", "", candidato)
    candidato = re.sub(r"\s*\(\s*\d[\d./-]*\s*\)\s*$", "", candidato).strip()
    candidato = re.sub(r"\s{2,}", " ", candidato).strip(" -:|")
    candidato = re.sub(r"\bCNPJ\b.*$", "", candidato, flags=re.I).strip(" -:|")

    m = re.search(r"(.+?\b(?:LTDA|LIMITADA|EIRELI|EPP|ME)\b)", candidato, flags=re.I)
    if m:
        candidato = m.group(1).strip()
    else:
        candidato = re.sub(r"\s+[A-ZÀ-Ü0-9 .&'/-]+/[A-Z]{2}\b.*$", "", candidato, flags=re.I).strip(" -:|")

    candidato = re.sub(r"\s{2,}", " ", candidato).strip(" -:|")
    return candidato


def _eh_candidato_empresa(texto):
    texto_norm = _norm(texto)
    if not texto_norm:
        return False
    if any(stop in texto_norm for stop in STOPWORDS_EMPRESA):
        return False
    return any(suf in texto_norm for suf in (" LTDA", " LIMITADA", " EIRELI", " EPP", " ME "))


def extrair_empresa_espelho_resumo_folha(texto: str) -> str | None:
    texto_norm = _norm(texto)
    linhas = _linhas(texto)

    m = re.search(
        r"EMPRESA:\s*(?:\d+\s*-\s*)?(.+?\b(?:LTDA|LIMITADA|EIRELI|EPP|ME)\b)",
        texto_norm,
        flags=re.S,
    )
    if m:
        candidato = _limpar_empresa(m.group(1))
        if candidato and not any(b in _norm(candidato) for b in STOPWORDS_EMPRESA):
            return candidato

    for i, linha in enumerate(linhas[:12]):
        lu = _norm(linha)
        if "EMPRESA:" not in lu and not _eh_candidato_empresa(lu):
            continue

        candidatos = []
        if "EMPRESA:" in lu and ":" in linha:
            candidatos.append(linha.split(":", 1)[1].strip())
        candidatos.append(linha)
        if i + 1 < len(linhas):
            candidatos.append(linhas[i + 1])
        if i + 2 < len(linhas):
            candidatos.append(linhas[i + 2])

        for cand in candidatos:
            cand = _limpar_empresa(cand)
            if cand and not any(b in _norm(cand) for b in STOPWORDS_EMPRESA):
                if _eh_candidato_empresa(cand) or "EMPRESA:" in lu:
                    return cand

    return None


def extrair_competencia_espelho_resumo_folha(texto: str) -> str | None:
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

    m = re.search(r"REFERENTE AO MES DE\s+([A-Z]+)/(\d{4})", texto_norm)
    if m:
        mes = meses.get(m.group(1), m.group(1))
        return f"{mes}/{m.group(2)}"

    m = re.search(r"REFERENTE AO M[EÊ]S DE\s+([A-Z]+)(?:/| DE )(\d{4})", texto_norm)
    if m:
        mes = meses.get(m.group(1))
        if mes:
            return f"{mes}/{m.group(2)}"

    for linha in _linhas(texto)[:20]:
        lu = _norm(linha)
        m = re.search(r"\b([A-Z]+)/(20\d{2})\b", lu)
        if m and m.group(1) in meses:
            return f"{meses[m.group(1)]}/{m.group(2)}"
        m = re.search(r"\b([A-Z]+)\s+DE\s+(20\d{2})\b", lu)
        if m and m.group(1) in meses:
            return f"{meses[m.group(1)]}/{m.group(2)}"

    return None


def _limpar_nome_candidato(candidato):
    candidato = re.sub(r"^\s*\d+\s*", "", str(candidato or "").strip())
    candidato = re.sub(r"(?:\s+[Oo01I2])+\s*$", "", candidato).strip()
    candidato = re.sub(r"\b(?:O|o|0|1|2)\b\s*$", "", candidato).strip()
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    candidato = re.sub(
        r"\b(ADMISSAO|SALARIO BASE|HORAS MENSAIS|SALARIO|CARGO|FUNCAO|FUNÇÃO|SITUACAO|SITUAÇÃO|ATIVO|INATIVO|TOTAL|PROVENTOS|DESCONTOS|LIQUIDO|LÍQUIDO|BASE|INSS|FGTS|IRRF|NF)\b.*$",
        "",
        candidato,
        flags=re.I,
    ).strip(" -:|")
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    return candidato


def extrair_colaboradores_espelho_resumo_folha(texto: str, empresa: str | None = None) -> list[dict]:
    linhas = _linhas(texto)
    nomes = []

    def adicionar(candidato):
        candidato = _limpar_nome_candidato(candidato)
        if not candidato:
            return
        if len(candidato.split()) < 2:
            return
        if empresa and _norm(candidato) == _norm(empresa):
            return
        if any(b in _norm(candidato) for b in IGNORAR_NOMES):
            return
        if nome_valido(candidato, empresa=empresa):
            titulo = re.sub(r"\s+", " ", candidato).strip().title()
            if all(_norm(n) != _norm(titulo) for n in nomes):
                nomes.append(titulo)

    for idx, linha in enumerate(linhas):
        lu = _norm(linha)
        if not lu:
            continue

        if re.match(r"^\d{1,7}\s+[A-ZÀ-Ü]", linha):
            base = re.sub(r"^\s*\d+\s+", "", linha).strip()
            base_norm = _norm(base)
            marcador = re.search(
                r"(ADMISS|SALARIO BASE|HORAS MENSAIS|TOTAL DE PROVENTOS|TOTAL DE DESCONTOS|LIQUIDO|LÍQUIDO|BASE INSS|PAGAMENTO EFETUADO)",
                base_norm,
            )
            if marcador:
                base = base[:marcador.start()].strip()
            base = _limpar_nome_candidato(base)
            prox = linhas[idx + 1] if idx + 1 < len(linhas) else ""
            if prox and re.fullmatch(r"[A-ZÀ-Ü][A-ZÀ-Ü .'-]{1,40}", prox.strip()):
                if base.endswith((" DE", " DA", " DO", " DAS", " DOS")) or len(base.split()) <= 3:
                    adicionar(f"{base} {prox}")
                    continue
            adicionar(base)
            continue

        if re.search(r"\bNOME DO COLABORADOR\b", lu):
            continue
        if any(b in lu for b in ("TOTAL DE PROVENTOS", "TOTAL DE DESCONTOS", "LÍQUIDO ->", "LIQUIDO ->")):
            continue

    return [{"nome": nome} for nome in nomes]


def extrair_dados_espelho_resumo_folha(texto: str) -> dict:
    if not eh_layout_espelho_resumo_folha(texto):
        return {}

    empresa = extrair_empresa_espelho_resumo_folha(texto)
    competencia = extrair_competencia_espelho_resumo_folha(texto)
    colaboradores = extrair_colaboradores_espelho_resumo_folha(texto, empresa=empresa)

    return {
        "empresa": empresa,
        "competencia": competencia,
        "colaboradores": colaboradores,
        "layout": "espelho_resumo_folha",
    }
