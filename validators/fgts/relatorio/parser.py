import re
import unicodedata


def _texto_sem_acentos(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c))


def _normalizar_espacos(texto):
    return re.sub(r"[ \t]+", " ", texto or "").replace("\r", "")


def _valor_para_float(valor):
    if valor is None:
        return 0.0
    valor = str(valor).strip().replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return 0.0


def _extrair_valor_por_rotulo(texto, rotulos):
    texto_norm = _normalizar_espacos(texto)
    linhas = [linha.strip() for linha in texto_norm.splitlines() if linha.strip()]

    for indice, linha in enumerate(linhas):
        linha_sem_acentos = _texto_sem_acentos(linha).upper()
        if any(rotulo in linha_sem_acentos for rotulo in rotulos):
            candidatos = []

            candidatos.extend(re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", linha))
            if indice > 0:
                candidatos.extend(re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", linhas[indice - 1]))
            if indice + 1 < len(linhas):
                candidatos.extend(re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", linhas[indice + 1]))

            if candidatos:
                return candidatos[-1]

    return None


def _extrair_empresa(texto):
    padroes = [
        r"Nome\s+Empregador:\s*([^\n]+)",
        r"Empregador:\s*(?:\n|\s)+[0-9./-]*\s*Nome\s+Empregador:\s*([^\n]+)",
        r"Emitida\s+por:\s*[0-9./-]+\s*-\s*([^\n]+)",
    ]

    for padrao in padroes:
        match = re.search(padrao, texto or "", re.IGNORECASE)
        if match:
            empresa = re.sub(r"\s+", " ", match.group(1)).strip()
            empresa = re.sub(r"^\d[\d./-]*\s*", "", empresa).strip()
            if empresa:
                return empresa

    return None


def _extrair_competencia(texto):
    matches = re.findall(r"(?<!/)\b(0[1-9]|1[0-2])\s*/\s*(20\d{2})\b", texto or "")
    if matches:
        contagem = {}
        for mes, ano in matches:
            competencia = f"{mes}/{ano}"
            contagem[competencia] = contagem.get(competencia, 0) + 1
        return max(contagem, key=contagem.get)

    return None


def extrair_resumo_fgts_digital(texto):
    valor = _extrair_valor_por_rotulo(
        texto,
        [
            "TOTAL DA GUIA",
            "VALOR A RECOLHER",
            "VALOR A PAGAR",
        ],
    )

    return {
        "empresa": _extrair_empresa(texto),
        "competencia": _extrair_competencia(texto),
        "valor_total": _valor_para_float(valor),
        "valor_total_formatado": valor,
    }


def _formatar_documento(doc):
    digitos = re.sub(r"\D", "", doc or "")
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    if len(digitos) == 12:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:10]}/{digitos[10:]}"
    return doc


def extrair_colaboradores_fgts_digital(texto, tomador_alvo=None):
    linhas = [linha.strip() for linha in (texto or "").replace("\r", "").splitlines() if linha.strip()]
    tomador_busca = re.sub(r"\D", "", str(tomador_alvo or ""))
    colaboradores = []
    tomador_atual = None
    capturando = False

    for indice, linha in enumerate(linhas):
        linha_up = _texto_sem_acentos(linha).upper()

        if linha_up.startswith("TOMADOR"):
            trecho = " ".join(linhas[indice:indice + 3])
            match = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{2}\.\d{3}\.\d{5}/\d{2}", trecho)
            tomador_atual = match.group(0) if match else None
            tomador_norm = re.sub(r"\D", "", tomador_atual or "")
            capturando = bool(tomador_atual) and (not tomador_busca or tomador_busca == tomador_norm)
            continue

        if "TOTAL DO TOMADOR" in linha_up:
            capturando = False
            tomador_atual = None
            continue

        if not capturando:
            continue

        comp_match = re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", linha)
        if not comp_match or indice + 1 >= len(linhas):
            continue

        nome = linhas[indice + 1].strip()
        if not re.fullmatch(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{5,}", nome):
            continue

        valores = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", "\n".join(linhas[max(0, indice - 10):indice]))
        valor_fgts = valores[1] if len(valores) >= 2 else (valores[-1] if valores else None)

        colaboradores.append(
            {
                "nome": nome,
                "valor_fgts": _valor_para_float(valor_fgts),
                "tomador": _formatar_documento(tomador_atual),
            }
        )

    return colaboradores


def normalizar_linha(linha):
    linha = linha.upper()

    correcoes = {
        "TRABELHADORES": "TRABALHADORES",
        "TRABALHAD0RES": "TRABALHADORES",
        "TRABALHADORAS": "TRABALHADORES",
        "TEMASOR": "TOMADOR",
        "TOMASOR": "TOMADOR",
        "T0MADOR": "TOMADOR",
        "RELAÇÃO DA": "RELAÇÃO DE",
        "RELACAO DA": "RELAÇÃO DE"
    }

    for errado, correto in correcoes.items():
        linha = linha.replace(errado, correto)

    return linha


def extrair_dados_relatorio(texto, tomador_alvo=None):
    dados = {
        "empresa": None,
        "gfd": None,
        "trabalhadores": [],
        "secoes_encontradas": []
    }

    if not texto:
        return dados

    linhas = texto.replace("\r", "").split("\n")

    tomador_busca = re.sub(r"[^\d]", "", str(tomador_alvo)) if tomador_alvo else None

    capturando_bloco = False
    capturando_tabela = False
    tomador_atual = None

    competencias_encontradas = set()

    tags_obrigatorias = {
        "Relação de Categorias": "RELAÇÃO DE CATEGORIAS",
        "Relação de Tipos de Valor": "RELAÇÃO DE TIPOS DE VALOR",
        "Relação de Tomadores": "RELAÇÃO DE TOMADORES",
        "Relação de Estabelecimentos": "RELAÇÃO DE ESTABELECIMENTOS",
        "Relação de Trabalhadores": "RELAÇÃO DE TRABALHADORES"
    }

    for linha in linhas:
        l = normalizar_linha(linha.strip())

        # -----------------------------------
        # 1. SEÇÕES
        # -----------------------------------
        for chave, tag in tags_obrigatorias.items():
            if tag in l and chave not in dados["secoes_encontradas"]:
                dados["secoes_encontradas"].append(chave)

        # -----------------------------------
        # 2. EMPRESA
        # -----------------------------------
        if "NOME EMPREGADOR" in l:
            match = re.search(r"NOME EMPREGADOR[:\s]*(.*)", l)
            if match:
                dados["empresa"] = match.group(1).strip()

        # -----------------------------------
        # 3. GFD
        # -----------------------------------
        if "NÚMERO DA GUIA" in l or "NUMERO DA GUIA" in l:
            match = re.search(r"(\d{10,})", l)
            if match:
                dados["gfd"] = match.group(1)

        # -----------------------------------
        # 4. INÍCIO BLOCO
        # -----------------------------------
        if "RELAÇÃO DE TRABALHADORES" in l:
            capturando_bloco = True
            continue

        if not capturando_bloco:
            continue

        # -----------------------------------
        # 5. TOMADOR
        # -----------------------------------
        if "TOMADOR" in l:
            cno = re.sub(r"[^\d]", "", l)
            tomador_atual = cno

            if tomador_busca:
                capturando_tabela = tomador_busca in cno
            else:
                capturando_tabela = True

            continue

        # -----------------------------------
        # 6. FIM BLOCO
        # -----------------------------------
        if "TOTAL DO TOMADOR" in l:
            capturando_tabela = False
            continue

        # -----------------------------------
        # 7. EXTRAÇÃO
        # -----------------------------------
        if capturando_tabela:

            match = re.search(
                r"(0[1-9]/\d{4})\s+([A-Z\s]{10,})",
                l
            )

            if match:
                competencia = match.group(1)
                nome = match.group(2).strip()

                nome = re.split(r"(\s\d{3,}|COL)", nome)[0].strip()

                if len(nome.split()) >= 2:
                    dados["trabalhadores"].append({
                        "nome": nome,
                        "competencia": competencia,
                        "tomador": tomador_atual
                    })

                    competencias_encontradas.add(competencia)

    return {
        "empresa": dados["empresa"],
        "gfd": dados["gfd"],
        "trabalhadores": dados["trabalhadores"],
        "secoes_encontradas": dados["secoes_encontradas"],
        "competencias": list(competencias_encontradas)
    }
