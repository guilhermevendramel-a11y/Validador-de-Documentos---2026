import re
import unicodedata
from rapidfuzz import fuzz

from utils.ocr import extrair_texto_pdf_inteligente


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))


def _normalizar_nome(nome):
    nome = _sem_acento(nome).upper()
    nome = re.sub(r"[^A-Z\s]", " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome


def _similar_nome(a, b):
    na = _normalizar_nome(a)
    nb = _normalizar_nome(b)
    if not na or not nb:
        return 0
    return fuzz.token_sort_ratio(na, nb)


def _extrair_vigencia(texto):
    texto_u = _sem_acento(texto).upper()

    m = re.search(
        r"(\d{2}/\d{2}/\d{4}).{0,140}?(?:ATE|AT|A|-)\s*(?:\d{1,2}H\s*DE\s*)?(\d{2}/\d{2}/\d{4})",
        texto_u,
        re.DOTALL,
    )
    if m:
        return m.group(1), m.group(2), f"{m.group(1)} a {m.group(2)}"

    inicio = re.search(r"INICIO\s+DE\s+VIGENCIA.*?(\d{2}/\d{2}/\d{4})", texto_u, re.DOTALL)
    fim = re.search(r"FIM\s+DE\s+VIGENCIA.*?(\d{2}/\d{2}/\d{4})", texto_u, re.DOTALL)
    if inicio and fim:
        return inicio.group(1), fim.group(1), f"{inicio.group(1)} a {fim.group(1)}"

    return None, None, "Vigencia nao identificada"


def _extrair_cnpj_razao(texto):
    cnpjs = re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto or "")
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    up = [_sem_acento(l).upper() for l in linhas]

    for i, linha in enumerate(up):
        if "RAZAO SOCIAL" in linha:
            atual = linhas[i]
            if ":" in atual and atual.split(":", 1)[1].strip():
                return (cnpjs[0] if cnpjs else None), atual.split(":", 1)[1].strip()
            if i + 1 < len(linhas):
                prox = linhas[i + 1].strip(": ").strip()
                if prox and "DADOS DO" not in _sem_acento(prox).upper():
                    return (cnpjs[0] if cnpjs else None), prox

    for cnpj in cnpjs:
        for i, linha in enumerate(linhas):
            if cnpj in linha:
                janela = linhas[max(0, i - 3): i + 2]
                for cand in janela:
                    cand_u = _sem_acento(cand).upper()
                    if any(k in cand_u for k in ["LTDA", "S/A", "CORRETORA", "SEGUROS", "ME ", "EIRELI"]):
                        return cnpj, cand.strip()

    return (cnpjs[0] if cnpjs else None), "Nao identificada"


def _detectar_tipo_apolice(texto, colaboradores):
    t = _sem_acento(texto).upper()
    if any(k in t for k in ["APOLICE COLETIVA", "TOTAL DE VIDAS", "ESTIPULANTE"]):
        return "GLOBAL"
    if "COBERTURA INDIVIDUAL" in t or "DADOS DO PROPONENTE" in t:
        return "INDIVIDUAL"
    if len(colaboradores) > 1:
        return "GLOBAL"
    if len(colaboradores) == 1:
        return "INDIVIDUAL"
    return "NAO IDENTIFICADO"


def _extrair_colaboradores_apolice(texto):
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    colaboradores = []

    # nome imediatamente antes de CPF numerico
    for i, linha in enumerate(linhas):
        if re.fullmatch(r"\d{11}", re.sub(r"\D", "", linha)) and i > 0:
            nome = _normalizar_nome(linhas[i - 1])
            if len(nome.split()) >= 2 and nome not in colaboradores:
                colaboradores.append(nome)

    # remove duplicados e termos ruins
    filtrados = []
    termos_ruins = {
        "DADOS", "VIGENCIA", "APOLICE", "SEGURO", "CAPITAL", "PREMIO", "CONTRATO",
        "NASCIMENTO", "PAGAMENTO", "FORMA", "COBERTURAS", "SORTEIO", "ENDERECO",
        "N", "CPF", "DATA",
    }
    for nome in colaboradores:
        if any(x in nome for x in ["RUA", "SAO PAULO", "BRASILEIRO", "ENCARREGADO"]):
            continue
        if any(t in nome.split() for t in termos_ruins):
            continue
        if nome not in filtrados:
            filtrados.append(nome)
    return filtrados[:50]


def _extrair_pagamentos_comprovante(texto):
    pagamentos = []
    blocos = re.split(r"(?=COMPROVANTE|PIX|TED|TRANSFERENCIA)", _sem_acento(texto).upper())
    if len(blocos) == 1:
        blocos = [texto]

    for bloco in blocos:
        linhas = [l.strip() for l in bloco.splitlines() if l.strip()]
        nome = None
        valor = 0.0

        for i, linha in enumerate(linhas):
            lu = _sem_acento(linha).upper()
            if lu in {"RECEBEDOR", "FAVORECIDO", "DESTINATARIO", "BENEFICIARIO"} and i + 1 < len(linhas):
                nome = _normalizar_nome(linhas[i + 1])
                break

        for linha in linhas[:15]:
            m = re.search(r"R\$\s*([\d\.,]+)", linha, re.IGNORECASE)
            if m:
                try:
                    valor = float(m.group(1).replace(".", "").replace(",", "."))
                    if valor > 0:
                        break
                except Exception:
                    pass

        if nome or valor > 0:
            pagamentos.append({"nome": nome, "valor": valor})

    return pagamentos


def _tem_indicio_pagamento(texto):
    t = _sem_acento(texto).upper()
    bloqueios = [
        "CONSULTA A LANCAMENTOS DE DEBITO AUTOMATICO",
        "LANCAMENTO PENDENTE",
        "LANCAMENTO RECUSADO",
        "DEBITO AUTOMATICO",
        "FATURA",
    ]
    if any(b in t for b in bloqueios):
        return False

    sinais_comprovante = [
        "COMPROVANTE",
        "AUTENTICACAO",
        "AUTENTICACAO SISBB",
        "PAGO EM",
        "PAGAMENTO EFETUADO",
        "TRANSACAO EFETIVADA",
    ]
    if any(s in t for s in sinais_comprovante):
        return True

    if "DADOS DE PAGAMENTO" in t or "FORMA DE PAGAMENTO" in t:
        return True
    if re.search(r"R\$\s*\d", t):
        return True
    if "VALOR DO PAGAMENTO" in t or "PREMIO LIQUIDO" in t or "PREMIO" in t:
        return True
    return False


def _valor_float(texto_valor):
    try:
        s = str(texto_valor).strip()
        if "." in s and "," in s:
            if s.find(",") < s.find("."):
                # formato 1,234.56
                s = s.replace(",", "")
            else:
                # formato 1.234,56
                s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            # formato 1234,56
            s = s.replace(",", ".")
        elif "." in s:
            # formato 1234.56 (decimal com ponto) ou 1.234 (milhar)
            partes = s.split(".")
            if len(partes) == 2 and len(partes[1]) <= 2:
                pass
            else:
                s = s.replace(".", "")
        return float(s)
    except Exception:
        return 0.0


def _extrair_valor_por_nome_no_texto(texto, nome_colaborador):
    if not texto or not nome_colaborador:
        return 0.0

    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    nome_norm = _normalizar_nome(nome_colaborador)
    nome_tokens = [t for t in nome_norm.split() if len(t) >= 3]
    if not nome_tokens:
        return 0.0

    idx_nome = -1
    for i, linha in enumerate(linhas):
        ln = _normalizar_nome(linha)
        if not ln:
            continue
        cobertura = sum(1 for t in nome_tokens if t in ln) / max(1, len(nome_tokens))
        if cobertura >= 0.66:
            idx_nome = i
            break

    if idx_nome < 0:
        return 0.0

    janela = linhas[idx_nome: min(len(linhas), idx_nome + 45)]
    prioridade = []
    fallback = []

    for linha in janela:
        linha_u = _sem_acento(linha).upper()
        valores = re.findall(r"R\$\s*([\d\.,]+)", linha, re.IGNORECASE)
        for v in valores:
            val = _valor_float(v)
            if val <= 0:
                continue
            if any(k in linha_u for k in ["PREMIO", "PAGAMENTO", "VALOR"]):
                prioridade.append(val)
            else:
                fallback.append(val)

    # remove valores claramente de capital segurado (normalmente altos)
    prioridade = [v for v in prioridade if v < 1000]
    fallback = [v for v in fallback if v < 1000]

    if prioridade:
        # normalmente o premio aparece depois do capital segurado
        return prioridade[-1]
    if fallback:
        return fallback[-1]
    return 0.0


class SeguroVidaValidator:
    def analisar(self, caminhos_pdf):
        arquivos = []
        for caminho in caminhos_pdf or []:
            txt = extrair_texto_pdf_inteligente(caminho) or ""
            if txt.strip():
                arquivos.append({"caminho": caminho, "texto": txt})

        if not arquivos:
            return {
                "status": "Erro",
                "mensagem": "Nao foi possivel extrair texto dos arquivos de seguro de vida.",
                "validacoes": [],
                "colaboradores": [],
            }

        apolice = None
        comprovantes = []

        for arq in arquivos:
            t = _sem_acento(arq["texto"]).upper()
            if any(k in t for k in ["APOLICE", "BILHETE", "DADOS DO PROPONENTE", "DADOS DO SEGURO"]):
                if apolice is None or len(arq["texto"]) > len(apolice["texto"]):
                    apolice = arq
            else:
                comprovantes.append(arq)

        if apolice is None:
            apolice = max(arquivos, key=lambda x: len(x["texto"]))
            comprovantes = [a for a in arquivos if a is not apolice]

        cnpj, razao = _extrair_cnpj_razao(apolice["texto"])
        vig_ini, vig_fim, vigencia = _extrair_vigencia(apolice["texto"])
        colaboradores_apolice = _extrair_colaboradores_apolice(apolice["texto"])
        tipo = _detectar_tipo_apolice(apolice["texto"], colaboradores_apolice)

        pagamentos = []
        for comp in comprovantes:
            pagamentos.extend(_extrair_pagamentos_comprovante(comp["texto"]))

        colaboradores = []
        if tipo == "INDIVIDUAL":
            base = colaboradores_apolice or []
            if not base and pagamentos:
                base = [p.get("nome") for p in pagamentos if p.get("nome")]

            usados = set()
            for nome in base:
                melhor = None
                melhor_idx = -1
                melhor_score = -1
                for i, pag in enumerate(pagamentos):
                    if i in usados:
                        continue
                    score = _similar_nome(nome, pag.get("nome"))
                    if score > melhor_score:
                        melhor_score = score
                        melhor = pag
                        melhor_idx = i

                comprovante_ok = melhor is not None and melhor_score >= 75
                if comprovante_ok:
                    usados.add(melhor_idx)

                colaboradores.append(
                    {
                        "nome": nome,
                        "comprovante_pagamento": comprovante_ok,
                        "valor_comprovante": (melhor or {}).get("valor", 0.0) if comprovante_ok else 0.0,
                        "status": "OK" if comprovante_ok else "Pendente",
                        "detalhe": "Comprovante localizado" if comprovante_ok else "Comprovante nao localizado para o colaborador",
                    }
                )
        else:
            colaboradores = [
                {
                    "nome": "APOLICE GLOBAL",
                    "comprovante_pagamento": bool(pagamentos),
                    "valor_comprovante": sum(p.get("valor", 0.0) for p in pagamentos),
                    "status": "OK" if pagamentos else "Pendente",
                    "detalhe": "Comprovante de pagamento localizado" if pagamentos else "Comprovante de pagamento nao localizado",
                }
            ]

        comprovante_no_mesmo_pdf = _tem_indicio_pagamento(apolice["texto"])
        if tipo == "INDIVIDUAL" and comprovante_no_mesmo_pdf and not pagamentos:
            for c in colaboradores:
                valor_localizado = _extrair_valor_por_nome_no_texto(apolice["texto"], c.get("nome"))
                c["comprovante_pagamento"] = True
                c["status"] = "OK"
                c["valor_comprovante"] = valor_localizado
                c["detalhe"] = "Comprovante identificado no mesmo documento da apolice"

        comprovante_ok_geral = all(c.get("comprovante_pagamento") for c in colaboradores)
        vigencia_ok = vigencia != "Vigencia nao identificada"
        tipo_ok = tipo in {"GLOBAL", "INDIVIDUAL"}
        cnpj_ok = bool(cnpj) if tipo == "GLOBAL" else True

        validacoes = [
            {"item": "Vigencia", "valor": vigencia, "status": "OK" if vigencia_ok else "Pendente"},
            {"item": "Tipo de apolice", "valor": tipo, "status": "OK" if tipo_ok else "Pendente"},
            {"item": "Razao social", "valor": razao or "Nao identificada", "status": "OK" if razao and razao != "Nao identificada" else "Pendente"},
            {
                "item": "Comprovante(s) de pagamento",
                "valor": "Localizado" if comprovante_ok_geral else "Pendente",
                "status": "OK" if comprovante_ok_geral else "Pendente",
            },
        ]
        if tipo == "GLOBAL":
            validacoes.insert(3, {"item": "CNPJ", "valor": cnpj or "Nao encontrado", "status": "OK" if cnpj_ok else "Pendente"})

        status = "Aprovado" if all(v["status"] == "OK" for v in validacoes) else "Reprovado"

        return {
            "status": status,
            "mensagem": "Apolice analisada com sucesso.",
            "empresa": razao or "Nao identificada",
            "cnpj": (cnpj or "Nao encontrado") if tipo == "GLOBAL" else "-",
            "vigencia": vigencia,
            "vigencia_inicio": vig_ini,
            "vigencia_fim": vig_fim,
            "tipo_apolice": tipo,
            "validacoes": validacoes,
            "colaboradores": colaboradores,
            "resumo_financeiro": {
                "total_pago": sum(c.get("valor_comprovante", 0.0) for c in colaboradores),
                "quantidade_colaboradores": len(colaboradores),
            },
        }
