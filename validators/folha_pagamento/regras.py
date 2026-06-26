import re
import unicodedata


MESES = {
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

BLOCKLIST_NOME = {
    "FOLHA",
    "PAGAMENTO",
    "RECIBO",
    "CNPJ",
    "COMPETENCIA",
    "COMPETÊNCIA",
    "PERIODO",
    "PERÍODO",
    "TOTAL",
    "VENCIMENTOS",
    "DESCONTOS",
    "PROVENTOS",
    "EMPRESA",
    "EMPREGADOR",
    "CARGO",
    "FUNCAO",
    "FUNÇÃO",
    "CBO",
    "DEPARTAMENTO",
    "ADMISSAO",
    "ADMISSÃO",
    "SALARIO",
    "SALÁRIO",
    "BASE",
    "INSS",
    "FGTS",
    "IRRF",
    "LIQUIDO",
    "LQUIDO",
    "ASSINATURA",
    "RUBRICA",
    "ASSINADO",
    "NOME DO FUNCIONARIO",
    "NOME DO FUNCIONÃRIO",
    "NOME DO COLABORADOR",
    "NOME DO EMPREGADO",
    "FUNCIONARIO",
    "FUNCIONÃRIO",
    "COLABORADOR",
    "EMPREGADO",
    "ESTAGIARIO",
    "ESTAGIÁRIOS",
    "ESTAGIARIOS",
    "CALCULO",
    "CÁLCULO",
    "NO.",
    "ANALISTA",
    "ENGENHEIRO",
    "AJUDANTE",
    "AUXILIAR",
    "OPERADOR",
    "ASSISTENTE",
    "TECNICO",
    "TÉCNICO",
    "MECANICO",
    "MECÂNICO",
    "VENDEDOR",
    "PEDREIRO",
    "SERVENTE",
    "MOTORISTA",
    "FISCAL",
    "ENCARREGADO",
    "LIDER",
    "LÍDER",
    "SUPERVISOR",
    "SOLDADOR",
    "ELETRICISTA",
    "COORDENADOR",
    "ALMOXARIFE",
    "VALIDACAO",
    "PADRAO",
    "MODELO",
    "DOCUMENTO",
    "LAYOUT",
    "TESTE",
    "BLOCO",
    "ANCHORS",
}

BLOCKLIST_EMPRESA = {
    "FOLHA",
    "PAGAMENTO",
    "RECIBO",
    "EXTRATO",
    "MENSAL",
    "HORAS",
    "SEMANAIS",
    "HORAS SEMANAIS",
    "CNPJ",
    "COMPETENCIA",
    "COMPETÃŠNCIA",
    "PERIODO",
    "PERÃODO",
    "TOTAL",
    "VENCIMENTOS",
    "DESCONTOS",
    "PROVENTOS",
    "CARGO",
    "FUNCAO",
    "FUNÃ‡ÃƒO",
    "CBO",
    "DEPARTAMENTO",
    "ADMISSAO",
    "ADMISSÃƒO",
    "SALARIO",
    "SALÃRIO",
    "BASE",
    "INSS",
    "FGTS",
    "IRRF",
    "LIQUIDO",
    "LÃQUIDO",
    "ASSINATURA",
    "RUBRICA",
    "ASSINADO",
    "CALCULO",
    "CÁLCULO",
    "FALTA",
    "ESTAGIARIO",
    "ESTAGIÁRIOS",
    "ESTAGIARIOS",
}

STOPWORDS_NOME = {"DE", "DA", "DO", "DAS", "DOS", "E"}

BLOCKLIST_COLABORADOR_EXTRA = {
    "EXTRATO",
    "MENSAL",
    "HORAS",
    "SEMANAIS",
    "HORAS SEMANAIS",
    "HORA",
    "MES",
    "IMPOSTO",
    "RENDA",
    "ADICIONAL",
    "NOTURNO",
    "CURSO",
    "PROGRAMA",
    "QUALIFICACAO",
    "AFASTADO",
    "AFASTADA",
    "DIREITOS",
    "INTEGRAIS",
    "FOLGA",
    "CAMPO",
    "PARCIAL",
    "PASS",
    "ADT",
    "INFOR",
    "VALE",
    "ALIMENTACAO",
    "ALIMENTACAO INFORMATIVA",
    "INFORMATIVA",
    "REFLEXO",
    "REFLEXOS",
    "EXTRAS",
    "DSR",
    "CONTRIBUICAO",
    "ASSIST",
    "ASSISTENCIA",
    "SITRAMON",
    "DESCONTO",
    "DESCONTOS",
    "ADIANTAMENTO",
    "FERIAS",
    "FALTA",
    "FALTAS",
    "ATESTADO",
    "AFASTAMENTO",
    "APURACAO",
    "APURACAO DOS",
    "APURACAO DO",
    "TRIBUTOS",
    "FEDERAIS",
    "SALDO",
    "COMPENSAR",
    "RECOLHER",
    "REMANESCENTE",
    "RESTITUIR",
    "ENCARGO",
    "COOPERATIVAS",
    "VALORES",
    "VALOR",
    "VALOR DE PIS",
    "PAGOS",
    "PIS",
    "DEBITOS",
    "CREDITOS",
    "DEBITO",
    "CREDITO",
    "CONTRIBUICAO PATRONAL",
    "BASE DE CALCULO",
    "BASE CALCULO",
    "RESUMO POR RUBRICAS",
    "RUBRICAS DO SERVICO",
    "APURACAO TRIBUTOS FEDERAIS",
    "ESTAGIARIO",
    "ESTAGIARIOS",
    "HORA EXTRA",
    "HORAS EXTRAS",
    "RESCISAO",
    "INSS",
    "FGTS",
    "IRRF",
    "VT",
    "VR",
    "VA",
    "BASE",
    "CALCULO",
    "CALCULOS",
    "VENCIMENTO",
    "VENCIMENTOS",
    "PROVENTO",
    "PROVENTOS",
    "LIQUIDO",
    "LQUIDO",
    "BRUTO",
    "TITULO",
    "TITULOS",
    "RESUMO",
    "RUBRICA",
    "RUBRICAS",
    "SERVICO",
    "SERVICOS",
    "NUMERO",
    "NUMERO DE DIRETORES",
    "NUMERO DE AUTONOMOS",
    "DIRETORES",
    "AUTONOMOS",
}

BLOCKLIST_EMPRESA_EXTRA = {
    "EXTRATO",
    "MENSAL",
    "HORAS",
    "SEMANAIS",
    "HORAS SEMANAIS",
    "RESUMO",
    "RELATORIO",
    "FUNCIONARIO",
    "FUNCIONARIOS",
    "COLABORADOR",
    "COLABORADORES",
    "EMPREGADO",
    "EMPREGADOS",
    "PAGAMENTO",
    "FOLHA",
    "COMPETENCIA",
    "VALOR DE PIS",
    "NUMERO DE DIRETORES",
    "NUMERO DE AUTONOMOS",
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


def _limpar_candidato(candidato):
    candidato = re.sub(r"^\s*\d+\s*[-.:|)]*\s*", "", str(candidato or "").strip())
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    candidato = re.split(
        r"\b(CBO|CARGO|FUNCAO|FUNÇÃO|DEPARTAMENTO|ADMISSAO|ADMISSÃO|COMPETENCIA|COMPETÊNCIA|FOLHA|TOTAL|"
        r"VENCIMENTOS|DESCONTOS|PROVENTOS|SALARIO|SALÁRIO|INSS|FGTS|IRRF|BASE|ASSINATURA|RUBRICA|EMPRESA|EMPREGADOR)\b",
        candidato,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    candidato = re.sub(r"\s{2,}", " ", candidato).strip()
    return candidato


def _tokens_norm(texto):
    return [t for t in _norm(texto).split() if t]


def _tem_bloqueio_textual(texto_norm, bloqueios):
    texto_tokens = set(re.findall(r"[A-Z0-9]+", texto_norm))
    for b in bloqueios:
        b_norm = _norm(b)
        b_tokens = [t for t in re.findall(r"[A-Z0-9]+", b_norm) if t]
        if not b_tokens:
            continue

        if len(b_tokens) == 1:
            token = b_tokens[0]
            if token in texto_tokens:
                return True
        elif b_norm in texto_norm:
            return True
    return False


def _parece_nome_humano(candidato, empresa=None):
    candidato = _limpar_candidato(candidato)
    if not candidato:
        return False

    if len(candidato) < 8 or re.search(r"\d", candidato):
        return False

    nome_norm = _norm(candidato)
    if empresa and nome_norm == _norm(empresa):
        return False

    if _tem_bloqueio_textual(nome_norm, BLOCKLIST_NOME):
        return False
    if _tem_bloqueio_textual(nome_norm, BLOCKLIST_COLABORADOR_EXTRA):
        return False

    palavras = _tokens_norm(candidato)
    if len(palavras) < 2 or len(palavras) > 6:
        return False

    if any(p in STOPWORDS_NOME for p in palavras) and len(palavras) == 2:
        return False

    if sum(1 for p in palavras if len(p) >= 3 and p not in STOPWORDS_NOME) < 2:
        return False

    if sum(1 for p in palavras if p in STOPWORDS_NOME) > 2:
        return False

    if any(p in BLOCKLIST_EMPRESA_EXTRA for p in palavras):
        return False

    return True


def nome_valido(nome, empresa=None):
    return _parece_nome_humano(nome, empresa=empresa)


def _empresa_valida(candidato):
    candidato = _limpar_candidato(candidato)
    if len(candidato) < 4 or re.search(r"\d", candidato):
        return False

    candidato_norm = _norm(candidato)
    if any(b in candidato_norm for b in BLOCKLIST_EMPRESA):
        return False
    if any(b in candidato_norm for b in BLOCKLIST_EMPRESA_EXTRA):
        return False

    if any(suf in candidato_norm for suf in (" LTDA", " S A", " S.A", " EIRELI", " ME ", " EPP ", " LIMITADA")):
        return True

    if _parece_nome_humano(candidato):
        return False

    palavras = [p for p in candidato.split() if p]
    return len(palavras) >= 2


def extrair_empresa(texto: str) -> str | None:
    linhas = _linhas(texto)

    for i, linha in enumerate(linhas):
        lu = _norm(linha)
        if any(rotulo in lu for rotulo in ("RAZAO SOCIAL", "RAZAO", "EMPRESA", "EMPREGADOR", "ESTABELECIMENTO")):
            candidatos = []
            if ":" in linha:
                candidatos.append(linha.split(":", 1)[1].strip())
            elif "-" in linha:
                candidatos.append(linha.split("-", 1)[1].strip())
            else:
                candidatos.append(linha)

            candidatos.extend(linhas[i + 1:i + 4])

            for cand in candidatos:
                cand = _limpar_candidato(cand)
                if _empresa_valida(cand):
                    return cand

    for linha in linhas[:30]:
        candidato = _limpar_candidato(linha)
        if _empresa_valida(candidato):
            return candidato

    return None


def extrair_competencia_folha(texto: str) -> str | None:
    def _extrair_de_texto(bloco: str) -> str | None:
        linhas = _linhas(bloco)

        # Primeiro procura o mes/ano isolado no topo do documento.
        for linha in linhas[:15]:
            lu = _norm(linha)
            m = re.fullmatch(r"(0[1-9]|1[0-2])/(20\d{2})", lu)
            if m:
                return f"{m.group(1)}/{m.group(2)}"

        for idx, linha in enumerate(linhas[:15]):
            lu = _norm(linha)

            m = re.search(r"\b(0[1-9]|1[0-2])/(20\d{2})\b", lu)
            if m:
                # Evita confundir datas de emissao/dia com competencia.
                if re.search(r"\b\d{2}/\d{2}/20\d{2}\b", lu):
                    continue
                if any(rot in lu for rot in ("EMISSAO", "HORAS", "PAGINA")):
                    continue
                return f"{m.group(1)}/{m.group(2)}"

            m = re.search(r"\b([A-Z]+)\s+DE\s+(20\d{2})\b", lu)
            if m:
                mes = MESES.get(m.group(1))
                if mes:
                    return f"{mes}/{m.group(2)}"

            m = re.search(r"\b([A-Z]+)\s*/\s*(20\d{2})\b", lu)
            if m:
                mes = MESES.get(m.group(1))
                if mes:
                    return f"{mes}/{m.group(2)}"

            m = re.search(r"PERIODO\s*:\s*(\d{2})/(\d{2})/(20\d{2})\s+A\s+(\d{2})/(\d{2})/(20\d{2})", lu)
            if m:
                return f"{m.group(2)}/{m.group(3)}"

            if any(rot in lu for rot in ("EXTRATO MENSAL", "FOLHA MENSAL", "COMPETENCIA", "COMPETÊNCIA")):
                prox = linhas[idx + 1] if idx + 1 < len(linhas) else ""
                prox_lu = _norm(prox)
                m = re.fullmatch(r"(0[1-9]|1[0-2])/(20\d{2})", prox_lu)
                if m:
                    return f"{m.group(1)}/{m.group(2)}"

        texto_norm = _norm(bloco)
        m = re.search(r"\b(0[1-9]|1[0-2])/(20\d{2})\b", texto_norm)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        return None

    partes = [p.strip() for p in str(texto or "").split("\f") if p and p.strip()]
    if partes:
        competencia = _extrair_de_texto(partes[0])
        if competencia:
            return competencia

    return _extrair_de_texto(texto)


def extrair_valor_total_folha(texto: str):
    if not texto:
        return None

    linhas = _linhas(texto)
    rotulos_prioritarios = [
        "VALOR LIQUIDO",
        "VALOR LÍQUIDO",
        "LIQUIDO A RECEBER",
        "LÍQUIDO A RECEBER",
        "TOTAL LIQUIDO",
        "TOTAL LÍQUIDO",
    ]
    rotulos_secundarios = [
        "TOTAL DE VENCIMENTOS",
        "TOTAL DE DESCONTOS",
    ]

    def _buscar_valor(trecho):
        m = re.search(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", trecho)
        if not m:
            return None
        valor = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(valor)
        except Exception:
            return None

    for idx, linha in enumerate(linhas):
        lu = _norm(linha)
        if not any(rotulo in lu for rotulo in rotulos_prioritarios):
            continue

        valor = _buscar_valor(linha)
        if valor is not None and valor > 0:
            return valor

        for prox in linhas[idx + 1: idx + 4]:
            valor = _buscar_valor(prox)
            if valor is not None and valor > 0:
                return valor

    for idx, linha in enumerate(linhas):
        lu = _norm(linha)
        if not any(rotulo in lu for rotulo in rotulos_secundarios):
            continue

        valor = _buscar_valor(linha)
        if valor is not None and valor > 0:
            return valor

        for prox in linhas[idx + 1: idx + 4]:
            valor = _buscar_valor(prox)
            if valor is not None and valor > 0:
                return valor

    return None


def extrair_colaboradores(texto: str, empresa=None) -> list[dict]:
    linhas = _linhas(texto)
    candidatos = []

    rotulos_nome = (
        "NOME DO FUNCIONARIO",
        "NOME DO FUNCIONÁRIO",
        "NOME DO COLABORADOR",
        "NOME DO EMPREGADO",
        "NOME:",
        "FUNCIONARIO",
        "FUNCIONÁRIO",
        "COLABORADOR",
        "EMPREGADO",
    )

    def _adicionar(candidato):
        candidato = _limpar_candidato(candidato)
        if nome_valido(candidato, empresa):
            nome = re.sub(r"\s+", " ", candidato).strip().title()
            if nome not in candidatos:
                candidatos.append(nome)

    def _tem_ancora_empregado(idx):
        for prox in linhas[idx + 1:idx + 5]:
            lu = _norm(prox)
            if re.match(r"^(EMPR|CPF|SITUACAO|VINCULO|CARGO|DEPTO|CC)\b", lu):
                return True
        return False

    for i, linha in enumerate(linhas):
        lu = _norm(linha)
        if not any(rotulo in lu for rotulo in rotulos_nome):
            continue

        candidato = ""
        if ":" in linha:
            candidato = linha.split(":", 1)[1].strip()
        elif "-" in linha:
            candidato = linha.split("-", 1)[1].strip()
        elif "|" in linha:
            candidato = linha.split("|", 1)[1].strip()

        if candidato:
            _adicionar(candidato)

        for prox in linhas[i + 1:i + 5]:
            candidato = _limpar_candidato(prox)
            if candidato and nome_valido(candidato, empresa):
                _adicionar(candidato)
                break

    for idx, linha in enumerate(linhas):
        if not re.match(r"^\s*\d{2,7}\s+", linha):
            continue
        candidato = _limpar_candidato(re.sub(r"^\s*\d+\s+", "", linha))
        if _empresa_valida(candidato):
            continue
        if not _tem_ancora_empregado(idx):
            continue
        if _parece_nome_humano(candidato, empresa=empresa):
            _adicionar(candidato)

    for linha in linhas:
        if re.match(r"^\s*\d{2,7}\s+", linha):
            continue
        candidato = _limpar_candidato(linha)
        if len(candidato.split()) < 3:
            continue
        if _empresa_valida(candidato):
            continue
        if _parece_nome_humano(candidato, empresa=empresa):
            _adicionar(candidato)

    return [{"nome": nome, "status": "✔ OK"} for nome in candidatos]
