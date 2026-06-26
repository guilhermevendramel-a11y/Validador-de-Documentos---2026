import re
import unicodedata


VALOR_RE = re.compile(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})")
CPF_RE = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")
NOME_RE = re.compile(r"\b([A-Z][A-Z'&.\-]{1,}(?:\s+[A-Z][A-Z'&.\-]{1,}){1,6})\b")

ROTULOS_NOME = (
    "NOME",
    "NOME DO COLABORADOR",
    "NOME DO FUNCIONARIO",
    "NOME DO FUNCIONARIO(A)",
    "BENEFICIARIO",
    "BENEFICIARIO(A)",
    "FAVORECIDO",
    "DESTINATARIO",
    "RECEBEDOR",
    "COLABORADOR",
    "FUNCIONARIO",
    "FUNCIONARIO(A)",
    "PAGO A",
    "PAGAMENTO A",
)

ROTULOS_VALOR = (
    "VALOR",
    "VALOR PAGO",
    "VALOR LIQUIDO",
    "VALOR LIQUIDO",
    "LIQUIDO",
    "LIQUIDO A RECEBER",
    "TOTAL",
    "TOTAL DO DOCUMENTO",
    "TOTAL GERAL",
)

BLOQUEIOS_TOKENS = {
    "LTDA",
    "LIMITADA",
    "EIRELI",
    "ME",
    "EPP",
    "SA",
    "S/A",
    "MEI",
    "EMPRESA",
    "COMERCIO",
    "SERVICO",
    "SERVICOS",
    "CONSULTORIA",
    "GESTAO",
    "ALIMENTACAO",
    "PAGAMENTO",
    "PAGAMENTOS",
    "COMPROVANTE",
    "RECIBO",
    "NOTA",
    "FISCAL",
    "PEDIDO",
    "BOLETO",
    "TRANSFERENCIA",
    "TRANSF",
    "PIX",
    "CNPJ",
    "CPF",
    "RUBRICA",
    "ASSINATURA",
    "DOCUMENTO",
    "ASSINADO",
    "DIGITAL",
    "DIGITALMENTE",
    "ELETRONICAMENTE",
    "SEM",
    "TEXTO",
    "UTIL",
    "NENHUM",
    "NAO",
    "IDENTIFICADO",
    "IDENTIFICADA",
    "SALARIO",
    "SALARIO",
    "VALOR",
    "TOTAL",
    "DATA",
    "COMPETENCIA",
    "COMPETENCIA",
    "PAGINA",
    "FOLHA",
}

BLOQUEIOS_TRECHO = (
    "NOTA FISCAL",
    "CHAVE DE ACESSO",
    "DANFE",
    "COMPROVANTE EMITIDO",
    "E-COMPROVANTE",
    "ECOMPROVANTE",
)

STOPWORDS_NOME = {
    "ASSUNTO",
    "ALIMENTACAO",
    "ANEXO",
    "AUTORIZO",
    "BANCO",
    "BOLETO",
    "COMPROVANTE",
    "CONTA",
    "CREDITO",
    "CORRENTE",
    "DEBITADA",
    "DEBITADO",
    "DECLARO",
    "DEVIDOS",
    "DOCUMENTO",
    "DEVIDOS",
    "DIAS",
    "DADOS",
    "DESCRICAO",
    "EM",
    "EMITIDO",
    "EXTRATO",
    "FINS",
    "FORNECIDAS",
    "FOLHA",
    "REGIOES",
    "METROPOLITANAS",
    "HORAS",
    "IDENTIFICACAO",
    "INFORMACOES",
    "ITAU",
    "NO",
    "NOTA",
    "PAGADOR",
    "PAGAMENTO",
    "PARA",
    "PERIODO",
    "PIX",
    "PRAZO",
    "PRODUTO",
    "RECIBO",
    "REEMBOLSO",
    "REFEICAO",
    "REFERENTE",
    "RECEBI",
    "RECEBIDO",
    "SOLUCAO",
    "SISPAG",
    "TRANSFERENCIA",
    "UTEIS",
    "VALOR",
    "VIA",
    "VALE",
    "CREDITA",
    "CREDITADA",
    "AGENCIA",
    "PESSOA JURIDICA",
    "RUA",
    "AV",
    "AVENIDA",
    "TRAVESSA",
    "ALAMEDA",
    "PRACA",
    "BLOCO",
    "NUMERO",
    "ENDERECO",
    "DEFICIENTE",
    "AUDITIVO",
}

PARTICULAS_NOME = {"DA", "DE", "DI", "DO", "DOS", "DAS", "E"}


def _remover_acentos(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _normalizar(texto):
    texto = _remover_acentos(texto).upper()
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _titulo_nome(nome):
    return " ".join(part.capitalize() for part in _normalizar(nome).split())


def _limpar_linha(linha):
    linha = _normalizar(linha)
    linha = re.sub(r"^[\-\u2022\*]+\s*", "", linha)
    return linha.strip()


def _eh_nome_pessoa(nome):
    nome = _normalizar(nome)
    if not nome:
        return False
    if any(ch.isdigit() for ch in nome):
        return False
    if any(p in nome for p in BLOQUEIOS_TRECHO):
        return False

    tokens = [t for t in re.split(r"\s+", nome) if t]
    if len(tokens) < 2 or len(tokens) > 6:
        return False
    if any(token in BLOQUEIOS_TOKENS for token in tokens):
        return False
    if any(token in STOPWORDS_NOME for token in tokens):
        return False
    if any(len(token) <= 2 and token not in PARTICULAS_NOME for token in tokens):
        return False
    tokens_validos = [token for token in tokens if token not in PARTICULAS_NOME]
    if not any(len(token) >= 4 for token in tokens_validos):
        return False
    if any(p in nome for p in ("DECLARO PARA", "QUE RECEBI", "BANCO ITAU", "DADOS DA CONTA", "CONTATE", "EM CASO", "HORAS POR DIA")):
        return False
    if sum(len(t) for t in tokens_validos) < 8:
        return False

    # Evita capturar linhas muito parecidas com cabeçalhos de documento.
    if len(tokens) <= 3 and any(t in {"VALE", "ALIMENTACAO", "PAGAMENTO", "RECIBO", "COMPROVANTE"} for t in tokens):
        return False

    return True


def _nome_ja_representado(nome, valor, colaboradores):
    nome_norm = _normalizar(nome)
    if not nome_norm:
        return True

    for item in colaboradores:
        outro_nome = _normalizar(item.get("nome"))
        if not outro_nome:
            continue
        if nome_norm == outro_nome:
            return True

        valor_outro = round(float(item.get("valor", 0.0) or 0.0), 2)
        if abs(valor_outro - round(float(valor or 0.0), 2)) > 0.1:
            continue

        if len(outro_nome.split()) > len(nome_norm.split()) and nome_norm in outro_nome:
            return True

    return False


def _deduplicar_colaboradores(colaboradores):
    saida = []

    for item in colaboradores:
        if not isinstance(item, dict):
            continue

        nome = _normalizar(item.get("nome"))
        if not nome:
            continue

        valor = round(float(item.get("valor", 0.0) or 0.0), 2)
        substituiu = False

        for idx, existente in enumerate(saida):
            nome_existente = _normalizar(existente.get("nome"))
            if not nome_existente:
                continue
            valor_existente = round(float(existente.get("valor", 0.0) or 0.0), 2)
            if abs(valor_existente - valor) > 0.1:
                continue

            if nome == nome_existente:
                substituiu = True
                break

            if len(nome.split()) > len(nome_existente.split()) and nome_existente in nome:
                saida[idx] = item
                substituiu = True
                break

            if len(nome_existente.split()) > len(nome.split()) and nome in nome_existente:
                substituiu = True
                break

        if not substituiu:
            saida.append(item)

    return saida


def _extrair_valor_texto(texto):
    valores = []
    for m in VALOR_RE.finditer(_normalizar(texto)):
        bruto = m.group(1)
        try:
            valor = float(bruto.replace(".", "").replace(",", "."))
        except Exception:
            continue
        valores.append(valor)
    return valores


def _valor_proximo(linhas, indice, janela=3):
    melhor = 0.0
    melhor_score = -1
    for offset in range(0, janela + 1):
        for pos in (indice + offset, indice - offset):
            if pos < 0 or pos >= len(linhas):
                continue
            linha = linhas[pos]
            if not linha:
                continue
            valores = _extrair_valor_texto(linha)
            if not valores:
                continue
            score_base = 10 - abs(pos - indice)
            if any(rot in linha for rot in ROTULOS_VALOR):
                score_base += 15
            if "R$" in linha:
                score_base += 5
            for valor in valores:
                if valor <= 0:
                    continue
                score = score_base
                if valor < 10:
                    score -= 2
                if valor > 50000:
                    score -= 2
                if score > melhor_score:
                    melhor_score = score
                    melhor = valor
    return round(melhor, 2) if melhor > 0 else 0.0


def _nome_apos_rotulo(linha_atual, linha_proxima=""):
    linha = _limpar_linha(linha_atual)
    if not linha:
        return ""

    candidatos = []
    base = linha
    for rotulo in ROTULOS_NOME:
        if rotulo in base:
            base = base.split(rotulo, 1)[1].strip(" :-")
            break

    for trecho in (base, linha_proxima):
        if not trecho:
            continue
        for m in NOME_RE.finditer(trecho):
            candidato = m.group(1).strip(" :-")
            if _eh_nome_pessoa(candidato):
                candidatos.append(candidato)

    if not candidatos:
        return ""

    candidatos.sort(key=lambda item: (len(item.split()), len(item)), reverse=True)
    return _titulo_nome(candidatos[0])


def _nome_em_linha_solteira(linha):
    linha = _limpar_linha(linha)
    if not linha:
        return ""
    if any(b in linha for b in BLOQUEIOS_TRECHO):
        return ""
    if any(token in linha for token in BLOQUEIOS_TOKENS):
        return ""
    if "R$" in linha or CPF_RE.search(linha):
        return ""

    candidatos = []
    for m in NOME_RE.finditer(linha):
        candidato = m.group(1).strip(" :-")
        if _eh_nome_pessoa(candidato):
            candidatos.append(candidato)

    if not candidatos:
        return ""

    # Em linhas soltas, exigimos mais contexto para evitar capturar rodapés,
    # endereços e textos institucionais como se fossem nomes de pessoas.
    candidatos_filtrados = [c for c in candidatos if len(c.split()) >= 3]
    if candidatos_filtrados:
        candidatos = candidatos_filtrados

    candidatos.sort(key=lambda item: (len(item.split()), len(item)), reverse=True)
    return _titulo_nome(candidatos[0])


def _coletar_colaboradores(linhas):
    colaboradores = []
    vistos = set()

    for idx, linha in enumerate(linhas):
        if not linha:
            continue

        linha_proxima = linhas[idx + 1] if idx + 1 < len(linhas) else ""

        nome = _nome_apos_rotulo(linha, linha_proxima)
        if not nome:
            nome = _nome_em_linha_solteira(linha)
        if not nome:
            continue

        valor = _valor_proximo(linhas, idx)
        if valor <= 0:
            # Em casos de recibo com nome claro e valor em outra linha muito proxima.
            valor = _valor_proximo(linhas, idx, janela=5)

        chave = (nome, valor)
        if chave in vistos:
            continue
        if _nome_ja_representado(nome, valor, colaboradores):
            continue
        vistos.add(chave)

        colaboradores.append(
            {
                "nome": nome,
                "valor": round(valor, 2),
                "evidencia": linha.strip(),
            }
        )

    return colaboradores


def _extrair_por_cpf(texto, linhas):
    texto_norm = _normalizar(texto)
    linhas_norm = [_normalizar(ln) for ln in linhas]
    encontrados = []
    vistos = set()

    for cpf_match in CPF_RE.finditer(texto_norm):
        inicio = cpf_match.start()
        trecho_antes = texto_norm[max(0, inicio - 240):inicio]
        trecho_depois = texto_norm[inicio:inicio + 420]

        nome = ""
        candidatos = []
        for m in NOME_RE.finditer(trecho_antes):
            cand = m.group(1).strip(" :-")
            if _eh_nome_pessoa(cand):
                candidatos.append(cand)
        if candidatos:
            candidatos.sort(key=lambda item: (len(item.split()), len(item)), reverse=True)
            nome = _titulo_nome(candidatos[0])

        if not nome:
            continue

        valor = 0.0
        for bruto in _extrair_valor_texto(trecho_depois):
            if 0 < bruto <= 50000:
                valor = round(bruto, 2)
                break

        if valor <= 0:
            # Tenta localizar o valor na linha seguinte ao CPF.
            for idx, linha in enumerate(linhas_norm):
                if cpf_match.group(0) in linha.replace(".", "").replace("-", ""):
                    valor = _valor_proximo(linhas_norm, idx, janela=4)
                    break

        if valor <= 0:
            continue

        chave = (nome, valor)
        if chave in vistos:
            continue
        if _nome_ja_representado(nome, valor, encontrados):
            continue
        vistos.add(chave)
        encontrados.append({"nome": nome, "valor": valor, "evidencia": "CPF"})

    return encontrados


def _extrair_total_documento(texto):
    texto_norm = _normalizar(texto)
    candidatos = []

    for m in VALOR_RE.finditer(texto_norm):
        valor = 0.0
        try:
            valor = float(m.group(1).replace(".", "").replace(",", "."))
        except Exception:
            continue
        trecho = texto_norm[max(0, m.start() - 80):m.start() + 60]
        peso = 1
        if any(rot in trecho for rot in ("TOTAL GERAL", "TOTAL DO DOCUMENTO", "TOTAL", "SALDO FINAL")):
            peso = 4
        elif any(rot in trecho for rot in ("VALOR LIQUIDO", "LIQUIDO A RECEBER", "VALOR PAGO", "PAGAMENTO")):
            peso = 3
        candidatos.append((peso, valor))

    if not candidatos:
        return 0.0

    candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return round(candidatos[0][1], 2)


def extrair_dados_va(texto_completo):
    resultado = {
        "colaboradores": [],
        "colaboradores_detalhados": [],
        "soma_extraida": 0.0,
        "total_documento": 0.0,
    }

    if not texto_completo:
        return resultado

    linhas = [str(ln or "").strip() for ln in re.split(r"[\r\n]+", texto_completo) if str(ln or "").strip()]
    linhas_norm = [_limpar_linha(ln) for ln in linhas]
    texto_norm = _normalizar(texto_completo)

    colaboradores = []
    vistos = set()

    # 1. Estruturas com nome + valor em linha ou linhas proximas.
    for candidato in _coletar_colaboradores(linhas_norm):
        nome = candidato.get("nome", "")
        valor = round(float(candidato.get("valor", 0.0) or 0.0), 2)
        if not nome:
            continue
        chave = (nome, valor)
        if chave in vistos:
            continue
        vistos.add(chave)
        colaboradores.append(candidato)

    # 2. Documentos com CPF: usa o CPF como apoio para achar nome e valor.
    for candidato in _extrair_por_cpf(texto_completo, linhas_norm):
        chave = (candidato["nome"], candidato["valor"])
        if chave in vistos:
            continue
        vistos.add(chave)
        colaboradores.append(candidato)

    # 3. Se ainda nao encontrou nada, tenta nomes soltos com valor proximo.
    if not colaboradores:
        for idx, linha in enumerate(linhas_norm):
            nome = _nome_em_linha_solteira(linha)
            if not nome:
                continue
            valor = _valor_proximo(linhas_norm, idx, janela=4)
            chave = (nome, valor)
            if chave in vistos:
                continue
            if _nome_ja_representado(nome, valor, colaboradores):
                continue
            vistos.add(chave)
            colaboradores.append(
                {
                    "nome": nome,
                    "valor": round(valor, 2),
                    "evidencia": linha,
                }
            )

    colaboradores = _deduplicar_colaboradores(colaboradores)
    resultado["colaboradores_detalhados"] = colaboradores
    resultado["colaboradores"] = [{"nome": item.get("nome", "")} for item in colaboradores if item.get("nome")]
    resultado["soma_extraida"] = round(sum(float(c.get("valor", 0.0) or 0.0) for c in colaboradores), 2)

    total_documento = _extrair_total_documento(texto_norm)
    if total_documento <= 0 and resultado["soma_extraida"] > 0:
        total_documento = resultado["soma_extraida"]
    resultado["total_documento"] = round(total_documento, 2)

    return resultado
