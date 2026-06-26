import os
import re
import unicodedata
from rapidfuzz import fuzz

from services.document_learning import aprender_documento, encontrar_layout
try:
    from services.model_rules import extrair_campos_por_modelo, empresa_parece_razao_social
except Exception:  # pragma: no cover - fallback de segurança para nao quebrar o fluxo
    def extrair_campos_por_modelo(*args, **kwargs):
        return {"modelo_id": None, "confianca": 0.0, "campos": {}, "evidencias": []}
    def empresa_parece_razao_social(nome):
        nome_limpo = limpar_nome(nome) if "limpar_nome" in globals() else str(nome or "")
        marcadores_empresa = (" LTDA", " EIRELI", " S/A", " SA ", " ME ", " EPP", " CNPJ")
        if any(m in f" {nome_limpo} " for m in marcadores_empresa):
            return True
        return False

from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.ocr import deve_chamar_ia, extrair_documento_inteligente
from utils.ocr.ocr_comprovante import extrair_texto_comprovante
from utils.ocr.ocr_comprovante import extrair_valor_comprovante_arquivo
from utils.openai.comprovante import extrair_comprovante_openai_pdf
from utils.openai.holerite import extrair_holerite_openai_pdf
from utils.signature_detection import detectar_rubricas_por_colaborador
from utils.yolo_signature_detection import (
    detectar_assinaturas_yolo,
    detectar_assinaturas_yolo_por_colaborador,
    yolo_disponivel,
)
from validators.holerite.engine_parser import (
    extrair_assinatura_data_holerite as extrair_dados_assinatura_holerite,
    extrair_comprovante_do_bloco as extrair_dados_comprovante_do_bloco,
    extrair_nome_comprovante_robusto,
    extrair_holerite_do_bloco as extrair_dados_holerite_do_bloco,
)


TERMOS_INVALIDOS_NOME = (
    "ASSINATURA",
    "FUNCIONARIO",
    "RECIBO",
    "PAGAMENTO",
    "HOLERITE",
    "DEMONSTRATIVO",
    "COMPETENCIA",
    "TOTAL",
    "LIQUIDO",
    "VENCIMENTOS",
    "DESCONTOS",
    "CNPJ",
    "CPF",
    "BANCO",
    "VALOR",
    "DATA",
    "CC",
    "GERAL",
    "CENTRO",
    "CUSTO",
    "MENSAL",
    "SALDO",
    "CONTRI",
    "CAL",
    "FAIXA",
    "MES",
    "TER",
    "IMPORTANCIA",
    "DISCRIMINADA",
    "NESTE",
    "NESTA",
    "NESTES",
    "NESTAS",
    "ASSUNTO",
    "REFERENTE",
    "RECEBI",
    "PEDIDO",
    "COMPROVANTE",
    "NOTA",
    "FISCAL",
    "EXTRATO",
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
)

PALAVRAS_LIGACAO = {"DA", "DE", "DO", "DAS", "DOS", "E"}
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
EQUIVALENCIAS_NOME = {
    "LUIS": "LUIZ",
    "LUIZ": "LUIS",
    "FELIPE": "FILIPE",
    "FILIPE": "FELIPE",
    "FILIPI": "FILIPE",
    "SOUSA": "SOUZA",
    "SOUZA": "SOUSA",
}


def sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c))


def limpar_nome(nome):
    if not nome:
        return None

    nome = sem_acento(nome).upper()
    nome = re.sub(r"[^A-Z\s]", " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    tokens = nome.split()
    while tokens and tokens[0] in {"DE", "DA", "DO", "DAS", "DOS", "A", "O"}:
        tokens.pop(0)
    while tokens and tokens[0] in PREFIXOS_RUIDO_NOME:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in PREFIXOS_RUIDO_NOME:
        tokens.pop()

    if len(nome) < 8 or len(nome.split()) < 2:
        return None
    if any(termo in tokens for termo in TERMOS_INVALIDOS_NOME):
        return None

    nome = " ".join(tokens).strip()
    if len(nome) < 8 or len(nome.split()) < 2:
        return None

    return nome


def nome_colaborador_valido(nome):
    nome_limpo = limpar_nome(nome) or ""
    if not nome_limpo:
        return False
    if nome_parece_empresa(nome_limpo):
        return False
    if " CC GERAL" in f" {nome_limpo} " or nome_limpo in {"CC GERAL", "C C GERAL"}:
        return False
    tokens = nome_limpo.split()
    if len(tokens) < 2:
        return False
    # Evita tokens muito curtos que costumam vir de ruido OCR
    if sum(1 for t in tokens if len(t) >= 3) < 2:
        return False
    return True


def extrair_nome_arquivo(path):
    nome_arquivo = os.path.splitext(os.path.basename(str(path)))[0]
    nome_arquivo = re.sub(r"^[0-9a-fA-F-]{20,}_", "", nome_arquivo)
    nome_arquivo = nome_arquivo.replace("_", " ").replace("-", " ")
    nome_arquivo = re.sub(
        r"\b(?:HOLERITE|COMPROVANTE|PAGAMENTO|PDF)\b",
        " ",
        nome_arquivo,
        flags=re.IGNORECASE,
    )
    return limpar_nome(nome_arquivo)


def extrair_nome(texto):
    if not texto:
        return None

    linhas_originais = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    for index, linha in enumerate(linhas_originais):
        if "nome do funcionario" in sem_acento(linha).lower():
            for prox in linhas_originais[index + 1:index + 4]:
                candidato = sem_acento(prox).upper()
                candidato = re.sub(r"^\d+\s+", "", candidato)
                candidato = re.split(r"\b(CBO|ADMISSAO|CPF|PIS|CARGO)\b", candidato)[0].strip()
                nome = limpar_nome(candidato)
                if nome and not nome_parece_empresa(nome):
                    return nome

    texto_sem_acento = sem_acento(texto).upper()
    padroes = [
        r"NOME\s+(?:DO\s+)?(?:FUNCIONARIO|EMPREGADO|COLABORADOR|FAVORECIDO)\s*[:\-]?\s*([A-Z\s]{8,80})",
        r"(?:FUNCIONARIO|EMPREGADO|COLABORADOR|FAVORECIDO)\s*[:\-]?\s*([A-Z\s]{8,80})",
        r"NOME\s*[:\-]?\s*([A-Z\s]{8,80})",
    ]

    for padrao in padroes:
        match = re.search(padrao, texto_sem_acento)
        if match:
            nome = limpar_nome(match.group(1))
            if nome_colaborador_valido(nome):
                return nome

    # Fallback focado em linha tabular: CODIGO + NOME + CBO
    m_tab = re.search(
        r"\b\d{2,}\s+([A-Z]{2,}(?:\s+[A-Z]{2,}){1,6})\s+\d{3,}\b",
        texto_sem_acento,
        flags=re.IGNORECASE,
    )
    if m_tab:
        nome = limpar_nome(m_tab.group(1))
        if nome_colaborador_valido(nome):
            return nome

    for linha in texto_sem_acento.splitlines():
        nome = limpar_nome(linha)
        if nome_colaborador_valido(nome):
            return nome

    return None


def normalizar_valor(valor):
    try:
        if isinstance(valor, (int, float)):
            return float(valor)
        return float(str(valor).replace(".", "").replace(",", "."))
    except Exception:
        return None


def extrair_valor(texto, tipo="documento"):
    texto_upper = sem_acento(texto).upper()
    padroes_prioritarios = []

    if tipo == "holerite":
        try:
            dados = extrair_dados_holerite_do_bloco(texto or "")
            valor_parser = dados.get("valor_liquido")
            if valor_parser is not None:
                valor_parser = float(valor_parser)
            if valor_parser is not None and (valor_parser > 0 or dados.get("evidencia_valor_liquido")):
                return valor_parser
        except Exception:
            pass

        padroes_prioritarios = [
            r"VALOR\s+LIQUIDO\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
            r"VALOR\s+L[ÍI]QUIDO\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
            r"L[ÍI]QUIDO\s+A\s+RECEBER\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
            r"TOTAL\s+L[ÍI]QUIDO\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
            r"VALOR\s+A\s+RECEBER\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
        ]
    elif tipo == "comprovante":
        padroes_prioritarios = [
            r"VALOR\s+(?:PAGO|TRANSFERIDO|DO\s+PAGAMENTO)?\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
            r"VALOR\s*R?\$?\s*([\d\.,]+)(?=\s*(?:DATA|AUTENTICA|IDENTIFICADOR|COMPROVANTE))",
            r"R\$\s*([\d\.,]+)",
        ]

    for padrao in padroes_prioritarios:
        match = re.search(padrao, texto_upper, re.DOTALL)
        if match:
            valor = normalizar_valor(match.group(1))
            if valor and valor > 0:
                return valor

    return None


def extrair_competencia(texto):
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
    texto_sem_acento = sem_acento(texto or "").upper()

    for mes, numero in meses.items():
        match = re.search(rf"\b{mes}(?:\s+DE)?\s+(\d{{4}})\b", texto_sem_acento)
        if match:
            return f"{numero}/{match.group(1)}"

    match = re.search(r"\b(0[1-9]|1[0-2])/\d{4}\b", texto or "")
    return match.group() if match else None


def normalizar_competencia(comp):
    if not comp:
        return None
    base = sem_acento(str(comp)).upper().strip()
    m = re.search(r"\b(0?[1-9]|1[0-2])[/\-](\d{4})\b", base)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    for mes, numero in {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "ABRIL": "04",
        "MAIO": "05", "JUNHO": "06", "JULHO": "07", "AGOSTO": "08",
        "SETEMBRO": "09", "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12",
    }.items():
        mm = re.search(rf"\b{mes}(?:\s+DE)?\s+(\d{{4}})\b", base)
        if mm:
            return f"{numero}/{mm.group(1)}"
    return comp


def analisar_assinatura_data(texto_bloco):
    if not texto_bloco:
        return {
            "assinatura_ok": False,
            "assinatura_detalhe": "Nao identificado",
            "data_manuscrita_ok": False,
            "data_detalhe": "Nao identificada",
        }
    info = extrair_dados_assinatura_holerite(texto_bloco or "")
    assinatura_ok = bool(info.get("assinatura"))
    data_encontrada = info.get("data")
    modelo_assinatura = info.get("modelo_assinatura")
    rotulo_assinatura = info.get("rotulo")
    data_ok = bool(data_encontrada)

    return {
        "assinatura_ok": assinatura_ok,
        "assinatura_detalhe": (
            f"Rubrica/assinatura identificada ({modelo_assinatura})"
            if assinatura_ok and modelo_assinatura
            else ("Rubrica/assinatura identificada" if assinatura_ok else "Rubrica/assinatura nao identificada")
        ),
        "data_manuscrita_ok": data_ok,
        "data_detalhe": f"Data identificada: {data_encontrada}" if data_ok else "Data proxima da assinatura nao identificada",
        "data_identificada": data_encontrada,
        "modelo_assinatura": modelo_assinatura,
        "rotulo_assinatura": rotulo_assinatura,
    }


def texto_indica_assinatura_digital(texto):
    texto_upper = sem_acento(texto or "").upper()
    termos = [
        "DOCUMENTO ASSINADO ELETRONICAMENTE",
        "ASSINADO ELETRONICAMENTE",
        "ASSINATURA DIGITAL",
        "CERTIFICADO DIGITAL",
        "RELATORIO DE ASSINATURAS",
        "STATUS ASSINADO",
        "TOKEN:",
    ]
    return any(t in texto_upper for t in termos)


def dividir_blocos_holerite(texto):
    if not texto:
        return []
    if "\f" in texto:
        paginas = [p.strip() for p in texto.split("\f") if p and len(p.strip()) > 40]
        if paginas:
            return paginas
    blocos = re.split(
        r"(?=RECIBO\s+DE\s+PAGAMENTO\s+DE\s+SALARIO|RECIBO\s+DE\s+PAGAMENTO|RECIBO\s+DE\s+SALARIO|DEMONSTRATIVO|HOLERITE|ADIANTAMENTO)",
        texto,
        flags=re.IGNORECASE,
    )
    if len([b for b in blocos if b and len(b.strip()) > 40]) <= 1:
        blocos = re.split(
            r"(?=(?:NOME\s+(?:DO\s+)?(?:FUNCIONARIO|FUNCIONÁRIO|COLABORADOR|EMPREGADO)|(?:CODIGO\s+)?NOME\s+DO\s+(?:FUNCIONARIO|FUNCIONÁRIO|COLABORADOR|EMPREGADO)))",
            texto,
            flags=re.IGNORECASE,
        )
    return [b.strip() for b in blocos if b and len(b.strip()) > 40]


def dividir_blocos_comprovante(texto):
    if not texto:
        return []
    if "\f" in texto:
        paginas = [p.strip() for p in texto.split("\f") if p and len(p.strip()) > 30]
        if paginas:
            return paginas
    blocos = re.split(
        r"(?=BANCO\s+ITAU\s*-\s*COMPROVANTE\s+DE\s+TRANSFERENCIA|DADOS\s+DA\s+CONTA\s+CREDITADA\s*:|COMPROVANTE\s+DE\s+TRANSFERENCIA|COMPROVANTE\s+PIX|COMPROVANTE\s+TED)",
        sem_acento(texto).upper(),
        flags=re.IGNORECASE,
    )
    blocos = [b.strip() for b in blocos if b and len(b.strip()) > 30]
    if len(blocos) <= 1:
        blocos = re.split(r"(?=COMPROVANTE\s+BB)", texto, flags=re.IGNORECASE)
        blocos = [b.strip() for b in blocos if b and len(b.strip()) > 30]
    return blocos


def similaridade_nomes(nome_a, nome_b):
    def _norm(txt):
        return normalizar_nome_comparacao(txt)

    def _tokens(txt):
        tokens = [t for t in _norm(txt).split() if t not in PALAVRAS_LIGACAO]
        return [EQUIVALENCIAS_NOME.get(t, t) for t in tokens]

    def _similaridade(a, b):
        if not a or not b:
            return 0.0
        try:
            return float(fuzz.ratio(a, b)) / 100.0
        except Exception:
            return 0.0

    def _token_parece_igual(token_oficial: str, token_banco: str) -> bool:
        a = EQUIVALENCIAS_NOME.get(token_oficial, token_oficial)
        b = EQUIVALENCIAS_NOME.get(token_banco, token_banco)
        if a == b:
            return True
        if len(b) == 1 and a.startswith(b):
            return True
        if len(b) >= 2 and a.startswith(b):
            return True
        if len(a) >= 3 and b.startswith(a):
            return True
        return _similaridade(a, b) >= 0.80

    a = _norm(nome_a)
    b = _norm(nome_b)
    if not a or not b:
        return 0
    if a == b:
        return 100

    tokens_a = _tokens(nome_a)
    tokens_b = _tokens(nome_b)
    if not tokens_a or not tokens_b:
        return 0

    compacto_a = "".join(tokens_a)
    compacto_b = "".join(tokens_b)
    sim_compacto = _similaridade(compacto_a, compacto_b)
    primeiro_ok = 1.0 if _token_parece_igual(tokens_a[0], tokens_b[0]) else 0.0
    primeiro_inicial_ok = 1.0 if tokens_a[0][:1] == tokens_b[0][:1] else 0.0

    if a.startswith(b) or b.startswith(a):
        return 99.0
    if sim_compacto >= 0.965:
        return 97.0

    pos = 0
    encontrados = 0
    for token_b in tokens_b:
        while pos < len(tokens_a):
            if _token_parece_igual(tokens_a[pos], token_b):
                encontrados += 1
                pos += 1
                break
            pos += 1

    cobertura_banco = encontrados / len(tokens_b)
    cobertura_oficial = encontrados / len(tokens_a)
    sim_frase = _similaridade(a, b)
    ultimo_ok = 1.0 if _token_parece_igual(tokens_a[-1], tokens_b[-1]) else 0.0

    score = 100 * (
        0.38 * cobertura_banco
        + 0.27 * cobertura_oficial
        + 0.17 * sim_frase
        + 0.12 * sim_compacto
        + 0.04 * primeiro_ok
        + 0.02 * ultimo_ok
    )

    if primeiro_ok and ultimo_ok:
        score += 0.5

    if len(tokens_b) <= 2 and len(tokens_a) >= 4 and cobertura_oficial < 0.70:
        score -= 28

    if primeiro_ok == 0:
        if primeiro_inicial_ok and sim_compacto >= 0.90:
            score -= 8
        elif sim_compacto >= 0.94 and cobertura_oficial >= 0.75:
            score -= 12
        else:
            score -= 35

    return round(max(0.0, min(score, 100.0)), 2)


def normalizar_nome_comparacao(nome):
    base = limpar_nome(nome) or ""
    if not base:
        return ""

    ruido = {
        "CBO",
        "LOCAL",
        "DEPARTAMENTO",
        "FOLHA",
        "FUNCIONARIO",
        "COLABORADOR",
        "EMPREGADO",
    }
    tokens = [t for t in base.split() if t not in ruido and len(t) > 1]
    return " ".join(tokens)


def nome_para_exibicao(nome):
    return normalizar_nome_comparacao(nome) or (limpar_nome(nome) or nome)


def resolver_nome_documento(nome_ocr, nome_arquivo=None):
    nome_ocr = nome_para_exibicao(nome_ocr)
    nome_arquivo = nome_para_exibicao(nome_arquivo)

    if nome_ocr and nome_colaborador_valido(nome_ocr):
        return nome_ocr
    if nome_arquivo and nome_colaborador_valido(nome_arquivo):
        return nome_arquivo

    return nome_ocr or nome_arquivo or None


def extrair_nome_comprovante(texto):
    if not texto:
        return None
    nome, _debug = extrair_nome_comprovante_robusto(texto)
    if nome and nome_colaborador_valido(nome):
        return nome
    return extrair_nome(texto)


def iniciais_nome(nome):
    nome_norm = normalizar_nome_comparacao(nome)
    if not nome_norm:
        return ""
    return "".join([t[0] for t in nome_norm.split() if t])


def extrair_valor_comprovante(texto):
    if not texto:
        return 0.0
    texto_base = sem_acento(texto).upper()
    linhas = [l.strip() for l in texto_base.splitlines() if l.strip()]
    anchors = (
        "VALOR",
        "VALOR DO PAGAMENTO",
        "DADOS DA TRANSACAO",
        "DADOS DE QUEM ESTA RECEBENDO",
        "FAVORECIDO",
        "BENEFICIARIO",
        "BENEFICIÁRIO",
        "TRANSFERENCIA EFETUADA",
        "TRANSFERÊNCIA EFETUADA",
        "COMPROVANTE DE TRANSFERENCIA",
        "COMPROVANTE DE TRANSFERÊNCIA",
        "PAGAMENTO",
        "PIX",
    )

    candidatos = []
    for idx, linha in enumerate(linhas):
        linha_norm = sem_acento(linha).upper()
        if not any(anchor in linha_norm for anchor in anchors):
            continue
        janela_inicio = max(0, idx - 1)
        janela_fim = min(len(linhas), idx + 4)
        janela = linhas[janela_inicio:janela_fim]
        for pos, janela_linha in enumerate(janela):
            if "0800" in janela_linha or "AGENCIA" in janela_linha or "CONTA" in janela_linha:
                continue
            for match in re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", janela_linha):
                valor = normalizar_valor(match)
                if valor <= 0:
                    continue
                score = 0
                if "VALOR" in linha_norm:
                    score += 50
                if "TRANSFERENCIA" in linha_norm:
                    score += 35
                if "PIX" in linha_norm or "PAGAMENTO" in linha_norm:
                    score += 15
                if pos == 0:
                    score += 10
                if pos <= 2:
                    score += 5
                if "R$" in janela_linha.upper():
                    score += 5
                score += min(20, len(match))
                candidatos.append((score, valor))

    if candidatos:
        candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
        melhor = candidatos[0][1]
        if melhor > 0:
            return melhor

    padroes = [
        r"\bVALOR\s*:\s*R?\$?\s*([\d\.\s,]+)",
        r"\bVALOR\s+DO\s+PAGAMENTO\s*:\s*R?\$?\s*([\d\.\s,]+)",
        r"\bTRANSFERENCIA\s+EFETUADA.*?\bR?\$?\s*([\d\.\s,]+)",
        r"R\$\s*([\d\.\s,]+)",
    ]
    for p in padroes:
        m = re.search(p, texto_base, flags=re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        valor_txt = re.sub(r"\s+", "", m.group(1))
        valor = normalizar_valor(valor_txt)
        if valor and valor > 0:
            return valor

    for linha in linhas[:30]:
        if "0800" in linha or "AGENCIA" in linha or "CONTA" in linha:
            continue
        m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", linha)
        if m:
            v = normalizar_valor(m.group(1))
            if v and v > 0:
                return v
    return extrair_valor(texto_base, "comprovante") or 0.0


def nome_parece_empresa(nome):
    return empresa_parece_razao_social(nome)


def normalizar_lista_arquivos(valor):
    if not valor:
        return []
    if isinstance(valor, (list, tuple, set)):
        return [str(item) for item in valor if item]
    return [str(valor)]


def holerite_item_incompleto(item):
    if not isinstance(item, dict):
        return True
    nome_ok = bool(item.get("nome"))
    valor_base = None
    for chave in ("valor_holerite", "valor_liquido", "valor_liquido_extraido"):
        if chave in item and item.get(chave) is not None:
            valor_base = item.get(chave)
            break
    valor_num = normalizar_valor(valor_base) if valor_base is not None else 0.0
    valor_ok = bool(valor_base is not None and (valor_num > 0 or item.get("evidencia_valor_liquido") or item.get("metodo_valor_liquido")))
    assinatura_ok = bool(item.get("assinatura_ok") or item.get("assinatura_presente") or item.get("assinatura"))
    data_ok = bool(item.get("data_manuscrita_ok") or item.get("data_assinatura") or item.get("data_identificada"))
    return not (nome_ok and valor_ok and assinatura_ok and data_ok)


def converter_item_openai_para_holerite(item, caminho_holerite, competencia_padrao=None):
    nome_arquivo = extrair_nome_arquivo(caminho_holerite)
    nome = resolver_nome_documento(item.get("nome") or item.get("nome_colaborador"), nome_arquivo)
    valor_base = None
    for chave in ("valor_liquido", "valor", "liquido"):
        if chave in item and item.get(chave) is not None:
            valor_base = item.get(chave)
            break
    valor = normalizar_valor(valor_base)
    assinatura = bool(item.get("assinatura"))
    data_assinatura = str(item.get("data_assinatura") or item.get("data") or "").strip() or None
    competencia = normalizar_competencia(item.get("competencia") or competencia_padrao)
    tipo_assinatura = str(item.get("tipo_assinatura") or ("assinatura" if assinatura else "ausente")).strip()
    confianca = float(item.get("confianca") or 0.0)
    pendencias = []
    if not nome:
        pendencias.append("nome_nao_identificado")
    if valor <= 0:
        pendencias.append("valor_liquido_nao_identificado")
    if not assinatura:
        pendencias.append("assinatura_nao_identificada")
    if assinatura and not data_assinatura:
        pendencias.append("data_nao_identificada")

    return {
        "arquivo_origem": caminho_holerite,
        "nome": nome,
        "valor_holerite": valor,
        "competencia": competencia,
        "competencia_holerite": competencia,
        "assinatura_ok": assinatura,
        "assinatura_detalhe": (
            "Rubrica/assinatura identificada via OpenAI"
            if assinatura
            else "Rubrica/assinatura nao identificada"
        ),
        "assinatura_presente": assinatura,
        "tipo_assinatura": tipo_assinatura,
        "local_assinatura_detectado": "openai_vision" if assinatura else None,
        "confianca_valor_liquido": confianca,
        "confianca_assinatura": confianca if assinatura else 0.0,
        "valor_liquido_extraido": valor,
        "data_manuscrita_ok": bool(data_assinatura),
        "data_detalhe": f"Data identificada: {data_assinatura}" if data_assinatura else "Data proxima da assinatura nao identificada",
        "data_identificada": data_assinatura,
        "data_assinatura_extraida": data_assinatura,
        "tipo_documento": "holerite",
        "nome_colaborador": nome,
        "metodo_nome": item.get("metodo_nome") or "openai",
        "confianca_nome": item.get("confianca_nome", confianca),
        "evidencia_nome": item.get("evidencia_nome"),
        "metodo_valor_liquido": item.get("metodo_valor_liquido") or "openai",
        "confianca_valor_liquido": item.get("confianca_valor_liquido", confianca),
        "evidencia_valor_liquido": item.get("evidencia_valor_liquido"),
        "evidencias": [
            {
                "tipo": "openai_fallback",
                "valor_liquido": valor,
                "assinatura": assinatura,
                "data": data_assinatura,
            }
        ],
        "pendencias": pendencias,
        "status_final": "Aprovado" if (nome and valor > 0 and assinatura and data_assinatura) else "Pendente",
        "origem_ia": "openai_holerite_fallback",
        "ia_fallback": True,
        "modelo_id": item.get("modelo_id"),
        "origem_extracao": item.get("origem_extracao") or "openai",
    }


def converter_item_local_para_holerite(caminho_holerite, dados_bloco, nome, valor, competencia_bloco, analise_ass, competencia_padrao=None):
    competencia_item = competencia_bloco or competencia_padrao
    return {
        "arquivo_origem": caminho_holerite,
        "nome": nome,
        "valor_holerite": valor or 0.0,
        "competencia": competencia_item,
        "competencia_holerite": competencia_bloco,
        "assinatura_ok": analise_ass.get("assinatura_ok", False),
        "assinatura_detalhe": analise_ass.get("assinatura_detalhe"),
        "assinatura_presente": analise_ass.get("assinatura_ok", False),
        "tipo_assinatura": analise_ass.get("modelo_assinatura") or dados_bloco.get("tipo_assinatura"),
        "local_assinatura_detectado": analise_ass.get("modelo_assinatura"),
        "metodo_nome": dados_bloco.get("metodo_nome"),
        "confianca_nome": dados_bloco.get("confianca_nome", 0.0),
        "evidencia_nome": dados_bloco.get("evidencia_nome"),
        "metodo_valor_liquido": dados_bloco.get("metodo_valor_liquido"),
        "confianca_valor_liquido": dados_bloco.get("confianca_valor_liquido", 0.0),
        "evidencia_valor_liquido": dados_bloco.get("evidencia_valor_liquido"),
        "confianca_assinatura": dados_bloco.get("confianca_assinatura", 0.0),
        "valor_liquido_extraido": dados_bloco.get("valor_liquido_extraido", valor or 0.0),
        "data_manuscrita_ok": analise_ass.get("data_manuscrita_ok", False),
        "data_detalhe": analise_ass.get("data_detalhe"),
        "data_identificada": analise_ass.get("data_identificada"),
        "data_assinatura_extraida": analise_ass.get("data_identificada"),
        "tipo_documento": dados_bloco.get("tipo_documento") or "holerite",
        "nome_colaborador": dados_bloco.get("nome_colaborador") or nome,
        "evidencias": dados_bloco.get("evidencias", []),
        "pendencias": dados_bloco.get("pendencias", []),
        "status_final": dados_bloco.get("status_final"),
        "origem_ia": "ocr_local",
        "ia_fallback": False,
        "modelo_id": dados_bloco.get("modelo_id"),
        "origem_extracao": dados_bloco.get("origem_extracao") or "ocr_local",
    }


def converter_item_openai_para_comprovante(item, caminho_comprovante, nome_arquivo=None):
    nome = resolver_nome_documento(item.get("nome") or item.get("nome_colaborador"), nome_arquivo)
    valor = normalizar_valor(item.get("valor_pago") or item.get("valor") or item.get("liquido"))
    return {
        "arquivo_origem": caminho_comprovante,
        "nome": nome,
        "valor_comprovante": valor or 0.0,
        "data_pagamento": str(item.get("data_pagamento") or item.get("data") or "").strip() or None,
        "banco": str(item.get("banco") or "").strip() or None,
        "empresa_pagadora": str(item.get("empresa_pagadora") or "").strip() or None,
        "confianca": float(item.get("confianca") or 0.0),
        "evidencias": [
            {
                "tipo": "openai_fallback",
                "nome": nome,
                "valor_comprovante": valor or 0.0,
                "data_pagamento": str(item.get("data_pagamento") or item.get("data") or "").strip() or None,
            }
        ],
        "origem_ia": "openai_comprovante_fallback",
        "ia_fallback": True,
    }


def _valor_bloco_preservando_zero(dados_bloco):
    if not isinstance(dados_bloco, dict):
        return None
    if dados_bloco.get("evidencia_valor_liquido") is not None or dados_bloco.get("metodo_valor_liquido") not in (None, "", "nao_identificado"):
        for chave in ("valor_liquido", "valor_liquido_extraido", "valor"):
            if chave in dados_bloco and dados_bloco.get(chave) is not None:
                return normalizar_valor(dados_bloco.get(chave))
    return None


def processar_holerite_comprovante(path_holerite, paths_comprovantes, competencia_esperada=None):
    print("\n[HOLERITE] ===== HOLERITE + COMPROVANTES =====")

    paths_holerite = normalizar_lista_arquivos(path_holerite)
    paths_comprovantes = normalizar_lista_arquivos(paths_comprovantes)

    if not paths_holerite:
        return {"status": "Erro", "mensagem": "Arquivo do holerite nao enviado"}
    if not paths_comprovantes:
        return {"status": "Erro", "mensagem": "Comprovante de pagamento nao enviado"}

    textos_holerite = []
    holerites_lidos = []
    texto_holerite_base = ""
    layout_conhecido = None
    confianca_layout = 0.0
    for caminho_holerite in paths_holerite:
        try:
            ocr_holerite = extrair_documento_inteligente(caminho_holerite, tipo_documento="holerite", usar_ocr=True)
            texto_holerite_item = ocr_holerite.get("texto", "")
        except Exception as exc:
            return {"status": "Erro", "mensagem": "Erro OCR holerite", "detalhe": str(exc)}

        if not texto_holerite_item:
            continue

        textos_holerite.append(texto_holerite_item)
        if not texto_holerite_base:
            texto_holerite_base = texto_holerite_item
        holerites_lidos.append(
            {
                "path": caminho_holerite,
                "texto": texto_holerite_item,
                "nome_arquivo": extrair_nome_arquivo(caminho_holerite),
                "ocr": ocr_holerite,
            }
        )

        layout_item, confianca_item = encontrar_layout("holerite", texto_holerite_item)
        if confianca_item > confianca_layout:
            layout_conhecido = layout_item
            confianca_layout = confianca_item

    if not textos_holerite:
        return {"status": "Erro", "mensagem": "Erro OCR holerite"}

    textos_comprovantes = []
    nomes_comprovante = []
    comprovantes_lidos = []

    for path in paths_comprovantes:
        try:
            ocr_comprovante = extrair_documento_inteligente(path, tipo_documento="comprovante", usar_ocr=True)
            texto = ocr_comprovante.get("texto", "")
        except Exception as exc:
            print(f"[HOLERITE] Erro OCR comprovante {path}: {exc}")
            texto = ""
            ocr_comprovante = {
                "texto": "",
                "qualidade": 0.0,
                "metodo": "falha",
                "precisa_ia": True,
                "motivo_ia": f"erro_ocr:{exc}",
            }

        if not texto:
            try:
                texto = extrair_texto_comprovante(path)
            except Exception as exc:
                print(f"[HOLERITE] Fallback OCR comprovante {path}: {exc}")
                texto = ""

        if texto:
            textos_comprovantes.append(texto)
            comprovantes_lidos.append(
                {
                    "path": path,
                    "texto": texto,
                    "nome_arquivo": extrair_nome_arquivo(path),
                    "ocr": ocr_comprovante,
                }
            )

        nome_arquivo = extrair_nome_arquivo(path)
        if nome_arquivo:
            nomes_comprovante.append(nome_arquivo)

    if not textos_comprovantes:
        return {"status": "Erro", "mensagem": "Erro OCR comprovantes"}

    texto_holerite_global = "\n".join(textos_holerite)

    holerites_extraidos = []
    vistos_holerite = set()
    houve_fallback_openai = False
    motivo_fallback_openai = ""
    melhor_modelo_regras = {
        "modelo_id": None,
        "confianca": 0.0,
        "campos": {},
        "evidencias": [],
    }

    for holerite_lido in holerites_lidos:
        caminho_holerite = holerite_lido["path"]
        texto_holerite = holerite_lido["texto"]
        nome_arquivo_holerite = holerite_lido["nome_arquivo"]
        ocr_holerite = holerite_lido.get("ocr") or {}

        if not texto_holerite:
            continue

        holerites_local = []
        for bloco in dividir_blocos_holerite(texto_holerite):
            dados_bloco = extrair_dados_holerite_do_bloco(bloco, nome_arquivo=nome_arquivo_holerite)
            resultado_modelo = extrair_campos_por_modelo(bloco, "holerite") or {}
            campos_modelo = resultado_modelo.get("campos") or {}
            confianca_modelo = float(resultado_modelo.get("confianca") or 0.0)
            modelo_id = resultado_modelo.get("modelo_id")
            if modelo_id and confianca_modelo >= float(melhor_modelo_regras.get("confianca") or 0.0):
                melhor_modelo_regras = {
                    "modelo_id": modelo_id,
                    "confianca": confianca_modelo,
                    "campos": dict(campos_modelo),
                    "evidencias": list(resultado_modelo.get("evidencias") or []),
                }

            if modelo_id:
                dados_bloco["modelo_id"] = modelo_id
                dados_bloco["confianca_modelo_regras"] = confianca_modelo
                dados_bloco["campos_modelo_regras"] = dict(campos_modelo)
                dados_bloco["modelo_regras"] = modelo_id
                if resultado_modelo.get("evidencias"):
                    dados_bloco["evidencias_modelo_regras"] = list(resultado_modelo.get("evidencias") or [])
            nome = resolver_nome_documento(
                campos_modelo.get("nome_colaborador") or dados_bloco.get("nome") or extrair_nome(bloco),
                nome_arquivo_holerite,
            )
            if campos_modelo.get("nome_colaborador"):
                dados_bloco["nome"] = campos_modelo.get("nome_colaborador")
                dados_bloco["nome_colaborador"] = campos_modelo.get("nome_colaborador")
                dados_bloco["origem_extracao"] = "modelo_regras"
            valor_modelo = None
            if campos_modelo.get("valor_liquido") is not None:
                valor_modelo = normalizar_valor(campos_modelo.get("valor_liquido"))
            valor = valor_modelo
            if valor is None:
                valor = _valor_bloco_preservando_zero(dados_bloco)
            if valor is None:
                valor = extrair_valor(bloco, "holerite")
            if valor_modelo is not None:
                dados_bloco["valor_liquido"] = valor_modelo
                dados_bloco["valor_liquido_extraido"] = valor_modelo
                dados_bloco["metodo_valor_liquido"] = "modelo_regras"
                dados_bloco["evidencia_valor_liquido"] = campos_modelo.get("valor_liquido")
                dados_bloco["origem_extracao"] = "modelo_regras"
            competencia_bloco = extrair_competencia(bloco)
            if campos_modelo.get("competencia"):
                competencia_bloco = normalizar_competencia(campos_modelo.get("competencia"))
                dados_bloco["competencia"] = competencia_bloco
                dados_bloco["competencia_holerite"] = competencia_bloco
                dados_bloco["origem_extracao"] = "modelo_regras"
            if campos_modelo.get("assinatura_regiao"):
                dados_bloco["assinatura_modelo"] = campos_modelo.get("assinatura_regiao")
            if nome and not nome_colaborador_valido(nome):
                continue
            if nome or valor:
                analise_ass = analisar_assinatura_data(bloco)
                holerites_local.append(
                    converter_item_local_para_holerite(
                        caminho_holerite,
                        dados_bloco,
                        nome,
                        valor,
                        competencia_bloco,
                        analise_ass,
                        competencia_padrao=competencia_esperada,
                    )
                )

        if not holerites_local and texto_holerite:
            dados_bloco = extrair_dados_holerite_do_bloco(texto_holerite, nome_arquivo=nome_arquivo_holerite)
            resultado_modelo = extrair_campos_por_modelo(texto_holerite, "holerite") or {}
            campos_modelo = resultado_modelo.get("campos") or {}
            confianca_modelo = float(resultado_modelo.get("confianca") or 0.0)
            modelo_id = resultado_modelo.get("modelo_id")
            if modelo_id and confianca_modelo >= float(melhor_modelo_regras.get("confianca") or 0.0):
                melhor_modelo_regras = {
                    "modelo_id": modelo_id,
                    "confianca": confianca_modelo,
                    "campos": dict(campos_modelo),
                    "evidencias": list(resultado_modelo.get("evidencias") or []),
                }
            if modelo_id:
                dados_bloco["modelo_id"] = modelo_id
                dados_bloco["confianca_modelo_regras"] = confianca_modelo
                dados_bloco["campos_modelo_regras"] = dict(campos_modelo)
                dados_bloco["modelo_regras"] = modelo_id
                if resultado_modelo.get("evidencias"):
                    dados_bloco["evidencias_modelo_regras"] = list(resultado_modelo.get("evidencias") or [])
            nome = resolver_nome_documento(
                campos_modelo.get("nome_colaborador") or dados_bloco.get("nome") or extrair_nome(texto_holerite),
                nome_arquivo_holerite,
            ) or nome_arquivo_holerite
            if campos_modelo.get("nome_colaborador"):
                dados_bloco["nome"] = campos_modelo.get("nome_colaborador")
                dados_bloco["nome_colaborador"] = campos_modelo.get("nome_colaborador")
                dados_bloco["origem_extracao"] = "modelo_regras"
            valor_modelo = None
            if campos_modelo.get("valor_liquido") is not None:
                valor_modelo = normalizar_valor(campos_modelo.get("valor_liquido"))
            valor = valor_modelo
            if valor is None:
                valor = _valor_bloco_preservando_zero(dados_bloco)
            if valor is None:
                valor = extrair_valor(texto_holerite, "holerite") or 0.0
            if valor_modelo is not None:
                dados_bloco["valor_liquido"] = valor_modelo
                dados_bloco["valor_liquido_extraido"] = valor_modelo
                dados_bloco["metodo_valor_liquido"] = "modelo_regras"
                dados_bloco["evidencia_valor_liquido"] = campos_modelo.get("valor_liquido")
                dados_bloco["origem_extracao"] = "modelo_regras"
            competencia_bloco = extrair_competencia(texto_holerite)
            if campos_modelo.get("competencia"):
                competencia_bloco = normalizar_competencia(campos_modelo.get("competencia"))
                dados_bloco["competencia"] = competencia_bloco
                dados_bloco["competencia_holerite"] = competencia_bloco
                dados_bloco["origem_extracao"] = "modelo_regras"
            if campos_modelo.get("assinatura_regiao"):
                dados_bloco["assinatura_modelo"] = campos_modelo.get("assinatura_regiao")
            analise_ass = analisar_assinatura_data(texto_holerite)
            holerites_local.append(
                converter_item_local_para_holerite(
                    caminho_holerite,
                    dados_bloco,
                    nome,
                    valor,
                    competencia_bloco,
                    analise_ass,
                    competencia_padrao=competencia_esperada,
                )
            )

        parser_local = {
            "campos": {
                "nome": any(nome_colaborador_valido(h.get("nome")) for h in holerites_local),
                "valor_liquido": any((h.get("valor_holerite") or 0) > 0 for h in holerites_local),
            },
            "inconclusivo": not holerites_local or any(holerite_item_incompleto(h) for h in holerites_local),
        }
        chamar_ia, motivo_ia = deve_chamar_ia(ocr_holerite, parser_local, tipo_documento="holerite")
        holerites_do_arquivo = holerites_local
        usou_openai_arquivo = False

        if chamar_ia:
            try:
                dados_ia = extrair_holerite_openai_pdf(
                    caminho_holerite,
                    texto_ocr=texto_holerite,
                    competencia_esperada=competencia_esperada,
                )
            except Exception as exc:
                dados_ia = {"colaboradores": [], "motivo": f"erro_openai:{exc}"}

            colaboradores_ia = dados_ia.get("colaboradores") or []
            if colaboradores_ia:
                holerites_do_arquivo = [
                    converter_item_openai_para_holerite(item, caminho_holerite, competencia_padrao=competencia_esperada)
                    for item in colaboradores_ia
                ]
                houve_fallback_openai = True
                usou_openai_arquivo = True
                motivo_fallback_openai = f"openai_holerite:{dados_ia.get('motivo')}"

        for item in holerites_do_arquivo:
            if not isinstance(item, dict):
                continue
            nome_item = item.get("nome")
            valor_item = float(item.get("valor_holerite") or 0.0)
            if nome_item and not nome_colaborador_valido(nome_item):
                continue
            if not nome_item and valor_item <= 0:
                continue
            chave_holerite = (
                limpar_nome(nome_item or "") or "",
                round(float(valor_item or 0.0), 2),
                normalizar_competencia(item.get("competencia") or competencia_esperada or "") or "",
            )
            if chave_holerite in vistos_holerite:
                continue
            vistos_holerite.add(chave_holerite)
            item["ia_fallback"] = bool(chamar_ia and usou_openai_arquivo)
            item["ia_motivo"] = motivo_fallback_openai if item["ia_fallback"] else ""
            holerites_extraidos.append(item)

    holerites_extraidos = [
        h
        for h in holerites_extraidos
        if nome_colaborador_valido(h.get("nome")) and (h.get("valor_holerite") or 0) > 0
    ] or holerites_extraidos

    comprovantes_extraidos = []
    for comprovante in comprovantes_lidos:
        texto = comprovante["texto"]
        path_comprovante = comprovante.get("path")
        nome_arquivo_bloco = comprovante.get("nome_arquivo")
        ocr_comprovante = comprovante.get("ocr") or {}
        blocos = dividir_blocos_comprovante(texto) or [texto]
        comprovantes_do_arquivo = []
        for bloco in blocos:
            dados_bloco = extrair_dados_comprovante_do_bloco(bloco, nome_arquivo=nome_arquivo_bloco)
            resultado_modelo_comp = extrair_campos_por_modelo(bloco, "comprovante") or {}
            campos_modelo_comp = resultado_modelo_comp.get("campos") or {}
            modelo_id_comp = resultado_modelo_comp.get("modelo_id")
            confianca_modelo_comp = float(resultado_modelo_comp.get("confianca") or 0.0)
            if modelo_id_comp and str(modelo_id_comp).startswith("comprovante_") and confianca_modelo_comp >= 0.35:
                dados_bloco["modelo_id"] = modelo_id_comp
                dados_bloco["confianca_modelo_regras"] = confianca_modelo_comp
                dados_bloco["campos_modelo_regras"] = dict(campos_modelo_comp)
                dados_bloco["modelo_regras"] = modelo_id_comp
                dados_bloco["origem_extracao"] = "modelo_regras"
                if resultado_modelo_comp.get("evidencias"):
                    dados_bloco["evidencias_modelo_regras"] = list(resultado_modelo_comp.get("evidencias") or [])
            valor_bloco = dados_bloco.get("valor_pago")
            if campos_modelo_comp.get("valor_comprovante") is not None:
                valor_modelo_comp = normalizar_valor(campos_modelo_comp.get("valor_comprovante"))
                if valor_modelo_comp and valor_modelo_comp > 0:
                    valor_bloco = valor_modelo_comp
                    dados_bloco["valor_pago"] = valor_modelo_comp
                    dados_bloco["valor_comprovante"] = valor_modelo_comp
                    dados_bloco["valor_origem"] = "modelo_regras"
            elif campos_modelo_comp.get("valor_liquido") is not None:
                valor_modelo_comp = normalizar_valor(campos_modelo_comp.get("valor_liquido"))
                if valor_modelo_comp and valor_modelo_comp > 0:
                    valor_bloco = valor_modelo_comp
                    dados_bloco["valor_pago"] = valor_modelo_comp
                    dados_bloco["valor_comprovante"] = valor_modelo_comp
                    dados_bloco["valor_origem"] = "modelo_regras"
            if valor_bloco is None:
                valor_bloco = extrair_valor_comprovante(bloco)
            valor_bloco = normalizar_valor(valor_bloco) or 0.0

            nome_bloco = resolver_nome_documento(
                campos_modelo_comp.get("nome_colaborador") or dados_bloco.get("nome") or extrair_nome_comprovante(bloco),
                nome_arquivo_bloco,
            )
            if campos_modelo_comp.get("nome_colaborador"):
                dados_bloco["nome"] = campos_modelo_comp.get("nome_colaborador")
                dados_bloco["nome_colaborador"] = campos_modelo_comp.get("nome_colaborador")
                dados_bloco["origem_extracao"] = "modelo_regras"

            if nome_bloco or valor_bloco > 0:
                comprovantes_do_arquivo.append(
                    {
                        "nome": nome_bloco,
                        "valor_comprovante": valor_bloco,
                        "valor_origem": dados_bloco.get("origem_extracao") or "ocr_texto",
                        "modelo_id": dados_bloco.get("modelo_id"),
                        "origem_extracao": dados_bloco.get("origem_extracao") or "ocr_texto",
                    }
                )

        valor_arquivo = extrair_valor_comprovante_arquivo(path_comprovante, texto=texto) if path_comprovante else 0.0
        parser_local = {
            "campos": {
                "nome": any(bool(item.get("nome")) for item in comprovantes_do_arquivo),
                "valor_pago": any(float(item.get("valor_comprovante", 0.0) or 0.0) > 0 for item in comprovantes_do_arquivo),
            },
            "inconclusivo": not comprovantes_do_arquivo,
        }
        chamar_ia_comp, motivo_ia_comp = deve_chamar_ia(ocr_comprovante, parser_local, tipo_documento="comprovante")
        usou_openai_comprovante = False
        if chamar_ia_comp:
            try:
                dados_ia_comp = extrair_comprovante_openai_pdf(
                    path_comprovante,
                    texto_ocr=texto,
                )
            except Exception as exc:
                dados_ia_comp = {"pagamentos": [], "motivo": f"erro_openai:{exc}"}

            pagamentos_ia = dados_ia_comp.get("pagamentos") or []
            if pagamentos_ia:
                comprovantes_do_arquivo = [
                    converter_item_openai_para_comprovante(item, path_comprovante, nome_arquivo=nome_arquivo_bloco)
                    for item in pagamentos_ia
                ]
                usou_openai_comprovante = True
                houve_fallback_openai = True
                motivo_parcial = f"openai_comprovante:{dados_ia_comp.get('motivo')}"
                motivo_fallback_openai = motivo_parcial if not motivo_fallback_openai else f"{motivo_fallback_openai} | {motivo_parcial}"

        if valor_arquivo and valor_arquivo > 0:
            if not comprovantes_do_arquivo:
                comprovantes_do_arquivo.append(
                    {
                        "nome": resolver_nome_documento(extrair_nome_comprovante(texto), nome_arquivo_bloco),
                        "valor_comprovante": valor_arquivo,
                        "valor_origem": "ocr_arquivo",
                    }
                )
            elif len(comprovantes_do_arquivo) == 1 and not usou_openai_comprovante:
                valor_texto = float(comprovantes_do_arquivo[0].get("valor_comprovante", 0.0) or 0.0)
                diferenca_relativa = abs(valor_texto - float(valor_arquivo)) / max(float(valor_arquivo), 1.0)
                if valor_texto <= 0 or diferenca_relativa >= 0.25:
                    comprovantes_do_arquivo[0]["valor_comprovante"] = valor_arquivo
                    comprovantes_do_arquivo[0]["valor_origem"] = "ocr_arquivo"
                    comprovantes_do_arquivo[0]["valor_texto"] = valor_texto
            elif len(blocos) == 1 and not usou_openai_comprovante:
                if sum(float(item.get("valor_comprovante", 0.0) or 0.0) for item in comprovantes_do_arquivo) <= 0:
                    comprovantes_do_arquivo[0]["valor_comprovante"] = valor_arquivo
                    comprovantes_do_arquivo[0]["valor_origem"] = "ocr_arquivo"

        for item_comprovante in comprovantes_do_arquivo:
            if item_comprovante.get("nome"):
                nomes_comprovante.append(item_comprovante["nome"])
            if float(item_comprovante.get("valor_comprovante", 0.0) or 0.0) > 0:
                comprovantes_extraidos.append(item_comprovante)

    valor_total_pago = sum(c.get("valor_comprovante", 0.0) for c in comprovantes_extraidos)
    nome_comprovante = nomes_comprovante[0] if nomes_comprovante else None
    competencia_holerite = holerites_extraidos[0].get("competencia_holerite")
    competencia = holerites_extraidos[0].get("competencia") or competencia_esperada

    dados_base = {
        "nome_holerite": holerites_extraidos[0].get("nome"),
        "nome_comprovante": nome_comprovante,
        "valor_holerite": holerites_extraidos[0].get("valor_holerite"),
        "valor_comprovante": valor_total_pago,
        "competencia": competencia,
        "competencia_holerite": competencia_holerite,
        "metodo_nome": holerites_extraidos[0].get("metodo_nome"),
        "confianca_nome": holerites_extraidos[0].get("confianca_nome", 0.0),
        "evidencia_nome": holerites_extraidos[0].get("evidencia_nome"),
        "metodo_valor_liquido": holerites_extraidos[0].get("metodo_valor_liquido"),
        "confianca_valor_liquido": holerites_extraidos[0].get("confianca_valor_liquido", 0.0),
        "evidencia_valor_liquido": holerites_extraidos[0].get("evidencia_valor_liquido"),
    }

    print("[HOLERITE] BASE OCR:", dados_base)

    layout_aprendido, modelo_novo = aprender_documento(
        "holerite",
        texto_holerite_global,
        {
            "nome_holerite": dados_base.get("nome_holerite"),
            "competencia": dados_base.get("competencia"),
            "valor_holerite": dados_base.get("valor_holerite"),
        },
        origem=os.path.basename(str(paths_holerite[0])),
    )

    colaboradores = []
    erros = []
    comprovantes_disponiveis = list(comprovantes_extraidos)
    auth_digital = detectar_autenticacao_digital(texto_holerite_global + "\n" + "\n".join(textos_comprovantes))
    assinatura_digital_global = texto_indica_assinatura_digital(texto_holerite_global) or auth_digital.get("assinatura_digital")
    nomes_holerite = [h.get("nome") for h in holerites_extraidos if h.get("nome")]
    rubricas_por_nome = {}
    deteccoes_yolo = []
    for caminho_holerite in paths_holerite:
        rubricas_local = detectar_rubricas_por_colaborador(caminho_holerite, nomes_holerite)
        for nome_local, info_local in (rubricas_local or {}).items():
            if info_local and info_local.get("assinatura"):
                rubricas_por_nome[nome_local] = info_local
    yolo_ok = yolo_disponivel()
    assinaturas_yolo_por_nome = {}
    if yolo_ok:
        for caminho_holerite in paths_holerite:
            deteccoes_local = detectar_assinaturas_yolo(caminho_holerite)
            deteccoes_yolo.extend(deteccoes_local or [])
            mapa_local = detectar_assinaturas_yolo_por_colaborador(
                caminho_holerite,
                nomes_holerite,
                deteccoes=deteccoes_local,
            )
            for nome_local, info_local in (mapa_local or {}).items():
                if info_local and info_local.get("assinatura"):
                    assinaturas_yolo_por_nome[nome_local] = info_local

    for hol in holerites_extraidos:
        melhor_idx = None
        melhor_score = -1
        for idx, comp in enumerate(comprovantes_disponiveis):
            score = similaridade_nomes(hol.get("nome"), comp.get("nome"))
            if score > melhor_score:
                melhor_score = score
                melhor_idx = idx

        comprovante_match = None
        nome_ok = False
        if melhor_idx is not None and melhor_score >= 75:
            comprovante_match = comprovantes_disponiveis.pop(melhor_idx)
            nome_ok = melhor_score >= 85
        elif melhor_idx is not None:
            nome_h = hol.get("nome")
            nome_c = comprovantes_disponiveis[melhor_idx].get("nome")
            ini_h = iniciais_nome(nome_h)
            ini_c = iniciais_nome(nome_c)
            if ini_h and ini_c and (ini_h.startswith(ini_c) or ini_c.startswith(ini_h)):
                comprovante_match = comprovantes_disponiveis.pop(melhor_idx)
                nome_ok = True

        # Nao permite casar apenas por valor. Match precisa ser nominal.

        valor_holerite = hol.get("valor_holerite") or 0.0
        valor_comprovante = (comprovante_match or {}).get("valor_comprovante", 0.0) or 0.0
        diferenca = valor_comprovante - valor_holerite
        valor_ok = abs(diferenca) <= 1
        nome_hol = hol.get("nome")
        rubrica_legacy = bool((rubricas_por_nome.get(nome_hol) or {}).get("assinatura"))
        rubrica_yolo_info = assinaturas_yolo_por_nome.get(nome_hol) or {}
        rubrica_yolo = bool(rubrica_yolo_info.get("assinatura"))
        rubrica_visual = bool(rubrica_legacy or rubrica_yolo)
        assinatura_final = bool(rubrica_visual or hol.get("assinatura_ok") or assinatura_digital_global)
        if rubrica_yolo:
            assinatura_tipo = "yolo"
            assinatura_status = "Rubrica (YOLO)"
        elif rubrica_legacy or hol.get("assinatura_ok"):
            assinatura_tipo = "manual/rubrica"
            assinatura_status = "Rubrica"
        elif assinatura_digital_global:
            assinatura_tipo = "digital"
            assinatura_status = "Assinado digitalmente"
        else:
            assinatura_tipo = "ausente"
            assinatura_status = "Nao assinado"

        competencia_item = hol.get("competencia") or competencia_esperada
        competencia_item_norm = normalizar_competencia(competencia_item)
        competencia_esperada_norm = normalizar_competencia(competencia_esperada)
        competencia_ok = (
            True
            if not competencia_esperada
            else bool(competencia_item_norm) and competencia_item_norm == competencia_esperada_norm
        )

        # Regra solicitada: apenas identificar existencia de data na area
        # de assinatura (sem validar ano/competencia da data).
        data_manual_ok = bool(hol.get("data_manuscrita_ok") or assinatura_digital_global)
        pendencias_holerite = [p for p in (hol.get("pendencias") or []) if not (p == "valor_liquido_nao_identificado" and valor_holerite > 0)]
        valor_liquido_extraido = valor_holerite if valor_holerite > 0 else (hol.get("valor_liquido_extraido") or 0.0)
        valor_parsed_tem_evidencia = hol.get("evidencia_valor_liquido") is not None or hol.get("metodo_valor_liquido") not in (None, "", "nao_identificado")

        if not nome_ok:
            erros.append("Nome divergente")
        if not competencia_ok:
            erros.append("Competencia divergente")
        if not valor_ok:
            erros.append("Valor divergente entre holerite e comprovante")
        if not assinatura_final:
            erros.append("Assinatura nao identificada")
        if not data_manual_ok:
            erros.append("Data nao identificada")

        colaboradores.append(
            {
                "nome": nome_para_exibicao(hol.get("nome") or (comprovante_match or {}).get("nome")),
                "nome_holerite": hol.get("nome"),
                "nome_comprovante": (comprovante_match or {}).get("nome"),
                "competencia": competencia_item,
                "competencia_holerite": hol.get("competencia_holerite"),
                "tipo_documento": hol.get("tipo_documento") or "holerite",
                "nome_colaborador": nome_para_exibicao(hol.get("nome") or (comprovante_match or {}).get("nome")),
                "assinatura": assinatura_final,
                "assinatura_presente": assinatura_final,
                "assinatura_status": assinatura_status,
                "assinatura_tipo": assinatura_tipo,
                "tipo_assinatura": hol.get("tipo_assinatura") or assinatura_tipo,
                "assinatura_modelo": hol.get("assinatura_modelo"),
                "local_assinatura_detectado": hol.get("local_assinatura_detectado"),
                "assinatura_origem": "yolo" if rubrica_yolo else ("legacy" if rubrica_legacy else ("digital" if assinatura_tipo == "digital" else "ausente")),
                "assinatura_confianca": rubrica_yolo_info.get("confianca", 0.0) if rubrica_yolo else 0.0,
                "confianca_assinatura": hol.get("confianca_assinatura", 0.0),
                "assinatura_paginas": rubrica_yolo_info.get("paginas", []) if rubrica_yolo else [],
                "metodo_nome": hol.get("metodo_nome"),
                "confianca_nome": hol.get("confianca_nome", 0.0),
                "evidencia_nome": hol.get("evidencia_nome"),
                "metodo_valor_liquido": hol.get("metodo_valor_liquido"),
                "evidencia_valor_liquido": hol.get("evidencia_valor_liquido"),
                "valor_liquido": valor_holerite,
                "valor_holerite": valor_holerite,
                "valor_liquido_extraido": valor_liquido_extraido,
                "confianca_valor_liquido": hol.get("confianca_valor_liquido", 0.0) if valor_parsed_tem_evidencia else (0.95 if valor_holerite > 0 else 0.0),
                "valor_pago": valor_comprovante,
                "valor_comprovante": valor_comprovante,
                "diferenca": diferenca,
                "valor_ok": valor_ok,
                "nome_ok": nome_ok,
                "competencia_ok": competencia_ok,
                "prazo": True,
                "prazo_status": "OK",
                "datado": "Sim" if data_manual_ok else "Nao",
                "data_assinatura_extraida": hol.get("data_assinatura_extraida"),
                "data_identificada": hol.get("data_identificada"),
                "assinatura_detalhe": (
                    "Assinado digitalmente"
                    if assinatura_tipo == "digital"
                    else hol.get("assinatura_detalhe")
                ),
                "data_detalhe": hol.get("data_detalhe") if data_manual_ok else "Data proxima da assinatura nao identificada",
                "evidencias": hol.get("evidencias", []),
                "pendencias": pendencias_holerite,
                "status_final": hol.get("status_final"),
                "modelo_id": hol.get("modelo_id"),
                "origem_extracao": hol.get("origem_extracao") or ("modelo_regras" if hol.get("modelo_id") else "ocr_local"),
            }
        )

    status_final = "Aprovado" if not erros else "Reprovado"

    resumo_financeiro = {
        "total_liquido": sum(c.get("valor_holerite", 0.0) for c in colaboradores),
        "total_pago": sum(c.get("valor_comprovante", 0.0) for c in colaboradores),
        "diferenca_total": sum(c.get("diferenca", 0.0) for c in colaboradores),
    }
    nome_holerite_topo = None
    nome_comprovante_topo = None
    for c in colaboradores:
        if not nome_holerite_topo and c.get("nome_holerite") and not nome_parece_empresa(c.get("nome_holerite")):
            nome_holerite_topo = c.get("nome_holerite")
        if not nome_comprovante_topo and c.get("nome_comprovante") and not nome_parece_empresa(c.get("nome_comprovante")):
            nome_comprovante_topo = c.get("nome_comprovante")

    return {
        "status": status_final,
        "mensagem": f"{len(colaboradores)} colaborador(es) processado(s)",
        "competencia": dados_base["competencia"],
        "competencia_holerite": dados_base["competencia_holerite"],
        "nome_holerite": nome_holerite_topo or dados_base["nome_holerite"],
        "nome_comprovante": nome_comprovante_topo or dados_base["nome_comprovante"],
        "metodo_nome": dados_base["metodo_nome"],
        "confianca_nome": dados_base["confianca_nome"],
        "evidencia_nome": dados_base["evidencia_nome"],
        "metodo_valor_liquido": dados_base["metodo_valor_liquido"],
        "confianca_valor_liquido": dados_base["confianca_valor_liquido"],
        "evidencia_valor_liquido": dados_base["evidencia_valor_liquido"],
        "valor_holerite": resumo_financeiro["total_liquido"],
        "valor_comprovante": resumo_financeiro["total_pago"],
        "diferenca": resumo_financeiro["diferenca_total"],
        "valor_ok": abs(resumo_financeiro["diferenca_total"]) <= 1,
        "empresa": "NAO IDENTIFICADA",
        "modelo_documento": (layout_conhecido or layout_aprendido).get("modelo"),
        "modelo_regras": melhor_modelo_regras.get("modelo_id"),
        "confianca_modelo_regras": round(float(melhor_modelo_regras.get("confianca") or 0.0), 2),
        "campos_modelo_regras": melhor_modelo_regras.get("campos") or {},
        "modelo_aprendido": modelo_novo,
        "confianca_modelo": round(confianca_layout, 2),
        "colaboradores": colaboradores,
        "resumo_financeiro": resumo_financeiro,
        "erros": sorted(set(erros)),
        "avisos": [],
        "ia_fallback": houve_fallback_openai,
        "ia_motivo": motivo_fallback_openai,
        "autenticacao_digital": auth_digital,
        "assinatura_yolo": {
            "modelo_disponivel": yolo_ok,
            "deteccoes_totais": len(deteccoes_yolo),
        },
    }
