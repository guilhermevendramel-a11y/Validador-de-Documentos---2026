import os
import re
import unicodedata
from rapidfuzz import fuzz

from services.document_learning import aprender_documento, encontrar_layout
from utils.gemini.holerite import extrair_holerite_inteligente
from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.ocr.ocr_comprovante import extrair_texto_comprovante
from utils.ocr.ocr_holerite import extrair_texto_holerite
from utils.signature_detection import detectar_rubricas_por_colaborador
from utils.yolo_signature_detection import (
    detectar_assinaturas_yolo,
    detectar_assinaturas_yolo_por_colaborador,
    yolo_disponivel,
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
)


def sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in texto if not unicodedata.combining(c))


def limpar_nome(nome):
    if not nome:
        return None

    nome = sem_acento(nome).upper()
    nome = re.sub(r"[^A-Z\s]", " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip()

    if len(nome) < 8 or len(nome.split()) < 2:
        return None
    if any(termo in nome for termo in TERMOS_INVALIDOS_NOME):
        return None

    return nome


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
        if "nome do funcionário" in linha.lower() or "nome do funcionario" in sem_acento(linha).lower():
            if index > 0:
                nome = limpar_nome(linhas_originais[index - 1])
                if nome:
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
            if nome:
                return nome

    for linha in texto_sem_acento.splitlines():
        nome = limpar_nome(linha)
        if nome:
            return nome

    return None


def normalizar_valor(valor):
    try:
        return float(str(valor).replace(".", "").replace(",", "."))
    except Exception:
        return None


def extrair_valor(texto, tipo="documento"):
    texto_upper = sem_acento(texto).upper()
    padroes_prioritarios = []

    if tipo == "holerite":
        linhas = [linha.strip() for linha in texto_upper.splitlines() if linha.strip()]
        for index, linha in enumerate(linhas):
            if "DECLARO TER RECEBIDO" in linha:
                janela = "\n".join(linhas[index + 1:index + 8])
                valores = [
                    normalizar_valor(valor)
                    for valor in re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", janela)
                ]
                valores = [valor for valor in valores if valor and valor > 100]
                if len(valores) >= 3:
                    return valores[2]
                if valores:
                    return valores[-1]

        padroes_prioritarios = [
            r"TOTAL\s+LIQUIDO\s*(?:A\s+RECEBER)?\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
            r"VALOR\s+LIQUIDO\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
            r"LIQUIDO\s*[:\-]?\s*R?\$?\s*([\d\.,]+)",
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

    matches = re.findall(r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", texto_upper)
    for valor_texto in reversed(matches):
        valor = normalizar_valor(valor_texto)
        if valor and valor > 100:
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
        match = re.search(rf"\b{mes}\s+DE\s+(\d{{4}})\b", texto_sem_acento)
        if match:
            return f"{numero}/{match.group(1)}"

    match = re.search(r"\b(0[1-9]|1[0-2])/\d{4}\b", texto or "")
    return match.group() if match else None


def analisar_assinatura_data(texto_bloco):
    if not texto_bloco:
        return {
            "assinatura_ok": False,
            "assinatura_detalhe": "Nao identificado",
            "data_manuscrita_ok": False,
            "data_detalhe": "Nao identificada",
        }

    texto_up = sem_acento(texto_bloco).upper()
    linhas = [l.strip() for l in texto_up.splitlines() if l.strip()]

    idx_ass = -1
    for i, linha in enumerate(linhas):
        if "ASSINATURA" in linha or "RUBRICA" in linha:
            idx_ass = i
            break

    janela = []
    if idx_ass >= 0:
        janela = linhas[max(0, idx_ass - 1): min(len(linhas), idx_ass + 6)]

    padrao_data = re.compile(r"\b([0-3]?\d/[01]?\d/\d{2,4})\b")
    data_encontrada = None
    for linha in janela or linhas[-10:]:
        m = padrao_data.search(linha)
        if m:
            data_encontrada = m.group(1)
            break

    palavras_ruido = {
        "ASSINATURA", "RUBRICA", "DATA", "RECIBO", "PAGAMENTO", "DECLARO",
        "RECEBIDO", "FUNCIONARIO", "EMPREGADO", "COMPETENCIA", "LIQUIDO",
    }
    rubrica_detectada = False
    if janela:
        for linha in janela:
            tokens = [t for t in re.findall(r"[A-Z]{2,}", linha) if t not in palavras_ruido]
            if tokens:
                rubrica_detectada = True
                break

    assinatura_ok = idx_ass >= 0 and rubrica_detectada
    data_ok = data_encontrada is not None

    return {
        "assinatura_ok": assinatura_ok,
        "assinatura_detalhe": "Rubrica/assinatura identificada" if assinatura_ok else "Rubrica/assinatura nao identificada",
        "data_manuscrita_ok": data_ok,
        "data_detalhe": f"Data identificada: {data_encontrada}" if data_ok else "Data proxima da assinatura nao identificada",
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
        r"(?=RECIBO\s+DE\s+PAGAMENTO|DEMONSTRATIVO|HOLERITE|MENSAL)",
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
        r"(?=COMPROVANTE|AUTENTICA(?:C|Ç|CAO|ÇÃO)|PIX|TED|TRANSFER[ÊE]NCIA)",
        texto,
        flags=re.IGNORECASE,
    )
    blocos = [b.strip() for b in blocos if b and len(b.strip()) > 30]
    if len(blocos) <= 1:
        blocos = re.split(r"(?=COMPROVANTE\s+BB)", texto, flags=re.IGNORECASE)
        blocos = [b.strip() for b in blocos if b and len(b.strip()) > 30]
    return blocos


def similaridade_nomes(nome_a, nome_b):
    a = normalizar_nome_comparacao(nome_a)
    b = normalizar_nome_comparacao(nome_b)
    if not a or not b:
        return 0
    score_base = fuzz.token_sort_ratio(a, b)
    tokens_a = a.split()
    tokens_b = b.split()
    inter = len(set(tokens_a) & set(tokens_b))
    cobertura = int((inter / max(1, min(len(tokens_a), len(tokens_b)))) * 100)
    bonus_prefixo = 0
    if tokens_a and tokens_b and tokens_a[0] == tokens_b[0]:
        bonus_prefixo = 5
    return max(score_base, cobertura + bonus_prefixo)


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


def extrair_nome_comprovante(texto):
    if not texto:
        return None
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    for i, linha in enumerate(linhas):
        chave = sem_acento(linha).upper()
        if chave in ("RECEBEDOR", "FAVORECIDO", "DESTINATARIO", "BENEFICIARIO"):
            if i + 1 < len(linhas):
                nome = limpar_nome(linhas[i + 1])
                if nome and not nome_parece_empresa(nome):
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
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    for linha in linhas[:12]:
        m = re.search(r"R\$\s*([\d\.,]+)", linha, flags=re.IGNORECASE)
        if m:
            v = normalizar_valor(m.group(1))
            if v and v > 0:
                return v
    return extrair_valor(texto, "comprovante") or 0.0


def nome_parece_empresa(nome):
    nome_limpo = limpar_nome(nome) or ""
    if not nome_limpo:
        return False
    marcadores_empresa = (" LTDA", " EIRELI", " S/A", " SA ", " ME ", " EPP", " CNPJ")
    if any(m in f" {nome_limpo} " for m in marcadores_empresa):
        return True
    if len(nome_limpo.split()) <= 3 and any(token in nome_limpo for token in ("LTDA", "S/A", "EIRELI")):
        return True
    return False


def processar_holerite_comprovante(path_holerite, paths_comprovantes, competencia_esperada=None):
    print("\n[HOLERITE] ===== HOLERITE + COMPROVANTES =====")

    if not path_holerite:
        return {"status": "Erro", "mensagem": "Arquivo do holerite nao enviado"}
    if not paths_comprovantes:
        return {"status": "Erro", "mensagem": "Comprovante de pagamento nao enviado"}

    try:
        texto_holerite = extrair_texto_holerite(path_holerite)
    except Exception as exc:
        return {"status": "Erro", "mensagem": "Erro OCR holerite", "detalhe": str(exc)}

    if not texto_holerite:
        return {"status": "Erro", "mensagem": "Erro OCR holerite"}

    layout_conhecido, confianca_layout = encontrar_layout("holerite", texto_holerite)

    textos_comprovantes = []
    nomes_comprovante = []

    for path in paths_comprovantes:
        try:
            texto = extrair_texto_comprovante(path)
        except Exception as exc:
            print(f"[HOLERITE] Erro OCR comprovante {path}: {exc}")
            texto = ""

        if texto:
            textos_comprovantes.append(texto)

        nome_arquivo = extrair_nome_arquivo(path)
        if nome_arquivo:
            nomes_comprovante.append(nome_arquivo)

    if not textos_comprovantes:
        return {"status": "Erro", "mensagem": "Erro OCR comprovantes"}

    holerites_extraidos = []
    for bloco in dividir_blocos_holerite(texto_holerite):
        nome = extrair_nome(bloco)
        valor = extrair_valor(bloco, "holerite")
        competencia_bloco = extrair_competencia(bloco)
        if nome_parece_empresa(nome):
            continue
        if nome or valor:
            analise_ass = analisar_assinatura_data(bloco)
            holerites_extraidos.append(
                {
                    "nome": nome,
                    "valor_holerite": valor or 0.0,
                    "competencia": competencia_bloco or competencia_esperada,
                    "competencia_holerite": competencia_bloco,
                    "assinatura_ok": analise_ass.get("assinatura_ok", False),
                    "assinatura_detalhe": analise_ass.get("assinatura_detalhe"),
                    "data_manuscrita_ok": analise_ass.get("data_manuscrita_ok", False),
                    "data_detalhe": analise_ass.get("data_detalhe"),
                }
            )

    if not holerites_extraidos:
        holerites_extraidos = [
            {
                "nome": extrair_nome(texto_holerite) or extrair_nome_arquivo(path_holerite),
                "valor_holerite": extrair_valor(texto_holerite, "holerite") or 0.0,
                "competencia": extrair_competencia(texto_holerite) or competencia_esperada,
                "competencia_holerite": extrair_competencia(texto_holerite),
                "assinatura_ok": False,
                "assinatura_detalhe": "Nao identificado",
                "data_manuscrita_ok": False,
                "data_detalhe": "Nao identificada",
            }
        ]
    holerites_extraidos = [
        h
        for h in holerites_extraidos
        if (h.get("nome") and not nome_parece_empresa(h.get("nome")))
        and (h.get("valor_holerite") or 0) > 0
    ] or holerites_extraidos

    comprovantes_extraidos = []
    for texto in textos_comprovantes:
        blocos = dividir_blocos_comprovante(texto) or [texto]
        for bloco in blocos:
            valor = extrair_valor_comprovante(bloco)
            nome = extrair_nome_comprovante(bloco)
            if nome:
                nomes_comprovante.append(nome)
            if nome or valor:
                comprovantes_extraidos.append(
                    {
                        "nome": nome,
                        "valor_comprovante": valor or 0.0,
                    }
                )

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
    }

    print("[HOLERITE] BASE OCR:", dados_base)

    try:
        dados_ia = extrair_holerite_inteligente(texto_holerite)
        if isinstance(dados_ia, dict):
            nome_ia = limpar_nome(dados_ia.get("nome"))
            dados_base.update(
                {
                    "nome_holerite": nome_ia or dados_base["nome_holerite"],
                    "valor_holerite": dados_ia.get("liquido") or dados_base["valor_holerite"],
                    "competencia": dados_ia.get("competencia") or dados_base["competencia"],
                }
            )
    except Exception as exc:
        print("[HOLERITE] IA falhou:", exc)

    layout_aprendido, modelo_novo = aprender_documento(
        "holerite",
        texto_holerite,
        {
            "nome_holerite": dados_base.get("nome_holerite"),
            "competencia": dados_base.get("competencia"),
            "valor_holerite": dados_base.get("valor_holerite"),
        },
        origem=os.path.basename(str(path_holerite)),
    )

    colaboradores = []
    erros = []
    comprovantes_disponiveis = list(comprovantes_extraidos)
    auth_digital = detectar_autenticacao_digital(texto_holerite + "\n" + "\n".join(textos_comprovantes))
    assinatura_digital_global = texto_indica_assinatura_digital(texto_holerite) or auth_digital.get("assinatura_digital")
    nomes_holerite = [h.get("nome") for h in holerites_extraidos if h.get("nome")]
    rubricas_por_nome = detectar_rubricas_por_colaborador(path_holerite, nomes_holerite)
    yolo_ok = yolo_disponivel()
    deteccoes_yolo = detectar_assinaturas_yolo(path_holerite) if yolo_ok else []
    assinaturas_yolo_por_nome = (
        detectar_assinaturas_yolo_por_colaborador(
            path_holerite,
            nomes_holerite,
            deteccoes=deteccoes_yolo,
        )
        if yolo_ok
        else {}
    )

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

        if not comprovante_match:
            valor_holerite_tmp = hol.get("valor_holerite") or 0.0
            candidatos_valor = [
                (idx, comp)
                for idx, comp in enumerate(comprovantes_disponiveis)
                if abs((comp.get("valor_comprovante") or 0.0) - valor_holerite_tmp) <= 0.01
            ]
            if len(candidatos_valor) == 1:
                idx_match, comp_match = candidatos_valor[0]
                comprovante_match = comp_match
                comprovantes_disponiveis.pop(idx_match)
                nome_ok = True

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
        competencia_ok = (
            True
            if not competencia_esperada
            else bool(competencia_item) and competencia_item == competencia_esperada
        )

        if not nome_ok:
            erros.append("Nome divergente")
        if not competencia_ok:
            erros.append("Competencia divergente")
        if not valor_ok:
            erros.append("Valor divergente entre holerite e comprovante")

        colaboradores.append(
            {
                "nome": nome_para_exibicao(hol.get("nome") or (comprovante_match or {}).get("nome")),
                "nome_holerite": hol.get("nome"),
                "nome_comprovante": (comprovante_match or {}).get("nome"),
                "competencia": competencia_item,
                "competencia_holerite": hol.get("competencia_holerite"),
                "assinatura": assinatura_final,
                "assinatura_status": assinatura_status,
                "assinatura_tipo": assinatura_tipo,
                "assinatura_origem": "yolo" if rubrica_yolo else ("legacy" if rubrica_legacy else ("digital" if assinatura_tipo == "digital" else "ausente")),
                "assinatura_confianca": rubrica_yolo_info.get("confianca", 0.0) if rubrica_yolo else 0.0,
                "assinatura_paginas": rubrica_yolo_info.get("paginas", []) if rubrica_yolo else [],
                "valor_liquido": valor_holerite,
                "valor_holerite": valor_holerite,
                "valor_pago": valor_comprovante,
                "valor_comprovante": valor_comprovante,
                "diferenca": diferenca,
                "valor_ok": valor_ok,
                "nome_ok": nome_ok,
                "competencia_ok": competencia_ok,
                "prazo": True,
                "prazo_status": "OK",
                "datado": "Sim" if hol.get("data_manuscrita_ok") else "Nao",
                "assinatura_detalhe": (
                    "Assinado digitalmente"
                    if assinatura_tipo == "digital"
                    else hol.get("assinatura_detalhe")
                ),
                "data_detalhe": hol.get("data_detalhe"),
            }
        )

    status_final = "Aprovado" if not erros else "Reprovado"

    resumo_financeiro = {
        "total_liquido": sum(c.get("valor_holerite", 0.0) for c in colaboradores),
        "total_pago": sum(c.get("valor_comprovante", 0.0) for c in colaboradores),
        "diferenca_total": sum(c.get("diferenca", 0.0) for c in colaboradores),
    }

    return {
        "status": status_final,
        "mensagem": f"{len(colaboradores)} colaborador(es) processado(s)",
        "competencia": dados_base["competencia"],
        "competencia_holerite": dados_base["competencia_holerite"],
        "nome_holerite": dados_base["nome_holerite"],
        "nome_comprovante": dados_base["nome_comprovante"],
        "valor_holerite": resumo_financeiro["total_liquido"],
        "valor_comprovante": resumo_financeiro["total_pago"],
        "diferenca": resumo_financeiro["diferenca_total"],
        "valor_ok": abs(resumo_financeiro["diferenca_total"]) <= 1,
        "empresa": "NAO IDENTIFICADA",
        "modelo_documento": (layout_conhecido or layout_aprendido).get("modelo"),
        "modelo_aprendido": modelo_novo,
        "confianca_modelo": round(confianca_layout, 2),
        "colaboradores": colaboradores,
        "resumo_financeiro": resumo_financeiro,
        "erros": sorted(set(erros)),
        "avisos": [],
        "autenticacao_digital": auth_digital,
        "assinatura_yolo": {
            "modelo_disponivel": yolo_ok,
            "deteccoes_totais": len(deteccoes_yolo),
        },
    }
