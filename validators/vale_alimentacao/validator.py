import io
import os
import re

import fitz
import pytesseract
from PIL import Image

from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.ocr import extrair_texto_pdf_inteligente
from utils.openai.comprovante import extrair_comprovante_openai_pdf
from utils.validations import extrair_competencia as extrair_competencia_texto
from utils.yolo_signature_detection import detectar_assinaturas_yolo, yolo_disponivel
from validators.vale_alimentacao.parser_va import extrair_dados_va


def _texto_normalizado(texto):
    return str(texto or "").upper()


def _normalizar_nome(nome):
    return re.sub(r"\s+", " ", str(nome or "").strip().upper())


def _titulo_nome(nome):
    return " ".join([p.capitalize() for p in _normalizar_nome(nome).split()])


def _normalizar_valor(valor):
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    txt = str(valor).strip().replace("R$", "").replace("r$", "").replace(" ", "")
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return round(float(txt), 2)
    except Exception:
        return 0.0


def _extrair_colaboradores_declaracao(texto):
    t = _texto_normalizado(texto)
    bloco = t
    m_bloco = re.search(
        r"NOME\s*CPF\s*ASSINATURA(.*?)(ASSINADO DIGITALMENTE|ZAPSIGN|DOCUMENTO ASSINADO ELETRONICAMENTE)",
        t,
        re.S,
    )
    if m_bloco:
        bloco = m_bloco.group(1)

    padrao = r"([A-ZÀ-Ú][A-ZÀ-Ú\s]{4,}?)\s+(\d{3}\.?\d{3}\.?\d{3}-?\d{2})"
    candidatos = re.findall(padrao, bloco)

    bloqueios = {
        "DECLARACAO",
        "RECEBIMENTO",
        "ALIMENTACAO",
        "ASSINATURA",
        "NOME",
        "CPF",
        "DOCUMENTO",
        "NOTA FISCAL",
        "DANFE",
        "DESTINATARIO",
        "REMETENTE",
        "VENDA",
        "MERCADORIA",
        "SAO PAULO",
        "CNPJ",
        "INSCRICAO",
        "CHAVE DE ACESSO",
    }

    colaboradores = []
    vistos = set()
    for nome_raw, cpf in candidatos:
        linhas = [ln.strip() for ln in re.split(r"[\r\n]+", nome_raw) if ln.strip()]
        nome_base = linhas[-1] if linhas else nome_raw
        nome = _normalizar_nome(nome_base)
        if len(nome.split()) < 2:
            continue
        if any(b in nome for b in bloqueios):
            continue
        chave = (nome, cpf)
        if chave in vistos:
            continue
        vistos.add(chave)
        colaboradores.append({"nome": _titulo_nome(nome), "cpf": cpf})

    return colaboradores


def _detectar_assinatura_digital(texto, colaboradores):
    t = _texto_normalizado(texto)
    has_marcador = any(
        chave in t
        for chave in [
            "ASSINADO DIGITALMENTE",
            "DOCUMENTO ASSINADO ELETRONICAMENTE",
            "ZAPSIGN",
            "LEI 14.063/2020",
            "MP 2.200-2/2001",
        ]
    )
    if not has_marcador:
        return False

    if not colaboradores:
        return True

    assinados = 0
    for colaborador in colaboradores:
        partes = _normalizar_nome(colaborador.get("nome")).split()
        if len(partes) < 2:
            continue
        assinatura_curta = " ".join(partes[:2])
        if assinatura_curta in t or _normalizar_nome(colaborador.get("nome")) in t:
            assinados += 1

    return assinados >= max(1, len(colaboradores) // 2)


def _detectar_tipo_documento(texto):
    contexto = _detectar_contexto_documental(texto, "")
    return contexto["tipo_documento"]


def _detectar_contexto_documental(texto_completo, nomes_arquivos=""):
    base = _texto_normalizado(f"{texto_completo or ''}\n{nomes_arquivos or ''}")
    has_nf = any(chave in base for chave in ["NOTA FISCAL", "NF-E", "NFE", "DANFE", "CHAVE DE ACESSO"])
    has_pedido = any(chave in base for chave in ["PEDIDO", "SOLICITACAO", "SOLICITACAO DE", "SOLICITACAO:"])
    has_comprovante = any(
        chave in base
        for chave in [
            "RECIBO",
            "COMPROVANTE",
            "E-COMPROVANTE",
            "ECOMPROVANTE",
            "TRANSFERENCIA",
            "PIX",
            "PAGAMENTO",
        ]
    )

    if has_nf:
        tipo = "nota_fiscal"
    elif has_pedido:
        tipo = "pedido"
    elif has_comprovante:
        tipo = "comprovante_colaborador"
    else:
        tipo = "indefinido"

    return {
        "tipo_documento": tipo,
        "has_nf": has_nf,
        "has_pedido": has_pedido,
        "has_comprovante": has_comprovante,
    }


def _extrair_total_documento(texto):
    t = _texto_normalizado(texto)
    padrao_valor = r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2})"

    candidatos = []
    for match in re.finditer(padrao_valor, t):
        trecho = t[max(0, match.start() - 60): match.start() + 40]
        valor = float(match.group(1).replace(".", "").replace(",", "."))
        peso = 1
        if any(k in trecho for k in ["TOTAL", "VALOR TOTAL", "TOTAL GERAL", "TOTAL DO PEDIDO", "TOTAL DA NOTA"]):
            peso = 3
        elif any(k in trecho for k in ["LIQUIDO", "A PAGAR"]):
            peso = 2
        candidatos.append((peso, valor))

    if not candidatos:
        return 0.0

    candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return round(candidatos[0][1], 2)


def _extrair_valor_por_contexto(texto, palavras_chave):
    t = _texto_normalizado(texto)
    padrao_valor = r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2})"
    candidatos = []

    for match in re.finditer(padrao_valor, t):
        try:
            valor = float(match.group(1).replace(".", "").replace(",", "."))
        except Exception:
            continue
        trecho = t[max(0, match.start() - 100): match.start() + 80]
        if any(chave in trecho for chave in palavras_chave):
            peso = 1
            if "TOTAL" in trecho:
                peso += 2
            candidatos.append((peso, valor))

    if not candidatos:
        return 0.0

    candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return round(candidatos[0][1], 2)


def _tem_termo(texto, termos):
    t = _texto_normalizado(texto)
    return any(termo in t for termo in termos)


def _extrair_colaboradores_openai(caminhos_textos):
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return []

    colaboradores = []
    vistos = set()

    for caminho, texto in caminhos_textos:
        if not caminho:
            continue
        try:
            dados_ia = extrair_comprovante_openai_pdf(caminho, texto_ocr=texto or "", max_paginas=6)
        except Exception:
            continue

        pagamentos = dados_ia.get("pagamentos") or []
        for item in pagamentos:
            if not isinstance(item, dict):
                continue
            nome = _titulo_nome(item.get("nome") or item.get("nome_colaborador") or "")
            valor = _normalizar_valor(item.get("valor_pago") or item.get("valor") or item.get("liquido"))
            if not nome:
                continue
            chave = (nome, valor)
            if chave in vistos:
                continue
            vistos.add(chave)
            colaboradores.append(
                {
                    "nome": nome,
                    "valor": valor,
                    "origem": "openai_comprovante",
                    "evidencia": "Fallback OpenAI para comprovante/recibo",
                }
            )

    return colaboradores


def _somente_nomes_colaboradores(colaboradores):
    nomes = []
    vistos = set()

    for item in colaboradores or []:
        if isinstance(item, dict):
            nome_bruto = item.get("nome") or item.get("nome_colaborador") or ""
        else:
            nome_bruto = item

        nome = _titulo_nome(nome_bruto)
        chave = _normalizar_nome(nome)
        if not chave or chave in vistos:
            continue

        vistos.add(chave)
        nomes.append({"nome": nome})

    return nomes


def _extrair_texto_fallback_pdf(caminho_pdf):
    textos = []
    try:
        with fitz.open(caminho_pdf) as doc:
            for pagina in doc:
                texto = (pagina.get_text() or "").strip()
                if texto:
                    textos.append(texto)
                    continue
                pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                textos.append(pytesseract.image_to_string(img, lang="por"))
    except Exception:
        return ""
    return "\n".join([texto for texto in textos if texto]).strip()


def _extrair_textos_paginas_pdf(caminho_pdf):
    textos = []
    try:
        with fitz.open(caminho_pdf) as doc:
            for pagina in doc:
                texto = (pagina.get_text() or "").strip()
                if not texto:
                    pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    texto = pytesseract.image_to_string(img, lang="por").strip()
                textos.append(texto or "")
    except Exception:
        return []
    return textos


def _classificar_pagina_va(texto):
    t = _texto_normalizado(texto)
    if any(chave in t for chave in ["COMPROVANTE", "TRANSFERENCIA", "TRANSFERÊNCIA", "PIX", "SISPAG"]):
        return "comprovante"
    if any(chave in t for chave in ["DECLARO", "DECLARACAO", "DECLARA", "REEMBOLSO", "RECIBO"]):
        return "declaracao"
    return "outro"


class VAValidator:
    def analisar(self, caminhos_pdf):
        caminhos_pdf = caminhos_pdf or []
        textos_por_arquivo = []
        paginas_por_arquivo = []
        texto_completo = ""
        nomes_arquivos = " ".join([str(c or "") for c in caminhos_pdf]).upper()
        yolo_modelo_ok = yolo_disponivel()
        yolo_deteccoes_total = 0

        for caminho in caminhos_pdf:
            if yolo_modelo_ok:
                yolo_deteccoes_total += len(detectar_assinaturas_yolo(caminho))

            textos_paginas = _extrair_textos_paginas_pdf(caminho)
            if not textos_paginas:
                txt = extrair_texto_pdf_inteligente(caminho)
                if not txt:
                    txt = _extrair_texto_fallback_pdf(caminho)
                textos_paginas = [txt or ""]

            texto_arquivo = []
            for indice, texto_pagina in enumerate(textos_paginas):
                texto_pagina = texto_pagina or ""
                if texto_pagina:
                    texto_completo += f"\n{texto_pagina}"
                texto_arquivo.append(texto_pagina)
                paginas_por_arquivo.append((caminho, indice, texto_pagina))

            textos_por_arquivo.append((caminho, "\n".join([texto for texto in texto_arquivo if texto]).strip()))

        if not texto_completo.strip():
            contexto_vazio = _detectar_contexto_documental("", nomes_arquivos)
            return {
                "status": "Parcial",
                "mensagem": "Nao foi possivel extrair texto completo; classificacao preliminar por nome do arquivo.",
                "tipo_documento": contexto_vazio["tipo_documento"],
                "validacoes": [
                    {
                        "colaborador": "Nao identificado",
                        "valor": 0.0,
                        "status": "Pendente",
                        "detalhe": "OCR sem texto util. Recomendado PDF pesquisavel ou imagem com melhor qualidade.",
                    }
                ],
                "colaboradores": [],
                "resumo_financeiro": {
                    "soma_colaboradores": 0.0,
                    "total_boleto": 0.0,
                    "valor_nota_fiscal": 0.0,
                    "valor_comprovante": 0.0,
                    "conferido": False,
                },
            }

        contexto = _detectar_contexto_documental(texto_completo, nomes_arquivos)
        tipo_documento = contexto["tipo_documento"]
        auth_digital = detectar_autenticacao_digital(texto_completo)
        competencia_documento = extrair_competencia_texto(texto_completo) or ""
        dados_documento = extrair_dados_va(texto_completo)

        colaboradores_map = {}
        for _, _, texto_pagina in paginas_por_arquivo:
            dados_pagina = extrair_dados_va(texto_pagina)
            tipo_pagina = _classificar_pagina_va(texto_pagina)
            for item in (dados_pagina.get("colaboradores_detalhados") or dados_pagina.get("colaboradores") or []):
                nome = _titulo_nome(item.get("nome"))
                valor = round(_normalizar_valor(item.get("valor")), 2)
                if not nome or valor <= 0:
                    continue

                chave = _normalizar_nome(nome)
                registro = colaboradores_map.setdefault(
                    chave,
                    {
                        "nome": nome,
                        "cpf": item.get("cpf"),
                        "valor_recibo": 0.0,
                        "valor_comprovante": 0.0,
                        "valor": 0.0,
                    },
                )
                if item.get("cpf") and not registro.get("cpf"):
                    registro["cpf"] = item.get("cpf")

                if tipo_pagina == "comprovante":
                    registro["valor_comprovante"] = valor
                elif tipo_pagina == "declaracao":
                    registro["valor_recibo"] = valor
                else:
                    if not registro["valor_recibo"]:
                        registro["valor_recibo"] = valor
                    elif not registro["valor_comprovante"]:
                        registro["valor_comprovante"] = valor

                registro["valor"] = registro["valor_comprovante"] or registro["valor_recibo"] or valor

        colaboradores = list(colaboradores_map.values()) or (dados_documento.get("colaboradores_detalhados") or dados_documento.get("colaboradores", []))

        if not colaboradores and tipo_documento == "comprovante_colaborador":
            colaboradores_ia = _extrair_colaboradores_openai(textos_por_arquivo)
            if colaboradores_ia:
                colaboradores = colaboradores_ia

        colaboradores_declaracao = [] if tipo_documento == "comprovante_colaborador" else _extrair_colaboradores_declaracao(texto_completo)
        assinatura_digital_ok = _detectar_assinatura_digital(texto_completo, colaboradores_declaracao) or auth_digital.get("assinatura_digital")
        assinatura_yolo_ok = yolo_deteccoes_total > 0

        if colaboradores_declaracao and colaboradores:
            mapa_valores = {}
            for item in colaboradores:
                nome_item = _normalizar_nome(item.get("nome"))
                if nome_item:
                    mapa_valores[nome_item] = item

            nomes_declaracao = set()
            colaboradores_merge = []
            for colaborador in colaboradores_declaracao:
                nome_norm = _normalizar_nome(colaborador.get("nome"))
                nomes_declaracao.add(nome_norm)
                item_base = dict(mapa_valores.get(nome_norm, {}))
                item_base["nome"] = colaborador["nome"]
                item_base["cpf"] = colaborador.get("cpf")
                item_base["valor"] = round(_normalizar_valor(item_base.get("valor")), 2)
                colaboradores_merge.append(item_base)

            for nome_norm, item in mapa_valores.items():
                if nome_norm not in nomes_declaracao:
                    colaboradores_merge.append(item)

            colaboradores = colaboradores_merge or colaboradores

        def _normalizar_registro(colaborador):
            nome = _titulo_nome(colaborador.get("nome"))
            valor_recibo = round(_normalizar_valor(colaborador.get("valor_recibo") or colaborador.get("valor")), 2)
            valor_comprovante = round(_normalizar_valor(colaborador.get("valor_comprovante") or colaborador.get("valor")), 2)
            if valor_recibo <= 0 and valor_comprovante > 0:
                valor_recibo = valor_comprovante
            if valor_comprovante <= 0 and valor_recibo > 0:
                valor_comprovante = valor_recibo
            valor = round(_normalizar_valor(colaborador.get("valor") or valor_comprovante or valor_recibo), 2)
            return {
                **colaborador,
                "nome": nome,
                "valor_recibo": valor_recibo,
                "valor_comprovante": valor_comprovante,
                "valor": valor,
            }

        colaboradores = [_normalizar_registro(colaborador) for colaborador in colaboradores if _titulo_nome(colaborador.get("nome"))]

        soma_recibo = round(sum(_normalizar_valor(c.get("valor_recibo")) for c in colaboradores), 2)
        soma_comprovante = round(sum(_normalizar_valor(c.get("valor_comprovante")) for c in colaboradores), 2)
        soma = round(sum(_normalizar_valor(c.get("valor")) for c in colaboradores), 2)

        total_extraido_parser = round(float(dados_documento.get("total_documento", 0.0) or 0.0), 2)
        total_documento = total_extraido_parser if total_extraido_parser > 0 else (soma_comprovante or soma_recibo or _extrair_total_documento(texto_completo))

        has_nf = contexto["has_nf"]
        has_pedido = contexto["has_pedido"]
        tem_recibo_ou_comprovante = contexto["has_comprovante"]
        tem_declaracao = _tem_termo(
            texto_completo,
            [
                "DECLARO",
                "DECLARACAO",
                "DECLARA",
                "TERMOS DE RECEBIMENTO",
                "RECEBI",
                "ASSUNTO",
            ],
        )

        valor_nota_fiscal = _extrair_valor_por_contexto(
            texto_completo,
            ["VALOR TOTAL DA NOTA", "NOTA FISCAL", "NF-E", "NFE", "DANFE"],
        )
        valor_comprovante = soma_comprovante
        valor_recibo = soma_recibo if soma_recibo > 0 else (total_documento if tem_recibo_ou_comprovante else 0.0)

        if has_nf and valor_nota_fiscal <= 0:
            valor_nota_fiscal = total_documento
        if tem_recibo_ou_comprovante and valor_comprovante <= 0:
            valor_comprovante = total_documento

        valores_separados = []
        for colaborador in colaboradores:
            nome = _titulo_nome(colaborador.get("nome"))
            valor_recibo_ind = round(_normalizar_valor(colaborador.get("valor_recibo")), 2)
            valor_comprovante_ind = round(_normalizar_valor(colaborador.get("valor_comprovante")), 2)
            if not nome:
                continue
            status_ind = "OK" if valor_recibo_ind > 0 and valor_comprovante_ind > 0 and abs(valor_recibo_ind - valor_comprovante_ind) <= 0.1 else "Pendente"
            detalhe_ind = (
                "Recibo e comprovante conferidos por colaborador"
                if status_ind == "OK"
                else "Nao foi possivel comparar recibo e comprovante por colaborador"
            )
            valores_separados.append(
                {
                    "nome": nome,
                    "valor_recibo": valor_recibo_ind,
                    "valor_comprovante": valor_comprovante_ind,
                    "valor": valor_comprovante_ind or valor_recibo_ind,
                    "status": status_ind,
                    "detalhe": detalhe_ind,
                }
            )

        valores_encontrados = bool(valores_separados) if tipo_documento == "comprovante_colaborador" else bool(valor_nota_fiscal > 0 and valor_comprovante > 0)
        valores_conferem = bool(valores_separados) and all(
            abs(item["valor_recibo"] - item["valor_comprovante"]) <= 0.1 and item["valor_recibo"] > 0 and item["valor_comprovante"] > 0
            for item in valores_separados
        )
        tem_colaboradores = bool(colaboradores or colaboradores_declaracao)

        if tipo_documento == "comprovante_colaborador":
            if valores_separados:
                validacoes = [
                    {
                        "colaborador": item["nome"],
                        "valor": item["valor"],
                        "valor_recibo": item["valor_recibo"],
                        "valor_comprovante": item["valor_comprovante"],
                        "status": item["status"],
                        "detalhe": item["detalhe"],
                    }
                    for item in valores_separados
                ]
            else:
                validacoes = [
                    {
                        "colaborador": "Nao identificado",
                        "valor": total_documento,
                        "status": "Pendente",
                        "detalhe": "Documento classificado como comprovante, mas o nome do colaborador nao foi extraido com seguranca.",
                    }
                ]
        elif tipo_documento == "nota_fiscal":
            status_ok = bool(tem_declaracao and tem_recibo_ou_comprovante and valores_encontrados and valores_conferem)
            if status_ok:
                detalhe = "Nota fiscal com declaracao e comprovante conferidos"
            elif not tem_declaracao:
                detalhe = "Nota fiscal sem declaracao com nomes dos colaboradores"
            elif not tem_recibo_ou_comprovante:
                detalhe = "Nota fiscal sem comprovante"
            elif not valores_encontrados:
                detalhe = "Nao foi possivel localizar os valores da nota e do comprovante"
            else:
                detalhe = "Valor da nota fiscal divergente do comprovante"

            validacoes = [
                {
                    "colaborador": "Documento coletivo",
                    "valor": valor_nota_fiscal or total_documento,
                    "status": "OK" if status_ok else "Pendente",
                    "detalhe": detalhe,
                }
            ]
            if colaboradores_declaracao:
                validacoes.append(
                    {
                        "colaborador": f"{len(colaboradores_declaracao)} colaboradores identificados",
                        "valor": 0.0,
                        "status": "OK",
                        "detalhe": "Colaboradores extraidos da declaracao (Nome + CPF)",
                    }
                )
            validacoes.append(
                {
                    "colaborador": "Assinatura digital",
                    "valor": 0.0,
                    "status": "OK" if assinatura_digital_ok else "Pendente",
                    "detalhe": "Assinatura eletronica identificada"
                    if assinatura_digital_ok
                    else "Nao foi possivel confirmar assinatura eletronica no documento",
                }
            )
        elif tipo_documento == "pedido":
            status_ok = bool(tem_colaboradores and tem_recibo_ou_comprovante)
            if status_ok:
                detalhe = "Pedido com nomes dos colaboradores e comprovante identificados"
            elif not tem_colaboradores:
                detalhe = "Pedido sem nomes de colaboradores identificados"
            else:
                detalhe = "Pedido sem comprovante"
            validacoes = [
                {
                    "colaborador": "Documento coletivo",
                    "valor": total_documento,
                    "status": "OK" if status_ok else "Pendente",
                    "detalhe": detalhe,
                }
            ]
        else:
            validacoes = [
                {
                    "colaborador": "Nao identificado",
                    "valor": total_documento,
                    "status": "Pendente",
                    "detalhe": "Nao foi possivel classificar o pacote como nota fiscal, pedido ou comprovante.",
                }
            ]

        if tipo_documento == "comprovante_colaborador":
            conferido = bool(valores_separados) and all(item["status"] == "OK" for item in valores_separados)
            mensagem = (
                "Comprovante por colaborador identificado (nome + valor)."
                if valores_separados
                else "Documento parece comprovante, mas nenhum colaborador foi extraido com seguranca."
            )
        elif tipo_documento == "nota_fiscal":
            conferido = bool(tem_declaracao and tem_recibo_ou_comprovante and valores_encontrados and valores_conferem)
            if conferido:
                mensagem = "Nota fiscal com declaracao e comprovante conferidos para VA."
            elif not tem_declaracao:
                mensagem = "Nota fiscal sem declaracao com nomes dos colaboradores."
            elif not tem_recibo_ou_comprovante:
                mensagem = "Nota fiscal sem comprovante."
            elif not valores_encontrados:
                mensagem = "Nao foi possivel localizar os valores da nota fiscal e do comprovante."
            else:
                mensagem = "Valor da nota fiscal divergente do comprovante."
        elif tipo_documento == "pedido":
            conferido = bool(tem_colaboradores and tem_recibo_ou_comprovante)
            if conferido:
                mensagem = "Pedido com nomes dos colaboradores e comprovante identificado."
            elif not tem_colaboradores:
                mensagem = "Pedido sem nomes de colaboradores identificados."
            else:
                mensagem = "Pedido sem comprovante."
        else:
            conferido = bool(total_documento > 0)
            mensagem = "Documento identificado para VA."

        colaboradores_saida = _somente_nomes_colaboradores(colaboradores)

        return {
            "status": "Aprovado" if conferido else "Parcial",
            "mensagem": mensagem,
            "tipo_documento": tipo_documento,
            "competencia": competencia_documento,
            "validacoes": validacoes,
            "colaboradores": colaboradores_saida,
            "resumo_financeiro": {
                "soma_colaboradores": soma,
                "soma_recibo": soma_recibo,
                "soma_comprovante": soma_comprovante,
                "total_boleto": total_documento,
                "competencia": competencia_documento,
                "valor_nota_fiscal": valor_nota_fiscal,
                "valor_comprovante": valor_comprovante,
                "valor_recibo": valor_recibo,
                "valores_separados": valores_separados,
                "valores_encontrados": valores_encontrados,
                "valores_conferem": valores_conferem,
                "tem_colaboradores": tem_colaboradores,
                "tem_declaracao": tem_declaracao,
                "tem_recibo_ou_comprovante": tem_recibo_ou_comprovante,
                "has_pedido": has_pedido,
                "has_nf": has_nf,
                "conferido": conferido,
            },
            "autenticacao_digital": auth_digital,
            "assinatura_yolo": {
                "modelo_disponivel": yolo_modelo_ok,
                "detectada": assinatura_yolo_ok,
                "deteccoes_totais": yolo_deteccoes_total,
            },
        }
