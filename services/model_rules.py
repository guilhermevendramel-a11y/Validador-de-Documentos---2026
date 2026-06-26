import csv
import os
import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_MODELOS = os.path.join(PROJECT_ROOT, "data", "modelos_documentos.csv")

INVALID_NAME_TOKENS = {
    "CPF",
    "CNPJ",
    "CBO",
    "BANCO",
    "AGENCIA",
    "CONTA",
    "VALOR",
    "DADOS",
    "PAGAMENTO",
    "TRANSFERENCIA",
    "FOLHA",
    "MENSAL",
    "RECIBO",
    "DEMONSTRATIVO",
    "ASSINATURA",
    "DECLARO",
    "RECEBIDO",
    "FAVORECIDO",
    "BENEFICIARIO",
    "BENEFICIARIO",
    "RECEBENDO",
    "EMPRESA",
    "EMPREGADOR",
    "COLABORADOR",
    "FUNCIONARIO",
    "CARGO",
    "SETOR",
    "DEPARTAMENTO",
    "REFERENCIA",
    "REFERENCIAS",
    "APURACAO",
    "COMPETENCIA",
    "COMPETENCIAS",
    "LIQUIDO",
    "LIQUIDA",
    "RECEBER",
    "SALARIO",
    "BASE",
    "BASES",
    "CALC",
    "INSS",
    "FGTS",
    "IRRF",
    "DESCONTOS",
    "VENCIMENTOS",
    "EVENTOS",
    "RUBRICA",
    "SALDO",
    "CONTRI",
    "CAL",
    "FAIXA",
    "MES",
    "AJUDA",
    "CUSTO",
    "CESTA",
    "BASICA",
    "BASICO",
    "MONTADOR",
    "MOTORISTA",
    "ENCARREGADO",
    "AUXILIAR",
    "ANALISTA",
    "ASSISTENTE",
    "OPERADOR",
    "SERVENTE",
    "GERENTE",
    "SUPERVISOR",
    "COORDENADOR",
    "TECNICO",
    "UH",
    "SALDO",
    "CONTRI",
    "CAL",
    "FAIXA",
    "MES",
    "SERVICOS",
    "NOME",
    "RECEBEDOR",
    "FAVORECIDO",
    "BENEFICIARIO",
    "PAGADOR",
    "DESTINATARIO",
}

SUFIXOS_RUIDO = {"DE", "DA", "DO", "DAS", "DOS", "E", "RECEBER", "SALARIO", "PAGAMENTO", "ADIANTAMENTO", "RECIBO"}
PREFIXOS_RUIDO_NOME = {
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


def sem_acento(texto: Any) -> str:
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ASCII", "ignore").decode("ASCII")


def normalizar_texto(texto: Any) -> str:
    if texto is None:
        return ""
    txt = str(texto).replace("\r", "\n").replace("\u00a0", " ")
    txt = txt.replace("\t", " ")
    txt = re.sub(r"[ ]{2,}", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _texto_busca(texto: Any) -> str:
    txt = sem_acento(normalizar_texto(texto)).upper()
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _linhas(texto: Any) -> List[str]:
    return [linha.strip() for linha in normalizar_texto(texto).splitlines() if linha.strip()]


def _linhas_regiao(texto: Any, regiao: str) -> str:
    linhas = _linhas(texto)
    if not linhas:
        return ""

    n = len(linhas)
    regiao_norm = _texto_busca(regiao).lower()

    if regiao_norm in {"bloco_superior", "salario_superior", "holerite_salario"}:
        return "\n".join(linhas[: max(1, int(n * 0.52))])

    if regiao_norm in {"bloco_superior_rodape", "salario_rodape"}:
        inicio = int(n * 0.28)
        fim = max(inicio + 1, int(n * 0.82))
        return "\n".join(linhas[inicio:fim])

    if regiao_norm in {"bloco_superior_assinatura", "salario_assinatura"}:
        return "\n".join(linhas[: max(1, int(n * 0.52))])

    if regiao_norm in {"bloco_inferior", "adiantamento_inferior", "holerite_adiantamento"}:
        return "\n".join(linhas[int(n * 0.48):])

    if regiao_norm in {"bloco_inferior_rodape", "adiantamento_rodape"}:
        inicio = int(n * 0.82)
        return "\n".join(linhas[inicio:])

    if regiao_norm in {"bloco_inferior_assinatura", "adiantamento_assinatura"}:
        return "\n".join(linhas[int(n * 0.48):])

    if regiao_norm in {"topo", "cabecalho", "cabecalho", "superior"}:
        return "\n".join(linhas[: max(1, int(n * 0.65))])

    if regiao_norm in {"rodape", "rodape", "inferior", "baixo", "inferior_direita", "rodape_direita"}:
        return "\n".join(linhas[max(0, int(n * 0.55)):])

    if regiao_norm in {"centro", "meio"}:
        return "\n".join(linhas[max(0, int(n * 0.20)): max(1, int(n * 0.85))])

    return "\n".join(linhas)


def _split_pipe(valor: Any) -> List[str]:
    if not valor:
        return []
    return [item.strip() for item in str(valor).split("|") if item.strip()]


def _normalizar_chave(valor: Any) -> str:
    txt = sem_acento(str(valor or "")).upper()
    txt = re.sub(r"[^A-Z0-9\s]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def empresa_parece_razao_social(valor: Any) -> bool:
    nome_norm = _normalizar_chave(valor)
    if not nome_norm:
        return False
    marcadores = (
        " LTDA",
        " EIRELI",
        " S A",
        " SA ",
        " ME ",
        " EPP",
        " CNPJ",
        " CONSULTORIA ",
        " SERVICOS ",
        " SERVICO ",
        " TECNICOS ",
        " TECNICO ",
        " ENGENHARIA ",
        " COMERCIO ",
        " INDUSTRIA ",
        " CONSTRUCOES ",
        " TRANSPORTES ",
        " EMPRESA ",
        " EQUIPAMENTOS ",
        " MAQUINAS ",
        " LOCACOES ",
        " OBRAS ",
        " HIDRAULICA ",
    )
    if any(m in f" {nome_norm} " for m in marcadores):
        return True
    if len(nome_norm.split()) <= 3 and any(token in nome_norm for token in ("LTDA", "S A", "EIRELI")):
        return True
    return False


def nome_parece_empresa(nome: Any) -> bool:
    return empresa_parece_razao_social(nome)


def limpar_nome_colaborador(valor: Any) -> str:
    texto = _normalizar_chave(valor)
    if not texto:
        return ""

    texto = re.sub(r"^\d{1,6}\s+", "", texto)
    texto = re.sub(r"\b(NOME|FUNCIONARIO|FUNCIONARIO|CODIGO|CODIGO|COLABORADOR|EMPREGADO)\b", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" :-")
    tokens_brutos = [tok for tok in texto.split() if tok]
    while tokens_brutos and tokens_brutos[0] in {"DE", "DA", "DO", "DAS", "DOS", "A", "O"}:
        tokens_brutos.pop(0)
    while tokens_brutos and tokens_brutos[0] in PREFIXOS_RUIDO_NOME:
        tokens_brutos.pop(0)
    while len(tokens_brutos) > 1 and tokens_brutos[-1] in PREFIXOS_RUIDO_NOME:
        tokens_brutos.pop()
    texto = " ".join(tokens_brutos)
    tokens = [
        tok
        for tok in texto.split()
        if tok
        and tok not in INVALID_NAME_TOKENS
        and not re.search(r"\d", tok)
    ]
    while tokens and tokens[0] in SUFIXOS_RUIDO:
        tokens.pop(0)
    while tokens and tokens[0] in {"NOME", "FAVORECIDO", "BENEFICIARIO", "BENEFICIARIO", "DADOS"}:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in SUFIXOS_RUIDO:
        tokens.pop()
    texto = " ".join(tokens)
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto.split()) < 2:
        return ""
    if len(texto) < 8:
        return ""
    if any(tok in INVALID_NAME_TOKENS for tok in texto.split()):
        return ""
    if nome_parece_empresa(texto):
        return ""
    if sum(1 for t in texto.split() if len(t) >= 3) < 2:
        return ""
    return texto


def _extrair_valor(texto: Any) -> float:
    bruto = str(texto or "").strip().replace("R$", "").replace("r$", "").replace(" ", "")
    bruto = re.sub(r"[^0-9,.-]", "", bruto)
    if not bruto or bruto in {"-", ",", ".", "-,", "-."}:
        return 0.0
    if "," in bruto and "." in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    elif "," in bruto:
        bruto = bruto.replace(",", ".")
    try:
        return round(float(bruto), 2)
    except Exception:
        return 0.0


def _extrair_por_regex(texto: str, regex: str) -> Tuple[Optional[str], Optional[str]]:
    if not regex:
        return None, None
    padroes = [item.strip() for item in re.split(r"(?:\r?\n|;;)+", str(regex)) if item.strip()]
    if not padroes:
        padroes = [str(regex).strip()]
    texto_busca = _texto_busca(texto)
    for padrao in padroes:
        try:
            m = re.search(padrao, texto_busca, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            continue
        if not m:
            continue
        return m.group(0).strip(), padrao
    return None, None


def _find_label_index(linhas: List[str], labels: List[str]) -> Tuple[Optional[int], Optional[str]]:
    labels_norm = [_normalizar_chave(label) for label in labels if label]
    for idx, linha in enumerate(linhas):
        linha_norm = _normalizar_chave(linha)
        if not linha_norm:
            continue
        for label in labels_norm:
            if label and label in linha_norm:
                return idx, label
    return None, None


def _find_first_marker(linhas: List[str], markers: List[str], start: int = 0) -> Optional[int]:
    markers_norm = [_normalizar_chave(marker) for marker in markers if marker]
    for idx in range(max(0, start), len(linhas)):
        linha_norm = _normalizar_chave(linhas[idx])
        if not linha_norm:
            continue
        if any(marker and marker in linha_norm for marker in markers_norm):
            return idx
    return None


def _recortar_por_delimitadores(
    texto: Any,
    bloco_inicio: Any = None,
    bloco_fim: Any = None,
    ignorar_se_linha_contem: Any = None,
) -> str:
    linhas = _linhas(texto)
    if not linhas:
        return ""

    inicio_markers = _split_pipe(bloco_inicio)
    fim_markers = _split_pipe(bloco_fim)
    ignorar_markers = [_normalizar_chave(item) for item in _split_pipe(ignorar_se_linha_contem) if item]

    inicio_idx = 0
    if inicio_markers:
        achado = _find_first_marker(linhas, inicio_markers, 0)
        if achado is not None:
            inicio_idx = achado

    fim_idx = len(linhas)
    if fim_markers:
        achado_fim = _find_first_marker(linhas, fim_markers, inicio_idx + 1)
        if achado_fim is not None:
            fim_idx = achado_fim + 1

    recorte = linhas[inicio_idx:fim_idx]
    if ignorar_markers:
        filtrado = []
        for linha in recorte:
            linha_norm = _normalizar_chave(linha)
            if any(marker and marker in linha_norm for marker in ignorar_markers):
                continue
            filtrado.append(linha)
        recorte = filtrado

    return "\n".join(recorte)


def _extrair_nome_colaborador(
    texto: str,
    labels: List[str],
    regex: str,
    direcao_busca: str,
    max_linhas_apos_label: Optional[int] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    linhas = _linhas(texto)
    idx_label, label_encontrada = _find_label_index(linhas, labels)
    janela = texto
    trecho = ""

    if idx_label is not None:
        inicio = max(0, idx_label)
        limite = int(max_linhas_apos_label or 3)
        fim = min(len(linhas), idx_label + limite + 1)
        trecho = "\n".join(linhas[inicio:fim])
        janela = trecho
        if direcao_busca == "depois" and idx_label + 1 < len(linhas):
            candidatos = linhas[idx_label + 1: min(len(linhas), idx_label + 4)]
            for candidato in candidatos:
                nome = limpar_nome_colaborador(candidato)
                if nome:
                    return nome, {
                        "label": label_encontrada,
                        "trecho": trecho,
                        "direcao": direcao_busca,
                        "regex": regex,
                    }

    bruto, padrao = _extrair_por_regex(janela, regex)
    if bruto:
        nome = limpar_nome_colaborador(bruto)
        if nome:
            return nome, {
                "label": label_encontrada,
                "trecho": trecho or janela,
                "direcao": direcao_busca,
                "regex": padrao or regex,
            }

    for linha in linhas:
        nome = limpar_nome_colaborador(linha)
        if nome:
            return nome, {
                "label": label_encontrada,
                "trecho": linha,
                "direcao": direcao_busca,
                "regex": regex,
            }

    return None, {
        "label": label_encontrada,
        "trecho": trecho or janela[:200],
        "direcao": direcao_busca,
        "regex": regex,
    }


def _extrair_valor_liquido(
    texto: str,
    labels: List[str],
    regex: str,
    direcao_busca: str,
    max_linhas_apos_label: Optional[int] = None,
) -> Tuple[Optional[float], Dict[str, Any]]:
    linhas = _linhas(texto)
    idx_label, label_encontrada = _find_label_index(linhas, labels)
    janela = texto
    trecho = ""

    if idx_label is not None:
        inicio = max(0, idx_label - 1 if direcao_busca == "antes" else idx_label)
        limite = int(max_linhas_apos_label or 3)
        fim = min(len(linhas), idx_label + limite + 1)
        trecho = "\n".join(linhas[inicio:fim])
        janela = trecho

    bruto, padrao = _extrair_por_regex(janela, regex)
    if not bruto and idx_label is not None:
        for linha in linhas[idx_label: min(len(linhas), idx_label + int(max_linhas_apos_label or 4) + 1)]:
            m = re.search(r"(R?\$?\s*\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", linha, flags=re.IGNORECASE)
            if m:
                bruto = m.group(1)
                padrao = "valor_faixa"
                break

    if bruto:
        valor = _extrair_valor(bruto)
        if valor > 0:
            return valor, {
                "label": label_encontrada,
                "trecho": trecho or janela[:200],
                "direcao": direcao_busca,
                "regex": padrao or regex,
            }

    return None, {
        "label": label_encontrada,
        "trecho": trecho or janela[:200],
        "direcao": direcao_busca,
        "regex": regex,
    }


def _extrair_competencia(
    texto: str,
    labels: List[str],
    regex: str,
    max_linhas_apos_label: Optional[int] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    linhas = _linhas(texto)
    idx_label, label_encontrada = _find_label_index(linhas, labels)
    janela = texto
    trecho = ""
    if idx_label is not None:
        inicio = max(0, idx_label - 1)
        limite = int(max_linhas_apos_label or 3)
        fim = min(len(linhas), idx_label + limite + 1)
        trecho = "\n".join(linhas[inicio:fim])
        janela = trecho

    bruto, padrao = _extrair_por_regex(janela, regex)
    if not bruto:
        bruto, padrao = _extrair_por_regex(texto, regex)

    if bruto:
        bruto = _texto_busca(bruto)
        m = re.search(r"\b(0?[1-9]|1[0-2])\s*/\s*(20\d{2})\b", bruto)
        if m:
            return f"{int(m.group(1)):02d}/{m.group(2)}", {
                "label": label_encontrada,
                "trecho": trecho or janela[:200],
                "regex": padrao or regex,
            }
        meses = {
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
        for mes, numero in meses.items():
            mm = re.search(rf"\b{mes}\s*(?:DE\s*)?(20\d{{2}})\b", bruto)
            if mm:
                return f"{numero}/{mm.group(1)}", {
                    "label": label_encontrada,
                    "trecho": trecho or janela[:200],
                    "regex": padrao or regex,
                }

    return None, {
        "label": label_encontrada,
        "trecho": trecho or janela[:200],
        "regex": regex,
    }


def _campo_obrigatorio(valor: Any) -> bool:
    return str(valor or "").strip().upper() in {"SIM", "S", "TRUE", "1", "YES"}


@lru_cache(maxsize=8)
def carregar_modelos_documentos() -> List[Dict[str, Any]]:
    if not os.path.exists(CSV_MODELOS):
        return []

    try:
        mtime_ns = os.path.getmtime(CSV_MODELOS)
    except Exception:
        mtime_ns = 0.0
    return _carregar_modelos_documentos_por_mtime(mtime_ns)


@lru_cache(maxsize=8)
def _carregar_modelos_documentos_por_mtime(_mtime_ns: float) -> List[Dict[str, Any]]:
    if not os.path.exists(CSV_MODELOS):
        return []

    modelos: List[Dict[str, Any]] = []
    try:
        with open(CSV_MODELOS, "r", encoding="utf-8-sig", newline="") as arquivo:
            reader = csv.DictReader(arquivo, delimiter=";")
            for linha in reader:
                if not linha:
                    continue
                tipo_documento = str(linha.get("tipo_documento") or "").strip().lower()
                modelo_id = str(linha.get("modelo_id") or "").strip()
                if not tipo_documento or not modelo_id:
                    continue
                prioridade = 0
                try:
                    prioridade = int(float(linha.get("prioridade") or 0))
                except Exception:
                    prioridade = 0
                min_score = 0.0
                try:
                    min_score = float(str(linha.get("min_score_modelo") or 0).replace(",", "."))
                except Exception:
                    min_score = 0.0
                max_linhas = None
                try:
                    raw_max = str(linha.get("max_linhas_apos_label") or "").strip()
                    if raw_max:
                        max_linhas = int(float(raw_max.replace(",", ".")))
                except Exception:
                    max_linhas = None
                modelos.append({
                    "tipo_documento": tipo_documento,
                    "modelo_id": modelo_id,
                    "prioridade": prioridade,
                    "palavras_chave": str(linha.get("palavras_chave") or ""),
                    "campo": str(linha.get("campo") or ""),
                    "labels": str(linha.get("labels") or ""),
                    "regiao": str(linha.get("regiao") or ""),
                    "direcao_busca": str(linha.get("direcao_busca") or "depois"),
                    "regex": str(linha.get("regex") or ""),
                    "obrigatorio": _campo_obrigatorio(linha.get("obrigatorio")),
                    "min_score_modelo": min_score,
                    "observacao": str(linha.get("observacao") or ""),
                    "bloco_inicio": str(linha.get("bloco_inicio") or ""),
                    "bloco_fim": str(linha.get("bloco_fim") or ""),
                    "max_linhas_apos_label": max_linhas,
                    "ignorar_se_linha_contem": str(linha.get("ignorar_se_linha_contem") or ""),
                })
    except Exception:
        return []
    return modelos


def _score_modelo(modelo: Dict[str, Any], texto_busca: str) -> float:
    chaves = []
    for item in _split_pipe(modelo.get("palavras_chave")):
        chave = _normalizar_chave(item)
        if chave and chave not in chaves:
            chaves.append(chave)

    if not chaves:
        return 0.0

    encontrados = sum(1 for chave in chaves if chave and chave in texto_busca)
    score = encontrados / max(1, len(chaves))
    labels = [_normalizar_chave(item) for item in _split_pipe(modelo.get("labels")) if item]
    if labels:
        encontrados_labels = sum(1 for label in labels if label and label in texto_busca)
        score = max(score, min(1.0, encontrados_labels / max(1, len(labels)) + 0.10))
    prioridade = float(modelo.get("prioridade") or 0) / 100.0
    score = min(1.0, score + min(0.10, prioridade * 0.02))
    return round(score, 4)


def extrair_campos_por_modelo(texto: Any, tipo_documento: str = "holerite") -> Dict[str, Any]:
    texto_norm = normalizar_texto(texto)
    if not texto_norm:
        return {"modelo_id": None, "confianca": 0.0, "campos": {}, "evidencias": []}

    texto_busca = _texto_busca(texto_norm)
    modelos = [m for m in carregar_modelos_documentos() if m.get("tipo_documento") == str(tipo_documento or "").strip().lower()]
    if not modelos:
        return {"modelo_id": None, "confianca": 0.0, "campos": {}, "evidencias": []}

    melhores: Dict[str, Any] = {}
    for modelo in modelos:
        score = _score_modelo(modelo, texto_busca)
        modelo_id = modelo["modelo_id"]
        melhor = melhores.get(modelo_id)
        if not melhor or score > melhor["confianca"]:
            melhores[modelo_id] = {
                "modelo_id": modelo_id,
                "confianca": score,
                "campos": {},
                "evidencias": [],
                "_modelo": modelo,
            }

    if not melhores:
        return {"modelo_id": None, "confianca": 0.0, "campos": {}, "evidencias": []}

    melhor = max(melhores.values(), key=lambda item: (item["confianca"], item["_modelo"].get("prioridade", 0)))
    modelo = melhor["_modelo"]
    if melhor["confianca"] < float(modelo.get("min_score_modelo") or 0.0):
        return {"modelo_id": None, "confianca": round(melhor["confianca"], 4), "campos": {}, "evidencias": []}

    campos: Dict[str, Any] = {}
    evidencias: List[Dict[str, Any]] = []
    texto_modelo = _recortar_por_delimitadores(
        texto_norm,
        modelo.get("bloco_inicio"),
        modelo.get("bloco_fim"),
        modelo.get("ignorar_se_linha_contem"),
    ) or texto_norm

    for regra in sorted(
        [m for m in modelos if m.get("modelo_id") == melhor["modelo_id"]],
        key=lambda item: int(item.get("prioridade") or 0),
        reverse=True,
    ):
        campo = regra.get("campo") or ""
        regiao = regra.get("regiao") or ""
        direcao_busca = regra.get("direcao_busca") or "depois"
        regex = regra.get("regex") or ""
        labels = _split_pipe(regra.get("labels"))
        texto_regiao = _linhas_regiao(texto_modelo, regiao)
        texto_regiao = _recortar_por_delimitadores(
            texto_regiao or texto_modelo,
            regra.get("bloco_inicio") or modelo.get("bloco_inicio"),
            regra.get("bloco_fim") or modelo.get("bloco_fim"),
            regra.get("ignorar_se_linha_contem") or modelo.get("ignorar_se_linha_contem"),
        ) or texto_regiao or texto_modelo
        if not texto_regiao:
            texto_regiao = texto_modelo

        if campo == "nome_colaborador":
            valor, evidencia = _extrair_nome_colaborador(
                texto_regiao,
                labels,
                regex,
                direcao_busca,
                max_linhas_apos_label=regra.get("max_linhas_apos_label") or modelo.get("max_linhas_apos_label"),
            )
            if not valor and texto_regiao != texto_modelo:
                valor, evidencia = _extrair_nome_colaborador(
                    texto_modelo,
                    labels,
                    regex,
                    direcao_busca,
                    max_linhas_apos_label=regra.get("max_linhas_apos_label") or modelo.get("max_linhas_apos_label"),
                )
            if valor:
                campos["nome_colaborador"] = valor
            evidencia.update({"campo": campo, "regiao": regiao, "modelo_id": melhor["modelo_id"]})
            evidencias.append(evidencia)
            continue

        if campo in {"valor_liquido", "valor_comprovante"}:
            valor, evidencia = _extrair_valor_liquido(
                texto_regiao,
                labels,
                regex,
                direcao_busca,
                max_linhas_apos_label=regra.get("max_linhas_apos_label") or modelo.get("max_linhas_apos_label"),
            )
            if valor is None and texto_regiao != texto_modelo:
                valor, evidencia = _extrair_valor_liquido(
                    texto_modelo,
                    labels,
                    regex,
                    direcao_busca,
                    max_linhas_apos_label=regra.get("max_linhas_apos_label") or modelo.get("max_linhas_apos_label"),
                )
            if valor is not None:
                campos[campo] = valor
                if campo == "valor_comprovante":
                    campos.setdefault("valor_liquido", valor)
            evidencia.update({"campo": campo, "regiao": regiao, "modelo_id": melhor["modelo_id"]})
            evidencias.append(evidencia)
            continue

        if campo == "competencia":
            valor, evidencia = _extrair_competencia(
                texto_regiao,
                labels,
                regex,
                max_linhas_apos_label=regra.get("max_linhas_apos_label") or modelo.get("max_linhas_apos_label"),
            )
            if not valor and texto_regiao != texto_modelo:
                valor, evidencia = _extrair_competencia(
                    texto_modelo,
                    labels,
                    regex,
                    max_linhas_apos_label=regra.get("max_linhas_apos_label") or modelo.get("max_linhas_apos_label"),
                )
            if valor:
                campos["competencia"] = valor
            evidencia.update({"campo": campo, "regiao": regiao, "modelo_id": melhor["modelo_id"]})
            evidencias.append(evidencia)
            continue

        if campo == "assinatura":
            evidencias.append({
                "campo": campo,
                "regiao": regiao,
                "modelo_id": melhor["modelo_id"],
                "label": labels[0] if labels else None,
                "trecho": texto_regiao[:250],
                "regex": regex,
            })
            campos.setdefault("assinatura_regiao", regiao)
            continue

    resultado = {
        "modelo_id": melhor["modelo_id"],
        "confianca": round(float(melhor["confianca"]), 4),
        "campos": campos,
        "evidencias": evidencias,
    }
    return resultado
