import re
import io

import fitz
import pytesseract
from PIL import Image
from utils.ocr import extrair_texto_pdf_inteligente
from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.yolo_signature_detection import detectar_assinaturas_yolo, yolo_disponivel
from validators.vale_alimentacao.parser_va import extrair_dados_va


def _texto_normalizado(texto):
    return str(texto or "").upper()


def _normalizar_nome(nome):
    return re.sub(r"\s+", " ", str(nome or "").strip().upper())


def _titulo_nome(nome):
    return " ".join([p.capitalize() for p in _normalizar_nome(nome).split()])


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
        "DECLARACAO", "RECEBIMENTO", "ALIMENTACAO", "ASSINATURA", "NOME", "CPF",
        "DOCUMENTO", "NOTA FISCAL", "DANFE", "DESTINATARIO", "REMETENTE", "VENDA",
        "MERCADORIA", "SAO PAULO", "CNPJ", "INSCRICAO", "CHAVE DE ACESSO"
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
    for c in colaboradores:
        partes = _normalizar_nome(c.get("nome")).split()
        if len(partes) < 2:
            continue
        assinatura_curta = " ".join(partes[:2])
        if assinatura_curta in t or _normalizar_nome(c.get("nome")) in t:
            assinados += 1

    return assinados >= max(1, len(colaboradores) // 2)


def _detectar_tipo_documento(texto):
    t = _texto_normalizado(texto)
    tem_ecomprovante = any(chave in t for chave in ["E-COMPROVANTE", "ECOMPROVANTE", "COMPROVANTE EMITIDO"])
    tem_nome_valor = ("CPF" in t or "COLABORADOR" in t or "FUNCIONARIO" in t) and "R$" in t
    tem_pedido = "PEDIDO" in t or "SOLICITACAO" in t
    tem_nf = any(chave in t for chave in ["NOTA FISCAL", "NF-E", "NFE", "CHAVE DE ACESSO"])

    if tem_nf and tem_ecomprovante:
        return "nota_fiscal_ecomprovante"
    if tem_nome_valor:
        return "comprovante_colaborador"
    if tem_pedido and tem_nf:
        return "pedido_nota_fiscal"
    if tem_nf:
        return "nota_fiscal"
    if tem_pedido:
        return "pedido"
    return "indefinido"


def _extrair_total_documento(texto):
    t = _texto_normalizado(texto)
    padrao_valor = r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2})"

    candidatos = []
    for m in re.finditer(padrao_valor, t):
        trecho = t[max(0, m.start() - 60): m.start() + 40]
        valor = float(m.group(1).replace(".", "").replace(",", "."))
        peso = 1
        if any(k in trecho for k in ["TOTAL", "VALOR TOTAL", "TOTAL GERAL", "TOTAL DO PEDIDO", "TOTAL DA NOTA"]):
            peso = 3
        elif any(k in trecho for k in ["LIQUIDO", "LÍQUIDO", "A PAGAR"]):
            peso = 2
        candidatos.append((peso, valor))

    if not candidatos:
        return 0.0
    candidatos.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return round(candidatos[0][1], 2)


def _extrair_valor_por_contexto(texto, palavras_chave):
    t = _texto_normalizado(texto)
    padrao_valor = r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2})"
    candidatos = []

    for m in re.finditer(padrao_valor, t):
        try:
            valor = float(m.group(1).replace(".", "").replace(",", "."))
        except Exception:
            continue
        trecho = t[max(0, m.start() - 100): m.start() + 80]
        if any(ch in trecho for ch in palavras_chave):
            peso = 1
            if "TOTAL" in trecho:
                peso += 2
            candidatos.append((peso, valor))

    if not candidatos:
        return 0.0
    candidatos.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return round(candidatos[0][1], 2)


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
    return "\n".join([t for t in textos if t]).strip()


class VAValidator:
    def analisar(self, caminhos_pdf):
        texto_completo = ""
        caminhos_pdf = caminhos_pdf or []
        nomes_arquivos = " ".join([str(c or "") for c in caminhos_pdf]).upper()
        yolo_modelo_ok = yolo_disponivel()
        yolo_deteccoes_total = 0

        for caminho in caminhos_pdf:
            if yolo_modelo_ok:
                yolo_deteccoes_total += len(detectar_assinaturas_yolo(caminho))
            txt = extrair_texto_pdf_inteligente(caminho)
            if not txt:
                txt = _extrair_texto_fallback_pdf(caminho)
            if txt:
                texto_completo += f"\n{txt}"

        if not texto_completo.strip():
            tipo_por_nome = _detectar_tipo_documento(nomes_arquivos)
            return {
                "status": "Parcial",
                "mensagem": "Nao foi possivel extrair texto completo; classificacao preliminar por nome do arquivo.",
                "tipo_documento": tipo_por_nome,
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

        tipo_documento = _detectar_tipo_documento(texto_completo)
        auth_digital = detectar_autenticacao_digital(texto_completo)
        dados = extrair_dados_va(texto_completo)
        colaboradores = dados.get("colaboradores", [])
        colaboradores_declaracao = _extrair_colaboradores_declaracao(texto_completo)
        assinatura_digital_ok = _detectar_assinatura_digital(texto_completo, colaboradores_declaracao) or auth_digital.get("assinatura_digital")
        assinatura_yolo_ok = yolo_deteccoes_total > 0
        if colaboradores_declaracao:
            colaboradores = [{"nome": c["nome"], "valor": 0.0, "cpf": c.get("cpf")} for c in colaboradores_declaracao]
        soma = round(float(dados.get("soma_extraida", 0.0) or 0.0), 2)

        total_extraido_parser = round(float(dados.get("total_documento", 0.0) or 0.0), 2)
        total_documento = total_extraido_parser if total_extraido_parser > 0 else _extrair_total_documento(texto_completo)
        valor_nota_fiscal = _extrair_valor_por_contexto(
            texto_completo,
            ["VALOR TOTAL DA NOTA", "NOTA FISCAL", "NF-E", "NFE", "DANFE"],
        )
        valor_comprovante = _extrair_valor_por_contexto(
            texto_completo,
            ["E-COMPROVANTE", "ECOMPROVANTE", "COMPROVANTE", "PAGAMENTO", "VALOR PAGO"],
        )
        if valor_nota_fiscal <= 0:
            valor_nota_fiscal = total_documento
        if valor_comprovante <= 0:
            valor_comprovante = total_documento
        valores_encontrados = bool(valor_nota_fiscal > 0 and valor_comprovante > 0)
        valores_conferem = bool(valores_encontrados and abs(valor_nota_fiscal - valor_comprovante) <= 0.1)

        validacoes = []
        if tipo_documento == "comprovante_colaborador":
            for c in colaboradores:
                nome = (c.get("nome") or "").strip()
                valor = round(float(c.get("valor", 0.0) or 0.0), 2)
                if not nome:
                    continue
                validacoes.append(
                    {
                        "colaborador": nome,
                        "valor": valor,
                        "status": "OK" if valor > 0 else "Pendente",
                        "detalhe": "Nome e valor identificados no comprovante",
                    }
                )

        elif tipo_documento in {"nota_fiscal_ecomprovante", "pedido_nota_fiscal", "pedido", "nota_fiscal"}:
            has_nf = any(chave in _texto_normalizado(texto_completo) for chave in ["NOTA FISCAL", "NF-E", "NFE"])
            has_ecomprovante = any(
                chave in _texto_normalizado(texto_completo)
                for chave in ["E-COMPROVANTE", "ECOMPROVANTE", "COMPROVANTE EMITIDO"]
            )
            status_ok = (has_nf and total_documento > 0) or (has_nf and has_ecomprovante)
            if has_nf and has_ecomprovante:
                detalhe = "Nota fiscal e e-comprovante identificados"
            elif has_nf:
                detalhe = "Pedido com nota fiscal identificado"
            else:
                detalhe = "Pedido sem nota fiscal clara"
            validacoes.append(
                {
                    "colaborador": "Documento coletivo",
                    "valor": total_documento,
                    "status": "OK" if status_ok else "Pendente",
                    "detalhe": detalhe,
                }
            )
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
                    "detalhe": "Assinatura eletronica identificada (ZapSign/Assinado digitalmente)"
                    if assinatura_digital_ok
                    else "Nao foi possivel confirmar assinatura eletronica no documento",
                }
            )
            validacoes.append(
                {
                    "colaborador": "Assinatura visual (YOLO)",
                    "valor": 0.0,
                    "status": "OK" if assinatura_yolo_ok else "Pendente",
                    "detalhe": (
                        f"YOLO detectou {yolo_deteccoes_total} assinatura(s)/rubrica(s)"
                        if assinatura_yolo_ok
                        else "YOLO nao detectou assinatura visual"
                    ),
                }
            )

        else:
            validacoes.append(
                {
                    "colaborador": "Nao identificado",
                    "valor": total_documento,
                    "status": "Pendente",
                    "detalhe": "Nao foi possivel classificar como comprovante por colaborador ou pedido com nota fiscal",
                }
            )

        if tipo_documento == "comprovante_colaborador":
            conferido = bool(soma > 0 and total_documento > 0 and abs(soma - total_documento) <= 0.1)
            mensagem = (
                "Comprovante por colaborador identificado (nome + valor)."
                if colaboradores
                else "Documento parece comprovante, mas nenhum colaborador foi extraido com seguranca."
            )
        elif tipo_documento == "nota_fiscal_ecomprovante":
            has_nf = any(chave in _texto_normalizado(texto_completo) for chave in ["NOTA FISCAL", "NF-E", "NFE", "CHAVE DE ACESSO"])
            has_ecomprovante = any(
                chave in _texto_normalizado(texto_completo)
                for chave in ["E-COMPROVANTE", "ECOMPROVANTE", "COMPROVANTE EMITIDO"]
            )
            conferido = bool(has_nf and has_ecomprovante)
            mensagem = "Nota fiscal e e-comprovante identificados para VA."
        else:
            conferido = bool(total_documento > 0)
            mensagem = "Pedido/nota fiscal identificado para VA."

        return {
            "status": "Aprovado" if conferido else "Parcial",
            "mensagem": mensagem,
            "tipo_documento": tipo_documento,
            "validacoes": validacoes,
            "colaboradores": colaboradores,
            "resumo_financeiro": {
                "soma_colaboradores": soma,
                "total_boleto": total_documento,
                "valor_nota_fiscal": valor_nota_fiscal,
                "valor_comprovante": valor_comprovante,
                "valores_encontrados": valores_encontrados,
                "valores_conferem": valores_conferem,
                "conferido": conferido,
            },
            "autenticacao_digital": auth_digital,
            "assinatura_yolo": {
                "modelo_disponivel": yolo_modelo_ok,
                "detectada": assinatura_yolo_ok,
                "deteccoes_totais": yolo_deteccoes_total,
            },
        }
