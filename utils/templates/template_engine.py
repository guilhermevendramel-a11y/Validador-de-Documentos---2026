import os
import json
import re

# ==========================================================
# 🔥 CONFIGURAÇÃO DE CAMINHOS
# ==========================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates", "cartao_ponto")

# ==========================================================
# 📦 CARREGAR TEMPLATES
# ==========================================================
def carregar_templates():
    templates = []

    if not os.path.exists(TEMPLATE_DIR):
        return []

    for arquivo in os.listdir(TEMPLATE_DIR):
        if not arquivo.endswith(".json"):
            continue

        caminho = os.path.join(TEMPLATE_DIR, arquivo)

        try:
            with open(caminho, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["__arquivo__"] = arquivo
                templates.append(data)
        except Exception as e:
            print(f"⚠️ Erro ao carregar template {arquivo}: {e}")

    return templates

# ==========================================================
# 🔍 DETECTAR TEMPLATE (ROBUSTO)
# ==========================================================
def detectar_template(texto):
    templates = carregar_templates()
    melhor_template = None
    melhor_score = 0

    texto_upper = texto.upper()

    for template in templates:
        palavras = template.get("identificacao", {}).get("palavras_chave", [])

        score = 0

        for p in palavras:
            if re.search(rf"\b{re.escape(p.upper())}\b", texto_upper):
                score += 3  # peso maior

        # penaliza templates fracos
        if len(palavras) < 3:
            score -= 2

        print(f"📄 Template: {template.get('__arquivo__')} | Score: {score}")

        if score > melhor_score:
            melhor_score = score
            melhor_template = template

    # exige mínimo de confiança
    if melhor_score < 3:
        return None

    return melhor_template

# ==========================================================
# 🧠 SEPARAR DOCUMENTO POR FUNCIONÁRIO
# ==========================================================
def separar_blocos(texto):
    partes = texto.upper().split("FOLHA DE PONTO INDIVIDUAL DE TRABALHO")

    blocos = []

    for parte in partes:
        parte = parte.strip()

        if len(parte) < 100:
            continue

        # adiciona o header de volta
        bloco = "FOLHA DE PONTO INDIVIDUAL DE TRABALHO\n" + parte
        blocos.append(bloco)

    return blocos

# ==========================================================
# 🧹 LIMPEZA DE VALORES
# ==========================================================
def limpar_valor(valor):
    valor = re.sub(r"[|\\/_]", " ", valor)
    valor = re.sub(r"\s+", " ", valor)
    return valor.strip()

# ==========================================================
# 🔍 EXTRAÇÃO DE CAMPOS
# ==========================================================
def extrair_campos_template(texto, template):
    if not template:
        return {}

    resultado = {}
    campos = template.get("campos", {})
    texto_upper = texto.upper()

    # Import seguro
    try:
        from validators.cartao_ponto.engine_parser import nome_valido
    except ImportError:
        try:
            from utils.validators.cartao_ponto.engine_parser import nome_valido
        except ImportError:
            def nome_valido(n): return len(n.split()) >= 2

    for campo, regra in campos.items():
        regex = regra.get("regex")

        if not regex:
            resultado[campo] = None
            continue

        try:
            matches = re.findall(regex, texto_upper, re.IGNORECASE | re.MULTILINE)

            if not matches:
                resultado[campo] = None
                continue

            # ==================================================
            # 🧠 NOME (SUPER PROTEGIDO)
            # ==================================================
            if "nome" in campo.lower():
                nomes_validos = []

                for m in matches:
                    nome = " ".join(m) if isinstance(m, tuple) else m
                    nome = limpar_valor(nome)

                    nome = re.sub(
                        r"(SAL[ÁA]RIO|BASE|R\$|FUN[ÇC][ÃA]O|CARGO)",
                        "",
                        nome,
                        flags=re.IGNORECASE
                    ).strip()

                    # bloqueio de lixo
                    if any(x in nome.upper() for x in [
                        "FOLHA", "PONTO", "EMPRESA", "CNPJ", "HORAS", "TOTAL"
                    ]):
                        continue

                    if nome_valido(nome) and 2 <= len(nome.split()) <= 5:
                        nomes_validos.append(nome.title())

                if nomes_validos:
                    resultado[campo] = max(nomes_validos, key=lambda n: len(n.split()))
                else:
                    resultado[campo] = None

            # ==================================================
            # 📅 COMPETÊNCIA
            # ==================================================
            elif "competencia" in campo.lower():
                valor = matches[0]
                valor = " ".join(valor) if isinstance(valor, tuple) else valor

                valor = limpar_valor(valor)

                digitos = re.sub(r"[^0-9]", "", valor)

                if len(digitos) == 6:
                    resultado[campo] = f"{digitos[:2]}/{digitos[2:]}"
                else:
                    resultado[campo] = valor.replace(" ", "/")

            # ==================================================
            # 📌 OUTROS CAMPOS
            # ==================================================
            else:
                valor = matches[0]
                valor = " ".join(valor) if isinstance(valor, tuple) else valor
                resultado[campo] = limpar_valor(valor)

        except Exception as e:
            print(f"⚠️ Erro regex no campo {campo}: {e}")
            resultado[campo] = None

    return resultado

# ==========================================================
# 🚀 EXTRAÇÃO COMPLETA
# ==========================================================
def extrair_documento_completo(texto):
    if not texto:
        return []

    texto_upper = texto.upper()

    # ignora páginas de assinatura
    if "RELATÓRIO DE ASSINATURAS" in texto_upper:
        return []

    template = detectar_template(texto)

    if not template:
        print("⚠️ Nenhum template detectado")
        return []

    blocos = separar_blocos(texto)

    resultados = []
    nomes_vistos = set()

    for bloco in blocos:
        dados = extrair_campos_template(bloco, template)

        nome = dados.get("nome")

        if nome and nome not in nomes_vistos:
            nomes_vistos.add(nome)

            if any(v for v in dados.values()):
                resultados.append(dados)

    return resultados

# ==========================================================
# 🧠 EXTRAÇÃO POR PADRÃO HUMANO
# ==========================================================
def extrair_nomes_por_padrao(texto):
    candidatos = []

    linhas = texto.split("\n")

    for linha in linhas:
        linha = linha.strip()

        if not linha:
            continue

        linha_upper = linha.upper()

        # ❌ ignora lixo
        if any(x in linha_upper for x in [
            "FOLHA", "PONTO", "EMPRESA", "CNPJ",
            "HORAS", "TOTAL", "SALARIO", "FUNCAO",
            "DATA", "MES", "ANO"
        ]):
            continue

        # ❌ ignora números
        if re.search(r"\d", linha):
            continue

        # ❌ tamanho inválido
        if len(linha) < 5 or len(linha) > 60:
            continue

        palavras = linha.split()

        # ✔️ padrão nome humano
        if 2 <= len(palavras) <= 5 and all(len(p) >= 3 for p in palavras):
            candidatos.append(linha.title())

    return candidatos    


def extrair_espelho_ponto_eletronico(texto):
    if not texto:
        return []

    texto_upper = texto.upper()
    if "ESPELHO DE PONTO ELETR" not in texto_upper:
        return []

    nome = None
    nome_match = re.search(
        r"(?:^|\n)\s*Nome\s*\n\s*([A-ZÀ-Úa-zà-ú' ]{5,80})\s*\n\s*(?:PIS|CPF|Cargo|Matr[íi]cula)",
        texto,
        re.IGNORECASE,
    )
    if nome_match:
        nome = limpar_valor(nome_match.group(1)).title()

    competencia = None
    periodo_match = re.search(
        r"\bDe\s+(\d{2})/(\d{2})/(\d{4})\s+at[ée]\s+(\d{2})/(\d{2})/(\d{4})",
        texto,
        re.IGNORECASE,
    )
    if periodo_match:
        competencia = f"{periodo_match.group(2)}/{periodo_match.group(3)}"

    horarios = re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", texto)
    horarios_validos = [h for h in horarios if h != "00:00"]

    dias_com_marcacao = set()
    for match in re.finditer(r"(?:Seg|Ter|Qua|Qui|Sex|S[áa]b|Dom),\s*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE):
        trecho_dia = texto[match.end():match.end() + 180]
        horarios_dia = re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", trecho_dia)
        if any(h != "00:00" for h in horarios_dia):
            dias_com_marcacao.add(match.group(1))

    if not nome:
        return []

    return [{
        "nome": nome,
        "competencia": competencia,
        "assinatura": False,
        "datado": bool(re.search(r"\b\d{2}/\d{2}/\d{4}\b", texto)),
        "marcacoes": len(horarios_validos) >= 4,
        "dias_trabalhados": len(dias_com_marcacao),
        "horas_total": max(len(horarios_validos) / 2, 0),
    }]


def _normalizar_competencia_secullum(texto):
    match = re.search(
        r"\bD[ÉE][\^\.\s:]*([0-3]?\d)\D+([01]?\d)\D+(\d{2,4})\s+A[TÍIÉE][\s\.\-:]*([0-3]?\d)\D+([01]?\d)\D+(\d{2,4})",
        texto,
        re.IGNORECASE,
    )
    if not match:
        return None

    dia_ini, mes_ini, ano_ini, _dia_fim, _mes_fim, ano_fim = match.groups()
    ano = ano_fim if len(ano_fim) == 4 else f"20{ano_fim}"
    mes = mes_ini.zfill(2)
    return f"{mes}/{ano}"


def _linha_nome_secullum(linhas):
    bloqueios = [
        "EMPRESA", "CNPJ", "INSCRI", "NOME", "FOLHA", "CTPS", "FUNÇÃO",
        "FUNCAO", "DEPARTAMENTO", "OBS", "HORÁRIO", "HORARIO", "TRABALHO",
        "OTMIX", "CONSTRU", "INDUSTRIAIS", "EIRELI", "OBRA", "PONTO",
        "SECULLUM", "SISTEMA", "PÁGINA", "PAGINA", "EMITIDO", "PIS",
        "PASEP", "ADMISS", "DESCRIÇÃO", "DESCRICAO", "JUSTIFICATIVA",
        "TOTAIS", "LEGENDA", "ATÉ", "ATE", "DATA", "HORA", "OCORR",
        "SOLDADOR", "ALMOXARIFE", "AJUDANTE", "ENCANADOR", "PEDREIRO",
        "MECÂNICO", "MECANICO", "TÉC.", "TECNICO", "SEGURANÇA",
    ]

    for linha in linhas:
        limpa = limpar_valor(linha)
        upper = limpa.upper()

        if not limpa or len(limpa) < 8 or len(limpa) > 80:
            continue
        if re.search(r"\d", limpa):
            continue
        if any(b in upper for b in bloqueios):
            continue

        palavras = limpa.split()
        if 2 <= len(palavras) <= 6 and sum(p[:1].isalpha() for p in palavras) == len(palavras):
            return limpa.title()

    return None


def extrair_secullum_cartao_ponto(texto):
    if not texto:
        return []

    texto_upper = texto.upper()
    if "SECULLUM" not in texto_upper and "CARTÃO PONTO" not in texto_upper and "CARTAO PONTO" not in texto_upper:
        return []

    blocos = re.split(r"(?=CART[ÃA]O PONTO|§+\s*Ponto\s+Sec|W\s+Ponto\s+Sec|Ponto\s+Secullum)", texto, flags=re.IGNORECASE)
    resultados = []
    nomes_vistos = set()

    for bloco in blocos:
        if len(bloco.strip()) < 250:
            continue
        if "SECULLUM" not in bloco.upper() and "CART" not in bloco.upper():
            continue

        linhas = [l.strip() for l in bloco.splitlines() if l.strip()]
        nome = None

        nome_direto = re.search(
            r"(?:^|\n)\s*Nome\s*\n\s*([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú ]{6,80})\s*\n",
            bloco,
            re.IGNORECASE,
        )
        if nome_direto:
            candidato = limpar_valor(nome_direto.group(1))
            if not any(x in candidato.upper() for x in ["NO FOLHA", "CTPS", "FUNÇÃO", "FUNCAO"]):
                nome = candidato.title()

        if not nome:
            nome = _linha_nome_secullum(linhas)

        if not nome or nome.lower() in nomes_vistos:
            continue

        nomes_vistos.add(nome.lower())
        horarios = re.findall(r"\b(?:[01]?\d|2[0-3])\s*[:;]\s*[0-5]\d\b", bloco)
        horarios_validos = [h for h in horarios if re.sub(r"\s", "", h) not in {"00:00", "0:00"}]

        resultados.append({
            "nome": nome,
            "competencia": _normalizar_competencia_secullum(bloco),
            "assinatura": bool(re.search(r"\b(?:ASSINADO|ASSINATURA)\b", bloco, re.IGNORECASE)),
            "verificar_assinatura_visual": True,
            "datado": bool(re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", bloco)),
            "marcacoes": len(horarios_validos) >= 4,
        })

    return resultados


def _linha_nome_folha_individual(linha):
    upper = linha.upper()
    bloqueios = [
        "EMPREGADOR", "EMPRESA", "CEI/CNPJ", "CNPJ", "ENDERE", "LOGRADOURO",
        "BAIRRO", "DISTRITO", "CIDADE", "UF", "EMPREGADO", "CTPS",
        "DATA", "ADMISS", "FUNÇÃO", "FUNCAO", "SALÁRIO", "SALARIO",
        "HORÁRIO", "HORARIO", "TRABALHO", "SÁBADOS", "SABADOS",
        "DESCANSO", "SEMANAL", "FOLHA", "PONTO", "INDIVIDUAL",
        "JM MONTAGENS", "LTDA", "RUA", "JANEIRO", "FEVEREIRO",
        "MARÇO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO",
        "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
        "ASSINATURA", "VISTO", "NORMAIS", "ENTRADA", "SAÍDA",
        "SAIDA", "EXTRAS", "COMPENSADO", "DOMINGO", "DIAS",
        "RETORNO", "TARDE", "TOTAL", "MANHÃ", "MANHA", "RESUMO",
        "FISCALIZAÇÃO", "FISCALIZACAO", "ENCARREGADO", "SERVENTE",
        "PEDREIRO", "MESTRE", "OBRA",
        "STATUS", "ASSINADO", "ZAPSIGN", "TRUORA", "E-MAIL", "EMAIL",
        "TOKEN", "RELATÓRIO", "RELATORIO", "DOCUMENTO", "HASH",
    ]

    if any(b in upper for b in bloqueios):
        return False
    if re.search(r"\d", linha):
        return False

    palavras = linha.split()
    return 2 <= len(palavras) <= 5 and all(len(p) >= 2 for p in palavras)


def _competencia_folha_individual(texto):
    meses = {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARÇO": "03", "MARCO": "03",
        "ABRIL": "04", "MAIO": "05", "JUNHO": "06", "JULHO": "07",
        "AGOSTO": "08", "SETEMBRO": "09", "OUTUBRO": "10",
        "NOVEMBRO": "11", "DEZEMBRO": "12",
    }
    linhas = [limpar_valor(l).upper() for l in texto.splitlines() if limpar_valor(l)]
    for i, linha in enumerate(linhas):
        if linha in meses:
            for prox in linhas[i + 1:i + 4]:
                if re.fullmatch(r"\d{4}", prox):
                    return f"{meses[linha]}/{prox}"
    return None


def extrair_folha_ponto_individual(texto):
    if not texto or "FOLHA DE PONTO INDIVIDUAL DE TRABALHO" not in texto.upper():
        return []

    competencia = _competencia_folha_individual(texto)
    linhas = [limpar_valor(l) for l in texto.splitlines() if limpar_valor(l)]
    candidatos = []

    for i, linha in enumerate(linhas):
        upper = linha.upper()
        if upper in {"2025", "2026", "2027", "2028"}:
            for prox in linhas[i + 1:i + 6]:
                if _linha_nome_folha_individual(prox):
                    candidatos.append(prox.title())
                    break

        if _linha_nome_folha_individual(linha):
            janela = " ".join(linhas[max(0, i - 8):i + 8]).upper()
            if "ASSINATURA" in janela or "EMPREGADO" in janela:
                candidatos.append(linha.title())

    nomes = []
    vistos = set()
    for nome in candidatos:
        key = nome.lower()
        if key not in vistos:
            vistos.add(key)
            nomes.append(nome)

    if not nomes:
        return []

    horarios = re.findall(r"\b(?:[01]?\d|2[0-3])\s*[:;]\s*[0-5]\d\b", texto)
    horarios_validos = [h for h in horarios if re.sub(r"\s", "", h) not in {"00:00", "0:00"}]

    return [
        {
            "nome": nome,
            "competencia": competencia,
            "assinatura": False,
            "verificar_assinatura_visual": True,
            "datado": True,
            "marcacoes": len(horarios_validos) >= 4,
        }
        for nome in nomes
    ]

# ==========================================================
# 🧠 FALLBACK FINAL COMPLETO (PRODUÇÃO)
# ==========================================================
def extrair_com_fallback(texto):

    print("\n🚀 ===== INICIANDO EXTRAÇÃO =====")

    dados = extrair_folha_ponto_individual(texto)

    if dados:
        print("Parser Folha de Ponto Individual funcionou")
        print("RESULTADO FOLHA INDIVIDUAL:", dados)
        return dados

    dados = extrair_secullum_cartao_ponto(texto)

    if dados:
        print("Parser Secullum funcionou")
        print("RESULTADO SECULLUM:", dados)
        return dados

    dados = extrair_espelho_ponto_eletronico(texto)

    if dados:
        print("Parser Espelho de Ponto Eletronico funcionou")
        print("RESULTADO ESPELHO:", dados)
        return dados

    # ======================================================
    # 1️⃣ TEMPLATE
    # ======================================================
    dados = extrair_documento_completo(texto)

    if dados:
        print("✅ TEMPLATE FUNCIONOU")
        print("👥 RESULTADO TEMPLATE:", dados)
        return dados

    print("⚠️ TEMPLATE FALHOU")

    # ======================================================
    # 2️⃣ PARSER
    # ======================================================
    try:
        from validators.cartao_ponto.parser import parse_cartao_ponto

        resultado = parse_cartao_ponto(texto)

        if resultado:
            print("🧠 PARSER FUNCIONOU")
            print("👥 RESULTADO PARSER:", resultado)
            return resultado

        print("⚠️ PARSER NÃO ENCONTROU DADOS")

    except Exception as e:
        print("❌ ERRO PARSER:", e)

    # ======================================================
    # 3️⃣ HEURÍSTICA (NOME HUMANO)
    # ======================================================
    print("🔥 USANDO HEURÍSTICA")

    try:
        nomes = extrair_nomes_por_padrao(texto)

        if nomes:
            resultado = [{"nome": n} for n in nomes]
            print("👥 RESULTADO HEURÍSTICA:", resultado)
            return resultado

        print("⚠️ HEURÍSTICA NÃO ENCONTROU NOMES")

    except Exception as e:
        print("❌ ERRO HEURÍSTICA:", e)

    # ======================================================
    # 4️⃣ IA (GEMINI) - OPCIONAL
    # ======================================================
    print("🤖 TENTANDO IA (GEMINI)")

    try:
        from utils.gemini.cartao_ponto import extrair_cartao_ponto

        resposta_ia = extrair_cartao_ponto(texto)
        resultado_ia = resposta_ia.get("colaboradores", []) if isinstance(resposta_ia, dict) else resposta_ia

        if resultado_ia:
            print("🤖 IA FUNCIONOU")
            print("👥 RESULTADO IA:", resultado_ia)
            return resultado_ia

        print("⚠️ IA NÃO RETORNOU DADOS")

    except Exception as e:
        print("❌ ERRO IA:", e)

    # ======================================================
    # ❌ FALHA TOTAL
    # ======================================================
    print("❌ NENHUMA ESTRATÉGIA FUNCIONOU")

    return []
