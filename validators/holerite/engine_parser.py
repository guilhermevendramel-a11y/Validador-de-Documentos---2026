import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

MESES = {
    "JANEIRO": "01",
    "FEVEREIRO": "02",
    "MARCO": "03",
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

INVALID_NAME_TOKENS = {"CPF", "CNPJ", "CBO", "BANCO", "AGENCIA", "CONTA", "VALOR", "DADOS", "PAGAMENTO", "TRANSFERENCIA", "FOLHA", "MENSAL", "RECIBO", "DEMONSTRATIVO"}
INVALID_NAME_TOKENS = INVALID_NAME_TOKENS | {
    "BASE", "BASES", "CALC", "CALCULO", "CALCULO", "SAL", "SALARIO", "SALARIOS",
    "CONTR", "INSS", "FGTS", "IRRF", "FAIXA", "MES", "MES", "MES",
    "PROVENTOS", "DESCONTOS", "LIQUIDO", "LIQUIDA", "TOTAL", "TOTAIS",
    "DEDUCOES", "VENCIMENTOS", "EVENTOS", "HABER", "HABERES", "RUBRICA",
    "ASSINATURA", "DECLARO", "RECEBIDO", "EMPRESA", "EMPREGADOR", "COLABORADOR",
    "FUNCIONARIO", "FUNCIONARIO", "FUNCIONARIO", "CARGO", "SETOR", "DEPARTAMENTO",
    "REFERENCIA", "REFERENCIAS", "APURACAO", "APURACAO", "COMPETENCIA", "COMPETENCIA",
    "TER", "IMPORTANCIA", "DISCRIMINADA", "NESTE", "NESTA", "NESTES", "NESTAS",
    "ASSUNTO", "REFERENTE", "RECEBI", "PEDIDO", "COMPROVANTE", "NOTA", "FISCAL",
    "AJUDA", "CUSTO", "CESTA", "BASICA", "BASICO", "MONTADOR", "MOTORISTA",
    "ENCARREGADO", "AUXILIAR", "ANALISTA", "ASSISTENTE", "OPERADOR", "SERVENTE",
    "GERENTE", "SUPERVISOR", "COORDENADOR", "TECNICO", "UH", "OUTROS",
    "SALDO", "CONTRI", "CAL", "FAIXA", "MES", "SERVICOS",
    "NOME", "RECEBEDOR", "FAVORECIDO", "BENEFICIARIO", "BENEFICIÁRIO", "PAGADOR",
    "DESTINATARIO", "DESTINATÁRIO",
}

SUFIXOS_NOME_RUIDO = {
    "DE",
    "DA",
    "DO",
    "DAS",
    "DOS",
    "E",
    "RECEBER",
    "SALARIO",
    "SALARIO",
    "PAGAMENTO",
    "ADIANTAMENTO",
    "RECIBO",
}

PREFIXOS_NOME_RUIDO = {
    "RUA",
    "AV",
    "AVENIDA",
    "TRAVESSA",
    "ESTRADA",
    "RODOVIA",
    "ALAMEDA",
    "PRACA",
    "LOTE",
    "QUADRA",
    "NUMERO",
}

ASSINATURA_ROTULOS = (
    "ASSINATURA E DATA",
    "ASSINATURA OU VISTO",
    "ASSINATURA DO FUNCIONARIO",
    "ASSINATURA DO FUNCIONÁRIO",
    "ASSINATURA DO EMPREGADO",
    "DECLARO TER RECEBIDO",
    "RUBRICA",
    "ASSINADO",
    "ASSINATURA",
)

VALOR_ROTULOS = (
    "VALOR LIQUIDO",
    "VALOR LÍQUIDO",
    "LIQUIDO A RECEBER",
    "LÍQUIDO A RECEBER",
    "LQUIDO A RECEBER",
    "TOTAL LIQUIDO",
    "TOTAL LÍQUIDO",
    "TOTAL LQUIDO",
    "VALOR A RECEBER",
)


def normalizar_texto(texto: Any) -> str:
    if texto is None:
        return ""
    txt = str(texto).replace("\r", "\n").replace("\u00a0", " ")
    txt = re.sub(r"[\t\f\v]+", " ", txt)
    txt = re.sub(r" +", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def normalizar_nome(nome: Any) -> str:
    txt = normalizar_texto(nome).upper()
    txt = unicodedata.normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")
    txt = re.sub(r"[^A-Z0-9\s]", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    tokens_raw = [t for t in txt.split() if t]
    while tokens_raw and tokens_raw[0] in {"DE", "DA", "DO", "DAS", "DOS", "A", "O"}:
        tokens_raw.pop(0)
    while tokens_raw and tokens_raw[0] in PREFIXOS_NOME_RUIDO:
        tokens_raw.pop(0)
    while len(tokens_raw) > 1 and tokens_raw[-1] in PREFIXOS_NOME_RUIDO:
        tokens_raw.pop()
    tokens = [t for t in tokens_raw if t not in INVALID_NAME_TOKENS and len(t) > 1]
    while tokens and tokens[0] in {"DE", "DA", "DO", "DAS", "DOS", "A", "O"}:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in SUFIXOS_NOME_RUIDO:
        tokens.pop()
    return " ".join(tokens)


def sem_acento(texto: Any) -> str:
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ASCII", "ignore").decode("ASCII")


def _candidato_parece_nome(texto: Any) -> bool:
    nome = normalizar_nome(texto)
    if not nome:
        return False
    tokens = nome.split()
    if len(tokens) < 2 or len(tokens) > 6:
        return False
    if re.search(r"\d", nome):
        return False
    if any(tok in INVALID_NAME_TOKENS for tok in tokens):
        return False
    if sum(1 for t in tokens if len(t) >= 3) < 2:
        return False
    if len(nome) < 8:
        return False
    return True


def normalizar_valor(valor: Any) -> float:
    if valor is None:
        return 0.0
    txt = str(valor).strip().replace("R$", "").replace("r$", "").replace(" ", "")
    txt = re.sub(r"[^\d,\.-]", "", txt)
    if txt in {"", "-", ".", ","}:
        return 0.0
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif "," in txt:
        txt = txt.replace(",", ".")
    try:
        return round(float(txt), 2)
    except (TypeError, ValueError):
        return 0.0


def buscar_com_padroes(texto: str, padroes: List[str]) -> Tuple[Optional[str], Optional[str]]:
    for padrao in padroes:
        m = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip(), padrao
    return None, None


def extrair_cnpj(texto: str) -> Optional[str]:
    m = re.search(r"\b(\d{2}[\.\s]?\d{3}[\.\s]?\d{3}[\/]\d{4}[-\s]?\d{2})\b", texto)
    if not m:
        return None
    dig = re.sub(r"\D", "", m.group(1))
    return f"{dig[:2]}.{dig[2:5]}.{dig[5:8]}/{dig[8:12]}-{dig[12:]}" if len(dig) == 14 else None


def extrair_competencia(texto: str) -> Optional[str]:
    t = normalizar_nome(texto)
    m = re.search(r"\b(?:COMPETENCIA\s*)?(0?[1-9]|1[0-2])[\/-](20\d{2})\b", t)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    m = re.search(r"\b(FOLHA\s+MENSAL\s+)?([A-Z]+)\s+DE\s+(20\d{2})\b", t)
    if m and m.group(2) in MESES:
        return f"{MESES[m.group(2)]}/{m.group(3)}"
    return None


def extrair_data_pagamento(texto: str) -> Optional[str]:
    data, _ = buscar_com_padroes(texto, [r"TRANSFER[EE]NCIA\s+EFETUADA\s+EM\s+(\d{2}/\d{2}/\d{4})", r"DATA\s+DE\s+PAGAMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", r"\b(\d{2}/\d{2}/\d{4})\b"])
    return data


def extrair_assinatura_data_holerite(texto: str) -> Dict[str, Any]:
    linhas = _linhas_validas(texto)
    texto_norm = sem_acento(texto).upper()
    padrao_data = re.compile(r"\b([0-3]?\d/[01]?\d/\d{2,4})\b")

    def _ano4(dt: str) -> str:
        partes = dt.split("/")
        if len(partes) != 3:
            return dt
        dd, mm, aa = partes
        if len(aa) == 2:
            aa_int = int(aa)
            aa = f"20{aa}" if aa_int <= 69 else f"19{aa}"
        return f"{int(dd):02d}/{int(mm):02d}/{aa}"

    candidatos = []
    for idx, linha in enumerate(linhas):
        linha_norm = sem_acento(linha).upper()
        rotulo = next((r for r in ASSINATURA_ROTULOS if r in linha_norm), None)
        if not rotulo:
            continue

        janela = linhas[max(0, idx - 2): min(len(linhas), idx + 5)]
        for janela_idx, prox in enumerate(janela):
            for dt in padrao_data.findall(prox):
                score = 80
                if rotulo in {"ASSINATURA E DATA", "ASSINATURA OU VISTO", "DECLARO TER RECEBIDO"}:
                    score = 110
                elif rotulo in {"RUBRICA", "ASSINADO"}:
                    score = 100
                elif rotulo == "ASSINATURA":
                    score = 90
                if janela_idx == 0:
                    score += 10
                elif janela_idx <= 2:
                    score += 5
                if idx >= int(len(linhas) * 0.55):
                    score += 10
                candidatos.append((score, _ano4(dt), rotulo))

    if candidatos:
        candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
        melhor = candidatos[0]
        return {
            "assinatura": True,
            "data": melhor[1],
            "rotulo": melhor[2],
            "modelo_assinatura": "inferior" if melhor[2] in {"ASSINATURA OU VISTO", "ASSINATURA", "RUBRICA", "DECLARO TER RECEBIDO"} else "direita",
        }

    if "ASSINATURA" in texto_norm or "RUBRICA" in texto_norm:
        dt = None
        m = padrao_data.search(texto_norm)
        if m:
            dt = _ano4(m.group(1))
        return {
            "assinatura": bool(dt),
            "data": dt,
            "rotulo": "ASSINATURA",
            "modelo_assinatura": None,
        }

    return {
        "assinatura": False,
        "data": None,
        "rotulo": None,
        "modelo_assinatura": None,
    }


def extrair_assinatura_textual_ou_indicio(texto: str) -> Optional[bool]:
    return bool(extrair_assinatura_data_holerite(texto).get("assinatura"))


def _linhas_validas(texto: str) -> List[str]:
    return [l.strip() for l in normalizar_texto(texto).split("\n") if l.strip()]


def _compactar_texto(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", sem_acento(texto).upper())


def _rotulo_valor_liquido(texto: str) -> Optional[str]:
    compact = _compactar_texto(texto)
    if not compact:
        return None

    if "VALORLIQUIDO" in compact or "VALORLQUIDO" in compact:
        return "VALOR LIQUIDO"
    if "LIQUIDOARECEBER" in compact or "LQUIDOARECEBER" in compact:
        return "LIQUIDO A RECEBER"
    if "TOTALLIQUIDO" in compact or "TOTALLQUIDO" in compact:
        return "TOTAL LIQUIDO"
    if "VALORARECEBER" in compact:
        return "VALOR A RECEBER"
    if ("LIQUIDO" in compact or "LQUIDO" in compact) and any(mark in compact for mark in ("VALOR", "TOTAL", "RECEBER")):
        if any(bloq in compact for bloq in ("DESCONTO", "FERIAS", "ADIANTAMENTO", "SALARIOBASE", "SALARIOCONTR", "INSS", "FGTS", "IRRF", "ASSISTENCIAL")):
            return None
        return "LIQUIDO"
    return None


def _extrair_valor_proximo_de_rotulo(
    linhas: List[str],
    rotulos: List[str],
    janela_linhas: int = 3,
    debug_tag: str = "valor_rotulo",
) -> Tuple[float, Optional[str], Optional[str]]:
    rotulos_norm = [sem_acento(rotulo).upper() for rotulo in rotulos if rotulo]

    for idx, linha in enumerate(linhas):
        linha_norm = sem_acento(linha).upper()
        rotulo_encontrado = None
        pos_rotulo = -1
        for rotulo in rotulos_norm:
            pos = linha_norm.find(rotulo)
            if pos != -1:
                rotulo_encontrado = rotulo
                pos_rotulo = pos
                break
        if rotulo_encontrado is None:
            continue

        trecho = linha[pos_rotulo + len(rotulo_encontrado):]
        valores_linha = re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", trecho)
        if valores_linha:
            valor = normalizar_valor(valores_linha[0])
            if valor > 0:
                return valor, debug_tag, rotulo_encontrado

        janela = linhas[idx + 1: idx + 1 + janela_linhas]
        for prox in janela:
            valores_prox = re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", prox)
            if valores_prox:
                valor = normalizar_valor(valores_prox[0])
                if valor > 0:
                    return valor, f"{debug_tag}_janela", rotulo_encontrado

    return 0.0, None, None


def extrair_nome_colaborador_holerite(texto: str, nome_arquivo: str = "") -> Optional[str]:
    linhas = _linhas_validas(texto)
    nomes_bons = []
    labels = ("NOME DO FUNCIONARIO", "NOME DO FUNCIONÁRIO", "NOME DO COLABORADOR", "NOME DO EMPREGADO", "FUNCIONARIO", "FUNCIONÁRIO", "COLABORADOR", "EMPREGADO")
    blocos_fortes = ("BASE", "BASES", "CALC", "CALCULO", "INSS", "FGTS", "IRRF", "DESCONT", "PROVENT", "VENCIMENT", "LIQUID", "ASSINATURA", "RUBRICA", "RECIBO", "FOLHA")

    for i, linha in enumerate(linhas):
        lu = sem_acento(linha).upper()
        if not any(lbl in lu for lbl in labels):
            continue

        partes = re.split(r"[:\-]", linha, maxsplit=1)
        if len(partes) > 1:
            candidato = partes[1].strip()
            candidato = re.split(r"\b(CBO|CPF|PIS|CARGO|ADMISS|COMPET|VALOR|FOLHA|BASE|INSS|FGTS|IRRF|DESCONT|PROVENT|VENCIMENT|ASSINATURA|RUBRICA)\b", candidato, maxsplit=1)[0].strip()
            if _candidato_parece_nome(candidato):
                nomes_bons.append(normalizar_nome(candidato))

        for prox in linhas[i + 1:i + 4]:
            candidato = re.sub(r"^\d+\s+", "", prox).strip()
            candidato = re.split(r"\b(CBO|CPF|PIS|CARGO|ADMISS|COMPET|VALOR|FOLHA|BASE|INSS|FGTS|IRRF|DESCONT|PROVENT|VENCIMENT|ASSINATURA|RUBRICA)\b", candidato, maxsplit=1)[0].strip()
            if _candidato_parece_nome(candidato):
                nomes_bons.append(normalizar_nome(candidato))
                break

    for linha in linhas[:20]:
        candidato = re.sub(r"^\d+\s+", "", linha).strip()
        candidato = re.split(r"\b(CBO|CPF|PIS|CARGO|ADMISS|COMPET|VALOR|FOLHA|BASE|INSS|FGTS|IRRF|DESCONT|PROVENT|VENCIMENT|ASSINATURA|RUBRICA)\b", candidato, maxsplit=1)[0].strip()
        if not candidato:
            continue
        if any(tok in sem_acento(candidato).upper() for tok in blocos_fortes):
            continue
        if _candidato_parece_nome(candidato):
            nomes_bons.append(normalizar_nome(candidato))
            break

    if nome_arquivo:
        base = re.sub(r"\.[A-Za-z0-9]+$", "", str(nome_arquivo))
        base = re.sub(r"^[0-9a-fA-F-]{20,}_", "", base)
        base = base.replace("_", " ").replace("-", " ")
        base = normalizar_nome(base)
        if _candidato_parece_nome(base):
            return base

    return None


def _extrair_nome_holerite(linhas: List[str], tu: str) -> Tuple[Optional[str], List[str]]:
    debug: List[str] = []
    bloqueios = {
        "FOLHA", "RECIBO", "LIQUIDO", "VENCIMENTOS", "DESCONTOS", "ASSINATURA",
        "CNPJ", "CPF", "CBO", "EMPRESA", "LTDA", "EIRELI", "S A", "SOCIAL",
        "CONSULTORIA", "SERVICOS", "SERVICOS", "TECNICOS", "ENGENHARIA",
        "NOME DO FUNCIONARIO", "NOME DO FUNCIONÁRIO", "NOME DO COLABORADOR",
        "NOME DO EMPREGADO", "FUNCIONARIO", "FUNCIONÁRIO", "COLABORADOR", "EMPREGADO",
    }

    padroes_linha = [
        r"NOME\s+(?:DO\s+)?(?:FUNCIONARIO|FUNCIONÁRIO|COLABORADOR|EMPREGADO)\s*[:\-]?\s*([A-ZÀ-Ú\s]{8,120})",
        r"\bNOME\s*[:\-]\s*([A-ZÀ-Ú\s]{8,120})",
        r"\bFUNCIONARIO\s*[:\-]\s*([A-ZÀ-Ú\s]{8,120})",
    ]
    for padrao in padroes_linha:
        m = re.search(padrao, tu, re.IGNORECASE)
        if m:
            candidato = re.split(r"\b(CBO|CPF|PIS|CARGO|ADMISS|COMPET|VALOR|FOLHA)\b", m.group(1))[0].strip()
            nome = normalizar_nome(candidato)
            if nome and len(nome.split()) >= 2:
                debug.append("nome_rotulo")
                return nome, debug

    for i, linha in enumerate(linhas):
        lu = sem_acento(linha).upper()
        if any(anc in lu for anc in ("NOME DO FUNCIONARIO", "NOME DO FUNCIONÁRIO", "NOME DO COLABORADOR", "NOME DO EMPREGADO")) or (
            "NOME" in lu and ("FUNCIONARIO" in lu or "FUNCIONÁRIO" in lu or "COLABORADOR" in lu or "EMPREGADO" in lu)
        ):
            janela = " ".join(linhas[i:i + 3])
            m = re.search(r"\b\d+\s+([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,}?)(?=\s+\d{2,4}\b|\s+CBO\b|$)", janela, re.IGNORECASE)
            if m:
                nome = normalizar_nome(m.group(1))
                if nome and len(nome.split()) >= 2:
                    debug.append("nome_codigo")
                    return nome, debug
            if i + 1 < len(linhas):
                prox = re.sub(r"^\d+\s+", "", linhas[i + 1])
                prox = re.split(r"\b(CBO|CPF|PIS|CARGO|ADMISS|COMPET|VALOR|FOLHA)\b", prox)[0].strip()
                nome = normalizar_nome(prox)
                if nome and len(nome.split()) >= 2:
                    debug.append("nome_linha_seguinte")
                    return nome, debug

    for linha in linhas:
        nome = normalizar_nome(linha)
        if nome and len(nome.split()) >= 2:
            if any(b in nome for b in bloqueios):
                continue
            if re.search(r"\d", nome):
                continue
            if any(tok.isalpha() for tok in nome):
                debug.append("nome_fallback")
                return nome, debug

    return None, debug


def _extrair_nome_holerite_detalhado(linhas: List[str], tu: str, nome_arquivo: str = "") -> Dict[str, Any]:
    debug: List[str] = []
    bloqueios = {
        "FOLHA", "RECIBO", "LIQUIDO", "VENCIMENTOS", "DESCONTOS", "ASSINATURA",
        "CNPJ", "CPF", "PIS", "CBO", "EMPRESA", "LTDA", "EIRELI", "S A", "SOCIAL",
        "CONSULTORIA", "SERVICOS", "SERVICOS", "TECNICOS", "ENGENHARIA", "INDUSTRIA",
        "COMERCIO", "MATRIZ", "FILIAL", "ENDERECO", "ENDEREÇO", "DEMONSTRATIVO",
        "NOME DO FUNCIONARIO", "NOME DO FUNCIONÁRIO", "NOME DO COLABORADOR",
        "NOME DO EMPREGADO", "FUNCIONARIO", "FUNCIONÁRIO", "COLABORADOR", "EMPREGADO",
    }

    def _cortar(candidato: str) -> str:
        candidato = re.split(r"\b(CBO|CPF|PIS|CARGO|ADMISS|COMPET|VALOR|FOLHA|RUBRICA|ASSINATURA|FUNCAO|FUNCAO|FUNÇÃO)\b", candidato)[0].strip()
        candidato = re.sub(r"\s{2,}", " ", candidato).strip()
        return candidato

    # Rotulo e valor na mesma linha.
    for i, linha in enumerate(linhas):
        lu = sem_acento(linha).upper()
        if not any(anc in lu for anc in ("NOME DO FUNCIONARIO", "NOME DO FUNCIONÁRIO", "NOME DO COLABORADOR", "NOME DO EMPREGADO")) and not (
            "NOME" in lu and ("FUNCIONARIO" in lu or "FUNCIONÁRIO" in lu or "COLABORADOR" in lu or "EMPREGADO" in lu)
        ):
            continue

        candidato = ""
        if ":" in linha:
            candidato = linha.split(":", 1)[1].strip()
        elif "-" in linha:
            candidato = linha.split("-", 1)[1].strip()
        candidato = _cortar(candidato)
        if _candidato_parece_nome(candidato):
            return {
                "nome": normalizar_nome(candidato),
                "metodo": "nome_rotulo",
                "confianca": 0.97,
                "evidencia": {"tipo": "nome", "metodo": "nome_rotulo", "linha": linha.strip(), "valor": normalizar_nome(candidato)},
                "debug": ["nome_rotulo"],
            }

        if i + 1 < len(linhas):
            prox = re.sub(r"^\d+\s+", "", linhas[i + 1]).strip()
            prox = _cortar(prox)
            if _candidato_parece_nome(prox):
                return {
                    "nome": normalizar_nome(prox),
                    "metodo": "nome_linha_seguinte",
                    "confianca": 0.93,
                    "evidencia": {
                        "tipo": "nome",
                        "metodo": "nome_linha_seguinte",
                        "linha": f"{linha.strip()} | {linhas[i + 1].strip()}",
                        "valor": normalizar_nome(prox),
                    },
                    "debug": ["nome_linha_seguinte"],
                }

        if i + 2 < len(linhas):
            janela = "\n".join(linhas[i + 1:i + 4])
            m = re.search(r"\b\d+\s+([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,}?)(?=\s+\d{2,4}\b|\s+CBO\b|$)", janela, re.IGNORECASE)
            if m:
                candidato = _cortar(m.group(1))
                if _candidato_parece_nome(candidato):
                    return {
                        "nome": normalizar_nome(candidato),
                        "metodo": "nome_codigo",
                        "confianca": 0.9,
                        "evidencia": {
                            "tipo": "nome",
                            "metodo": "nome_codigo",
                            "linha": janela.strip(),
                            "valor": normalizar_nome(candidato),
                        },
                        "debug": ["nome_codigo"],
                    }

    for linha in linhas:
        m = re.search(r"^\s*\d+\s+([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,}?)(?=\s+\d{2,4}\b|\s+CBO\b|$)", linha, re.IGNORECASE)
        if m:
            candidato = _cortar(m.group(1))
            if _candidato_parece_nome(candidato):
                return {
                    "nome": normalizar_nome(candidato),
                    "metodo": "nome_codigo",
                    "confianca": 0.88,
                    "evidencia": {
                        "tipo": "nome",
                        "metodo": "nome_codigo",
                        "linha": linha.strip(),
                        "valor": normalizar_nome(candidato),
                    },
                    "debug": ["nome_codigo"],
                }

    # Rotulo generico e Itau "dados da conta creditada".
    texto_norm = normalizar_texto(tu)
    m = re.search(
        r"DADOS\s+DA\s+CONTA\s+CREDITADA\s*:?(.+?)\bNOME\s*:\s*(.+?)(?:\n|VALOR\s*:|CPF|CNPJ|BANCO|AGENCIA|AGÊNCIA|CONTA|DATA|$)",
        texto_norm,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        candidato = _cortar(m.group(2))
        if _candidato_parece_nome(candidato):
            return {
                "nome": normalizar_nome(candidato),
                "metodo": "itau_nome_creditada",
                "confianca": 0.9,
                "evidencia": {
                    "tipo": "nome",
                    "metodo": "itau_nome_creditada",
                    "linha": m.group(0).strip(),
                    "valor": normalizar_nome(candidato),
                },
                "debug": ["itau_nome_creditada"],
            }

    m = re.search(r"\bNOME\s*:\s*(.+?)(?:\n|CPF|VALOR|BANCO|AGENCIA|AGÊNCIA|CONTA|DATA|TIPO|INSTITUICAO|INSTITUIÇÃO|$)", texto_norm, re.IGNORECASE | re.DOTALL)
    if m:
        candidato = _cortar(m.group(1))
        if _candidato_parece_nome(candidato):
            return {
                "nome": normalizar_nome(candidato),
                "metodo": "nome_generico",
                "confianca": 0.83,
                "evidencia": {
                    "tipo": "nome",
                    "metodo": "nome_generico",
                    "linha": m.group(0).strip(),
                    "valor": normalizar_nome(candidato),
                },
                "debug": ["nome_generico"],
            }

    if nome_arquivo:
        nome_arquivo_norm = normalizar_nome(nome_arquivo)
        if _candidato_parece_nome(nome_arquivo_norm):
            return {
                "nome": nome_arquivo_norm,
                "metodo": "nome_arquivo",
                "confianca": 0.58,
                "evidencia": {"tipo": "nome", "metodo": "nome_arquivo", "linha": nome_arquivo, "valor": nome_arquivo_norm},
                "debug": ["nome_arquivo"],
            }

    for linha in linhas[:20]:
        candidato = _cortar(re.sub(r"^\d+\s+", "", linha))
        if _candidato_parece_nome(candidato):
            nome = normalizar_nome(candidato)
            if any(b in nome for b in bloqueios):
                continue
            return {
                "nome": nome,
                "metodo": "nome_fallback",
                "confianca": 0.62,
                "evidencia": {"tipo": "nome", "metodo": "nome_fallback", "linha": linha.strip(), "valor": nome},
                "debug": ["nome_fallback"],
            }

    return {
        "nome": None,
        "metodo": "nao_identificado",
        "confianca": 0.0,
        "evidencia": None,
        "debug": [],
    }


def extrair_nome_comprovante_robusto(texto: str, nome_arquivo: str = "") -> Tuple[Optional[str], List[str]]:
    linhas = _linhas_validas(texto)
    debug: List[str] = []

    rotulos = (
        "NOME",
        "RECEBEDOR",
        "FAVORECIDO",
        "DESTINATARIO",
        "DESTINATÁRIO",
        "BENEFICIARIO",
        "BENEFICIÁRIO",
    )
    bloqueios = (
        "VALOR",
        "CPF",
        "CNPJ",
        "BANCO",
        "AGENCIA",
        "AGÊNCIA",
        "CONTA",
        "DATA",
        "TIPO",
        "INSTITUICAO",
        "INSTITUIÇÃO",
    )
    rotulos_ignorar = (
        "NOME DA EMPRESA",
        "NOME DA INSTITUICAO",
        "NOME DA INSTITUIÇÃO",
        "NOME DO PAGADOR",
        "DADOS DO PAGADOR",
        "PAGADOR",
        "DADOS DA CONTA DEBITADA",
        "DADOS DA CONTA DEBITADA:",
        "CONTA DEBITADA",
        "EMPRESA:",
    )

    def _cortar_candidato(candidato: str) -> str:
        candidato = re.split(r"\b(" + "|".join(bloqueios) + r")\b", candidato, maxsplit=1)[0].strip()
        candidato = re.sub(r"\s{2,}", " ", candidato).strip()
        return candidato

    # Prioridade máxima para recebedor/favorecido/beneficiario.
    for i, linha in enumerate(linhas):
        lu = sem_acento(linha).upper()
        if "PAGADOR" in lu:
            continue
        if not any(rot in lu for rot in ("RECEBEDOR", "FAVORECIDO", "BENEFICIARIO", "BENEFICIÁRIO")):
            continue

        candidato = ""
        if ":" in linha:
            candidato = linha.split(":", 1)[1].strip()
        elif "-" in linha:
            candidato = linha.split("-", 1)[1].strip()
        candidato = _cortar_candidato(candidato)
        if _candidato_parece_nome(candidato):
            debug.append("nome_recebedor")
            return normalizar_nome(candidato), debug

        if i + 1 < len(linhas):
            prox = _cortar_candidato(re.sub(r"^\d+\s+", "", linhas[i + 1]).strip())
            if _candidato_parece_nome(prox):
                debug.append("nome_recebedor")
                return normalizar_nome(prox), debug

    for i, linha in enumerate(linhas):
        lu = sem_acento(linha).upper()
        if not any(rot in lu for rot in rotulos):
            continue
        if any(rot in lu for rot in rotulos_ignorar):
            continue
        if "PAGADOR" in lu and not any(rot in lu for rot in ("RECEBEDOR", "FAVORECIDO", "BENEFICIARIO", "BENEFICIÁRIO")):
            continue

        candidato = ""
        if ":" in linha:
            candidato = linha.split(":", 1)[1].strip()
        elif "-" in linha:
            candidato = linha.split("-", 1)[1].strip()

        candidato = _cortar_candidato(candidato)
        if _candidato_parece_nome(candidato):
            debug.append("nome_linha")
            return normalizar_nome(candidato), debug

        if i + 1 < len(linhas):
            prox = linhas[i + 1].strip()
            prox = re.sub(r"^\d+\s+", "", prox)
            prox = _cortar_candidato(prox)
            if _candidato_parece_nome(prox):
                debug.append("nome_linha_seguinte")
                return normalizar_nome(prox), debug

        if i + 2 < len(linhas):
            janela = "\n".join(linhas[i + 1:i + 4])
            m = re.search(r"\b\d+\s+([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,}?)(?=\s+\d{2,4}\b|\s+CBO\b|$)", janela, re.IGNORECASE)
            if m:
                candidato = _cortar_candidato(m.group(1))
                if _candidato_parece_nome(candidato):
                    debug.append("nome_codigo")
                    return normalizar_nome(candidato), debug

    m = re.search(r"\bNOME\s*:\s*(.+?)(?:\n|CPF|VALOR|BANCO|AGENCIA|AGÊNCIA|CONTA|DATA|TIPO|INSTITUICAO|INSTITUIÇÃO|$)", normalizar_texto(texto), re.IGNORECASE | re.DOTALL)
    if m:
        candidato = _cortar_candidato(m.group(1))
        if _candidato_parece_nome(candidato):
            debug.append("nome_generico")
            return normalizar_nome(candidato), debug

    if nome_arquivo:
        nome_arquivo_norm = normalizar_nome(nome_arquivo)
        if _candidato_parece_nome(nome_arquivo_norm):
            debug.append("nome_arquivo")
            return nome_arquivo_norm, debug

    for linha in linhas[:20]:
        candidato = _cortar_candidato(re.sub(r"^\d+\s+", "", linha))
        if _candidato_parece_nome(candidato):
            debug.append("nome_fallback")
            return normalizar_nome(candidato), debug

    return None, debug


def _extrair_valor_liquido(linhas: List[str], tu: str) -> Tuple[float, List[str]]:
    debug: List[str] = []
    candidatos: List[Tuple[int, int, float, str, str]] = []

    for idx, linha in enumerate(linhas):
        rotulo_linha = _rotulo_valor_liquido(linha)
        if not rotulo_linha:
            continue

        linha_norm = sem_acento(linha).upper()
        trecho = linha
        for rotulo_base in VALOR_ROTULOS:
            rotulo_norm = sem_acento(rotulo_base).upper()
            pos = linha_norm.find(rotulo_norm)
            if pos != -1:
                trecho = linha[pos + len(rotulo_norm):]
                break

        valores = re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", trecho)
        if valores:
            valor = normalizar_valor(valores[0])
            if valor > 0:
                score = 100
                if rotulo_linha == "LIQUIDO":
                    score = 72
                if idx >= int(len(linhas) * 0.55):
                    score += 12
                if any(bloq in sem_acento(linha).upper() for bloq in ("DESCONTO", "FERIAS", "ADIANTAMENTO", "INSS", "FGTS", "IRRF", "ASSISTENCIAL")):
                    score -= 25
                if any(rot in sem_acento(linha).upper() for rot in ("VALOR", "TOTAL", "RECEBER")):
                    score += 8
                candidatos.append((score, idx, valor, rotulo_linha, "valor_liquido"))
                continue

        janela = linhas[idx + 1: idx + 5]
        for prox in janela:
            valores_prox = re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", prox)
            if valores_prox:
                valor = normalizar_valor(valores_prox[0])
                if valor > 0:
                    score = 88
                    if rotulo_linha == "LIQUIDO":
                        score = 68
                    if idx >= int(len(linhas) * 0.55):
                        score += 10
                    if any(bloq in sem_acento(linha).upper() for bloq in ("DESCONTO", "FERIAS", "ADIANTAMENTO", "INSS", "FGTS", "IRRF", "ASSISTENCIAL")):
                        score -= 25
                    if any(rot in sem_acento(linha).upper() for rot in ("VALOR", "TOTAL", "RECEBER")):
                        score += 5
                    candidatos.append((score, idx, valor, rotulo_linha, "valor_liquido_janela"))
                    break

    if candidatos:
        candidatos.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        melhor = candidatos[0]
        debug.append(melhor[4])
        debug.append(f"rotulo_{melhor[3].lower().replace(' ', '_')}")
        return melhor[2], debug

    return 0.0, debug


def _normalizar_moeda_para_float(valor_txt: str) -> float:
    return normalizar_valor(valor_txt) or 0.0


def _extrair_valor_liquido_detalhado(linhas: List[str], tu: str) -> Dict[str, Any]:
    candidatos: List[Dict[str, Any]] = []

    def _adicionar_candidato(score: float, idx: int, valor: float, metodo: str, linha: str, rotulo: str, evidencia: Dict[str, Any], aceita_zero: bool = False):
        if valor < 0:
            return
        if valor == 0 and not aceita_zero:
            return
        candidatos.append(
            {
                "score": score,
                "idx": idx,
                "valor": round(float(valor), 2),
                "metodo": metodo,
                "linha": linha,
                "rotulo": rotulo,
                "evidencia": evidencia,
            }
        )

    def _capturar_valor(texto_linha: str) -> Optional[float]:
        m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", texto_linha)
        if m:
            return _normalizar_moeda_para_float(m.group(1))
        return None

    rotulos_fortes = ("VALOR LIQUIDO", "VALOR LÍQUIDO", "LIQUIDO A RECEBER", "LÍQUIDO A RECEBER", "TOTAL LIQUIDO", "TOTAL LÍQUIDO", "VALOR A RECEBER")
    rotulos_fracos = rotulos_fortes + ("LIQUIDO", "LÍQUIDO")

    for idx, linha in enumerate(linhas):
        linha_norm = sem_acento(linha).upper()
        tem_rotulo_forte = any(sem_acento(rot).upper() in linha_norm for rot in rotulos_fortes)
        tem_rotulo_fraco = any(sem_acento(rot).upper() in linha_norm for rot in rotulos_fracos)

        if not tem_rotulo_fraco:
            continue

        valor = _capturar_valor(linha)
        if valor is not None:
            score = 96 if tem_rotulo_forte else 74
            if idx >= int(len(linhas) * 0.55):
                score += 8
            if any(bloq in linha_norm for bloq in ("DESCONTO", "FERIAS", "ADIANTAMENTO", "INSS", "FGTS", "IRRF", "ASSISTENCIAL")):
                score -= 20
            if valor == 0:
                score -= 4
            _adicionar_candidato(
                score,
                idx,
                valor,
                "valor_rotulo",
                linha,
                "valor_liquido",
                {"tipo": "valor_liquido", "metodo": "valor_rotulo", "linha": linha.strip(), "valor": valor},
                aceita_zero=tem_rotulo_forte,
            )

        for prox_idx, prox in enumerate(linhas[idx + 1: idx + 5], start=idx + 1):
            valor_prox = _capturar_valor(prox)
            if valor_prox is None:
                continue
            score = 90 if tem_rotulo_forte else 68
            if prox_idx >= int(len(linhas) * 0.55):
                score += 6
            if any(bloq in linha_norm for bloq in ("DESCONTO", "FERIAS", "ADIANTAMENTO", "INSS", "FGTS", "IRRF", "ASSISTENCIAL")):
                score -= 18
            if valor_prox == 0:
                score -= 3
            _adicionar_candidato(
                score,
                idx,
                valor_prox,
                "valor_janela",
                prox,
                "valor_liquido",
                {
                    "tipo": "valor_liquido",
                    "metodo": "valor_janela",
                    "linha": f"{linha.strip()} | {prox.strip()}",
                    "valor": valor_prox,
                },
                aceita_zero=tem_rotulo_forte,
            )
            break

    # Fallback por totais, quando o holerite vem com os campos de resumo.
    total_vencimentos = None
    total_descontos = None
    linha_venc = None
    linha_desc = None
    for linha in linhas:
        linha_norm = sem_acento(linha).upper()
        if total_vencimentos is None and any(ch in linha_norm for ch in ("TOTAL DOS VENCIMENTOS", "TOTAL VENCIMENTOS", "VENCIMENTOS")):
            valor = _capturar_valor(linha)
            if valor is not None:
                total_vencimentos = valor
                linha_venc = linha
        if total_descontos is None and any(ch in linha_norm for ch in ("TOTAL DOS DESCONTOS", "TOTAL DESCONTOS", "DESCONTOS")):
            valor = _capturar_valor(linha)
            if valor is not None:
                total_descontos = valor
                linha_desc = linha

    if total_vencimentos is not None and total_descontos is not None:
        calculado = round(max(0.0, total_vencimentos - total_descontos), 2)
        _adicionar_candidato(
            84,
            len(linhas),
            calculado,
            "total_calculado",
            f"{(linha_venc or '').strip()} | {(linha_desc or '').strip()}",
            "valor_liquido",
            {
                "tipo": "valor_liquido",
                "metodo": "total_calculado",
                "linha": f"{(linha_venc or '').strip()} | {(linha_desc or '').strip()}",
                "valor": calculado,
                "total_vencimentos": total_vencimentos,
                "total_descontos": total_descontos,
            },
            aceita_zero=True,
        )

    if candidatos:
        candidatos.sort(key=lambda item: (item["score"], item["idx"], item["valor"]), reverse=True)
        melhor = candidatos[0]
        return {
            "valor": melhor["valor"],
            "metodo": melhor["metodo"],
            "confianca": round(max(0.0, min(1.0, melhor["score"] / 100.0)), 2),
            "evidencia": melhor["evidencia"],
            "debug": [melhor["metodo"], f"rotulo_{melhor['rotulo']}"],
        }

    return {
        "valor": 0.0,
        "metodo": "nao_identificado",
        "confianca": 0.0,
        "evidencia": None,
        "debug": [],
    }


def extrair_holerite_generico(texto: str, nome_arquivo: str = "") -> Dict[str, Any]:
    linhas = _linhas_validas(texto)
    tu = "\n".join(linhas).upper()
    nome_info = _extrair_nome_holerite_detalhado(linhas, tu, nome_arquivo=nome_arquivo)
    valor_info = _extrair_valor_liquido_detalhado(linhas, tu)
    assinatura_info = extrair_assinatura_data_holerite(tu)
    debug: Dict[str, Any] = {"padroes": []}
    debug["padroes"].extend(nome_info.get("debug", []))
    debug["padroes"].extend(valor_info.get("debug", []))
    if assinatura_info.get("rotulo"):
        debug["padroes"].append(f"assinatura_{str(assinatura_info.get('rotulo')).lower().replace(' ', '_')}")

    nome = nome_info.get("nome")
    valor = float(valor_info.get("valor") or 0.0)
    assinatura_presente = bool(assinatura_info.get("assinatura"))
    data_assinatura = assinatura_info.get("data")
    local_assinatura = assinatura_info.get("modelo_assinatura") or "desconhecido"

    evidencias = []
    if nome_info.get("evidencia"):
        evidencias.append(nome_info["evidencia"])
    if valor_info.get("evidencia"):
        evidencias.append(valor_info["evidencia"])
    if assinatura_presente:
        evidencias.append(
            {
                "tipo": "assinatura",
                "presente": True,
                "rotulo": assinatura_info.get("rotulo"),
                "local": local_assinatura,
                "data": data_assinatura,
            }
        )

    pendencias = []
    if not nome:
        pendencias.append("nome_nao_identificado")
    if valor <= 0 and not (valor_info.get("evidencia") and valor_info.get("evidencia", {}).get("valor") == 0):
        pendencias.append("valor_liquido_nao_identificado")
    if not assinatura_presente:
        pendencias.append("assinatura_nao_identificada")
    if assinatura_presente and not data_assinatura:
        pendencias.append("data_nao_identificada")

    return {
        "tipo_documento": "holerite",
        "nome": normalizar_nome(nome) if nome else None,
        "nome_colaborador": normalizar_nome(nome) if nome else None,
        "metodo_nome": nome_info.get("metodo"),
        "confianca_nome": nome_info.get("confianca", 0.0),
        "evidencia_nome": nome_info.get("evidencia"),
        "empresa": "---",
        "cnpj_empresa": None,
        "competencia": extrair_competencia(tu),
        "valor_liquido": valor,
        "valor_liquido_extraido": valor,
        "metodo_valor_liquido": valor_info.get("metodo"),
        "confianca_valor_liquido": valor_info.get("confianca", 0.0),
        "evidencia_valor_liquido": valor_info.get("evidencia"),
        "data_assinatura": data_assinatura,
        "data_assinatura_extraida": data_assinatura,
        "data_recibo": data_assinatura,
        "assinatura": assinatura_presente,
        "assinatura_presente": assinatura_presente,
        "assinatura_tipo": "assinatura" if assinatura_presente else "ausente",
        "tipo_assinatura": "assinatura" if assinatura_presente else "ausente",
        "assinatura_modelo": assinatura_info.get("modelo_assinatura"),
        "local_assinatura_detectado": local_assinatura,
        "confianca_assinatura": 0.9 if assinatura_presente else 0.0,
        "evidencias": evidencias,
        "pendencias": pendencias,
        "status_final": "Aprovado" if (valor > 0 or (valor == 0 and valor_info.get("evidencia"))) and assinatura_presente and data_assinatura else "Pendente",
        "fonte": "holerite",
        "confianca": min(100, (40 if nome else 0) + (40 if (valor > 0 or (valor == 0 and valor_info.get("evidencia"))) else 0) + (10 if extrair_competencia(tu) else 0) + (10 if assinatura_presente else 0)),
        "debug": debug,
    }


def extrair_holerite_do_bloco(texto: str, nome_arquivo: str = "") -> Dict[str, Any]:
    dados = extrair_holerite_generico(texto, nome_arquivo=nome_arquivo)
    linhas = _linhas_validas(texto)
    tu = "\n".join(linhas).upper()
    cnpj = extrair_cnpj(tu)
    empresa = "---"
    if cnpj:
        for i, l in enumerate(linhas):
            if re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", l) and i > 0:
                empresa = linhas[i - 1].strip()
                break

    dados["empresa"] = empresa
    dados["cnpj_empresa"] = cnpj
    dados["confianca"] = min(100, dados.get("confianca", 0) + (10 if cnpj else 0) + (5 if empresa != "---" else 0))
    return dados


def extrair_comprovante_do_bloco(texto: str, nome_arquivo: str = "") -> Dict[str, Any]:
    debug: Dict[str, Any] = {"padroes": []}
    t = normalizar_texto(texto)
    tu = t.upper()
    banco = "Itau" if ("ITAU" in normalizar_nome(tu) or "DADOS DA CONTA CREDITADA" in tu or "COMPROVANTE DE TRANSFERENCIA" in tu) else None

    nome, debug_nome = extrair_nome_comprovante_robusto(t, nome_arquivo=nome_arquivo)
    debug["padroes"].extend(debug_nome)

    valor, debug_tag, rotulo_encontrado = _extrair_valor_proximo_de_rotulo(
        _linhas_validas(t),
        [
            "VALOR DO PAGAMENTO",
            "VALOR PAGO",
            "VALOR",
            "TRANSFERENCIA EFETUADA",
            "TRANSFERÊNCIA EFETUADA",
            "PAGAMENTO",
        ],
        janela_linhas=4,
        debug_tag="valor_linha",
    )
    if valor > 0:
        debug["padroes"].append(debug_tag or "valor_linha")
        if rotulo_encontrado:
            debug["padroes"].append(f"rotulo_{rotulo_encontrado.lower().replace(' ', '_')}")
    else:
        for c in re.findall(r"R\$\s*([\d\.\s,]+)", t, re.IGNORECASE):
            v = normalizar_valor(c)
            if v > 0:
                valor = v
                debug["padroes"].append("valor_fallback")
                break

    me = re.search(r"NOME\s+DA\s+EMPRESA\s*:\s*(.+?)(?:\n|CNPJ|CPF)", t, re.IGNORECASE)
    return {
        "nome": normalizar_nome(nome) if nome else None,
        "valor_pago": valor,
        "data_pagamento": extrair_data_pagamento(t),
        "banco": banco,
        "empresa_pagadora": me.group(1).strip() if me else None,
        "fonte": "comprovante",
        "confianca": min(100, (40 if nome else 0) + (35 if valor else 0) + (15 if extrair_data_pagamento(t) else 0) + (10 if banco else 0)),
        "debug": debug,
    }


def engine_extracao(texto: str, tipo: Optional[str] = None) -> Dict[str, Any]:
    txt = normalizar_texto(texto)
    if tipo == "holerite":
        return extrair_holerite_do_bloco(txt)
    if tipo == "comprovante":
        return extrair_comprovante_do_bloco(txt)
    tu = txt.upper()
    if "VALOR L" in tu and ("FOLHA MENSAL" in tu or "NOME DO FUNCIONARIO" in tu):
        return extrair_holerite_do_bloco(txt)
    if "COMPROVANTE" in tu or "TRANSFER" in tu or "DADOS DA CONTA CREDITADA" in tu:
        return extrair_comprovante_do_bloco(txt)
    return {"texto": txt, "confianca": 0, "debug": {"padroes": ["fallback_generico"]}}
