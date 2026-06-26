import io
import re
from collections import OrderedDict
from typing import Dict, List

import fitz
import pytesseract
from PIL import Image

from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.ocr import extrair_texto_pdf_inteligente
from utils.yolo_signature_detection import detectar_assinaturas_yolo, yolo_disponivel


def _normalizar(texto: str) -> str:
    texto = str(texto or "").upper()
    texto = (
        texto.replace("Á", "A").replace("À", "A").replace("Â", "A").replace("Ã", "A")
        .replace("É", "E").replace("Ê", "E")
        .replace("Í", "I")
        .replace("Ó", "O").replace("Ô", "O").replace("Õ", "O")
        .replace("Ú", "U")
        .replace("Ç", "C")
    )
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _titulo_nome(nome: str) -> str:
    nome = re.sub(r"\s+", " ", str(nome or "").strip())
    if not nome:
        return ""
    return " ".join(p.capitalize() for p in nome.split())


def _limpar_nome_bruto(nome: str) -> str:
    n = str(nome or "").strip()
    if not n:
        return ""

    n = re.sub(
        r"(?i)\b(RG|CPF|DATA|ASSINATURA|VALOR|MATRICULA|MATRÍCULA|CNPJ|CONTA|AGENCIA|AGÊNCIA|BANCO|CHAVE|PIX|TED|TEF)\b.*$",
        "",
        n,
    ).strip()
    n = re.sub(
        r"^\s*(EU|NOME|COLABORADOR|FUNCIONARIO|BENEFICIARIO)\s*[:\-]?\s*",
        "",
        n,
        flags=re.I,
    ).strip()
    n = re.sub(r"[,\.;:]+$", "", n).strip()
    return n


_BLOCKLIST_NOME = {
    "VALE",
    "TRANSPORTE",
    "TERMO",
    "DISPENSA",
    "OPTANTE",
    "NAO",
    "RECIBO",
    "COMPROVANTE",
    "TRANSFERENCIA",
    "PAGAMENTO",
    "RECEBIMENTO",
    "RECEBI",
    "DECLARO",
    "DECLARACAO",
    "RELACAO",
    "COLABORADORES",
    "COLABORADOR",
    "NOME",
    "ASSINATURA",
    "CPF",
    "RG",
    "CNPJ",
    "AGENCIA",
    "CONTA",
    "BANCO",
    "PIX",
    "TED",
    "TEF",
    "NOTA",
    "FISCAL",
    "DANFE",
    "EMPRESA",
    "FOLHA",
    "SALARIO",
    "VALOR",
    "TOTAL",
    "LIQUIDO",
    "REEMBOLSO",
    "ASSUNTO",
    "DEVIDOS",
    "FINS",
    "TERMOS",
    "SERVICO",
    "SERVICOS",
    "SERVIÇOS",
    "CONSULTORIA",
    "CONSULTORIA",
    "ENGENHARIA",
    "TECNICO",
    "TECNICO",
    "CORRETORA",
    "CORRETORAS",
    "SEGUROS",
    "LIMITADA",
    "LTDA",
    "EIRELI",
    "M E",
    "ME",
    "EPP",
    "SA",
    "S A",
    "S/A",
    "S.A",
    "INDUSTRIA",
    "INDUSTRIA",
    "COMERCIO",
    "COMERCIO",
    "TRANSPORTE",
    "TRANSPORTES",
    "LOGISTICA",
    "ADMINISTRACAO",
    "ASSESSORIA",
    "SISPAG",
    "SALARIO",
    "SALARIOS",
    "EXTRATO",
    "BANCO",
    "AGENCIA",
    "CONTA",
    "INFORMACOES FORNECIDAS PELO",
    "INFORMACOES FORNECIDAS",
    "FORNECIDAS PELO",
}


def _tem_bloqueio_linha(linha_norm: str) -> bool:
    palavras = set(linha_norm.split())
    for bloqueio in _BLOCKLIST_NOME:
        bloqueio_norm = _normalizar(bloqueio)
        if " " in bloqueio_norm:
            if bloqueio_norm in linha_norm:
                return True
        elif bloqueio_norm in palavras:
            return True
    return False


def _parece_nome_humano(candidato: str) -> bool:
    candidato = _titulo_nome(_limpar_nome_bruto(candidato))
    if not candidato or len(candidato) < 8:
        return False
    if re.search(r"\d", candidato):
        return False

    nome_norm = _normalizar(candidato)
    palavras = [p for p in nome_norm.split() if p]
    if len(palavras) < 2 or len(palavras) > 6:
        return False

    if nome_norm.startswith("INFORMACOES FORNECIDAS") or "FORNECIDAS PELO" in nome_norm:
        return False

    bloqueios_exatos = {
        "LTDA",
        "LIMITADA",
        "EIRELI",
        "ME",
        "EPP",
        "SA",
        "S A",
        "S/A",
        "S.A",
        "CONSULTORIA",
        "ENGENHARIA",
        "SEGUROS",
        "CORRETORA",
        "CORRETORAS",
        "TRANSPORTE",
        "TRANSPORTES",
        "SERVICO",
        "SERVICOS",
        "SERVIÇOS",
        "ADMINISTRACAO",
        "ASSESSORIA",
        "COMERCIO",
        "INDUSTRIA",
        "SISPAG",
        "SALARIO",
        "SALARIOS",
        "EXTRATO",
    }

    if any(p in bloqueios_exatos for p in palavras):
        return False

    nome_norm = _normalizar(candidato)
    if any(b in nome_norm for b in [" LTDA", " LIMITADA", " EIRELI", " S/A", " S.A", " CONSULTORIA", " ENGENHARIA", " SISPAG", " EXTRATO", " SALARIOS", " SALARIO"]):
        return False

    if sum(1 for p in palavras if len(p) >= 3) < 2:
        return False

    if sum(1 for p in palavras if p in {"DE", "DA", "DO", "DAS", "DOS", "E"}) > 3:
        return False

    return True


def _tokens_nome(nome: str) -> List[str]:
    return [token for token in _normalizar(_titulo_nome(nome)).split() if token]


def _eh_prefixo_de_nome_melhor(nome_curto: str, nome_longo: str) -> bool:
    curto = _tokens_nome(nome_curto)
    longo = _tokens_nome(nome_longo)
    if len(curto) < 2 or len(longo) < 2:
        return False
    if len(curto) > len(longo):
        return False

    if curto == longo[: len(curto)] and len(longo) > len(curto):
        return True

    if len(curto) == len(longo) and curto[:-1] == longo[:-1]:
        ultimo_curto = curto[-1]
        ultimo_longo = longo[-1]
        if ultimo_longo.startswith(ultimo_curto) and len(ultimo_longo) > len(ultimo_curto):
            return True

    return False


def _preferir_nomes_mais_completos(nomes: List[str]) -> List[str]:
    nomes_unicos = []
    vistos = set()
    for nome in nomes or []:
        nome_limpo = _titulo_nome(nome)
        chave = _normalizar(nome_limpo)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        nomes_unicos.append(nome_limpo)

    filtrados = []
    for nome in nomes_unicos:
        if any(
            _eh_prefixo_de_nome_melhor(nome, outro)
            for outro in nomes_unicos
            if outro != nome
        ):
            continue
        filtrados.append(nome)

    return filtrados


def _extrair_textos_paginas_pdf(caminho_pdf: str) -> List[str]:
    textos = []

    try:
        with fitz.open(caminho_pdf) as doc:
            for pagina in doc:
                texto = (pagina.get_text() or "").strip()
                if len(texto) < 25:
                    pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    texto = pytesseract.image_to_string(img, lang="por").strip()
                textos.append(texto or "")
    except Exception:
        return []

    if sum(len(txt.strip()) for txt in textos) < 120:
        texto_ocr = extrair_texto_pdf_inteligente(caminho_pdf) or ""
        if texto_ocr.strip():
            return [texto_ocr]

    return textos


def _tem_texto(texto_norm: str, termos: List[str]) -> bool:
    return any(_normalizar(termo) in texto_norm for termo in termos)


def _detectar_contexto_documental(texto: str) -> Dict[str, bool]:
    t = _normalizar(texto)
    return {
        "tem_termo_nao_optante": _tem_texto(
            t,
            [
                "TERMO DE NAO OPTANTE",
                "TERMO DE DISPENSA",
                "DISPENSA DO VALE TRANSPORTE",
                "NAO UTILIZAREI O VALE TRANSPORTE",
                "NAO DESEJO USUFRUIR DO VALE TRANSPORTE",
                "NAO OPTANTE",
            ],
        ),
        "tem_recibo": _tem_texto(
            t,
            [
                "RECIBO",
                "RECEBI",
                "RECEBIMENTO",
                "DECLARO TER RECEBIDO",
                "TERMO DE RECEBIMENTO",
            ],
        ),
        "tem_comprovante": _tem_texto(
            t,
            [
                "COMPROVANTE",
                "COMPROVANTE DE TRANSFERENCIA",
                "TRANSFERENCIA",
                "PIX",
                "TED",
                "TEF",
                "PAGAMENTO",
                "AUTENTICACAO",
            ],
        ),
        "tem_nf": _tem_texto(
            t,
            [
                "NOTA FISCAL",
                "NF-E",
                "NFE",
                "DANFE",
                "CHAVE DE ACESSO",
            ],
        ),
        "tem_declaracao": _tem_texto(
            t,
            [
                "DECLARACAO",
                "DECLARO",
                "RELACAO DE COLABORADORES",
                "RELACAO DE FUNCIONARIOS",
                "RELACAO",
            ],
        ),
    }


def _extrair_valor_monetario(texto: str, contexto_prioritario: List[str] | None = None) -> float:
    t = _normalizar(texto)
    padrao = r"R?\$?\s*([\d]{1,3}(?:\.\d{3})*,\d{2})"
    candidatos = []

    for match in re.finditer(padrao, t):
        trecho = t[max(0, match.start() - 100): match.start() + 80]
        try:
            valor = float(match.group(1).replace(".", "").replace(",", "."))
        except Exception:
            continue

        peso = 1
        if any(k in trecho for k in ["VALOR", "LIQUIDO", "PAGO", "PAGAMENTO", "TOTAL", "RECEBIDO"]):
            peso += 2
        if contexto_prioritario and any(_normalizar(k) in trecho for k in contexto_prioritario):
            peso += 3
        candidatos.append((peso, valor))

    if not candidatos:
        return 0.0

    candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return round(candidatos[0][1], 2)


def _extrair_nomes_colaboradores(texto: str) -> List[str]:
    linhas = [linha.strip() for linha in re.split(r"[\r\n]+", texto or "") if linha.strip()]
    candidatos = []

    for indice, linha in enumerate(linhas):
        linha_limpa = linha.strip()
        linha_norm = _normalizar(linha_limpa)
        if not linha_norm:
            continue

        nome_extraido = ""
        if linha_norm.startswith("NOME") or linha_norm.startswith("COLABORADOR") or linha_norm.startswith("FUNCIONARIO") or linha_norm.startswith("BENEFICIARIO"):
            parte = re.split(r"[:\-]", linha_limpa, 1)
            if len(parte) == 2:
                nome_extraido = parte[1].strip()
            elif indice + 1 < len(linhas):
                nome_extraido = linhas[indice + 1].strip()

        if not nome_extraido and linha_norm.startswith("EU"):
            m = re.search(
                r"(?i)\bEU[,:\s]+([A-ZÀ-Ú' \-]{5,100}?)(?=,|\s+(?:RG|CPF|DATA|ASSINATURA|VALOR|DECLARO|MATRICULA|MATRÍCULA)|$)",
                linha_limpa,
            )
            if m:
                nome_extraido = m.group(1).strip()

        if nome_extraido:
            candidatos.append(nome_extraido)
            continue

        if _tem_bloqueio_linha(linha_norm):
            continue

        candidatos.append(linha_limpa)

    nomes = OrderedDict()
    for candidato in candidatos:
        candidato = _limpar_nome_bruto(candidato)
        candidato = re.sub(r"\s{2,}", " ", candidato).strip()
        if not _parece_nome_humano(candidato):
            continue
        nome = _titulo_nome(candidato)
        nomes[_normalizar(nome)] = nome

    return _preferir_nomes_mais_completos(list(nomes.values()))


def _extrair_nome_termo(texto: str) -> str:
    t = texto or ""
    padroes = [
        r"(?im)\bEU[,:\s]+([A-ZÀ-Ú][A-ZÀ-Ú' \-]{5,100}?)(?=,|\s+(?:RG|CPF|DATA|ASSINATURA|VALOR|DECLARO|MATRICULA|MATRÍCULA)|$)",
        r"(?im)\bNOME\s*[:\-]?\s*([A-ZÀ-Ú][A-ZÀ-Ú' \-]{5,100}?)(?=,|\s+(?:RG|CPF|DATA|ASSINATURA|VALOR|DECLARO|MATRICULA|MATRÍCULA)|$)",
    ]
    for padrao in padroes:
        m = re.search(padrao, t)
        if m:
            nome = _titulo_nome(_limpar_nome_bruto(m.group(1)))
            if _parece_nome_humano(nome):
                return nome

    nomes = _extrair_nomes_colaboradores(texto)
    return nomes[0] if nomes else ""


def _extrair_nome_recebimento(texto: str) -> str:
    t = texto or ""
    padroes = [
        r"(?im)\bNOME\s*[:\-]?\s*([A-ZÀ-Ú][A-ZÀ-Ú' \-]{5,100}?)(?=,|\s+(?:VALOR|R\$|DATA|ASSINATURA|TRANSFERENCIA)|$)",
        r"(?im)\bCOLABORADOR\s*[:\-]?\s*([A-ZÀ-Ú][A-ZÀ-Ú' \-]{5,100}?)(?=,|\s+(?:VALOR|R\$|DATA|ASSINATURA|TRANSFERENCIA)|$)",
        r"(?im)\bBENEFICIARIO\s*[:\-]?\s*([A-ZÀ-Ú][A-ZÀ-Ú' \-]{5,100}?)(?=,|\s+(?:VALOR|R\$|DATA|ASSINATURA|TRANSFERENCIA)|$)",
    ]
    for padrao in padroes:
        m = re.search(padrao, t)
        if m:
            nome = _titulo_nome(_limpar_nome_bruto(m.group(1)))
            if _parece_nome_humano(nome):
                return nome

    nomes = _extrair_nomes_colaboradores(texto)
    return nomes[0] if nomes else ""


def _extrair_nome_nf(texto: str) -> str:
    nomes = _extrair_nomes_colaboradores(texto)
    return nomes[0] if nomes else ""


def _somente_nomes_colaboradores(nomes: List[str]) -> List[Dict[str, str]]:
    saida = []
    vistos = set()
    for nome in nomes or []:
        nome_limpo = _titulo_nome(nome)
        chave = _normalizar(nome_limpo)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        saida.append({"nome": nome_limpo})
    return saida


def _chave_nome(nome: str) -> str:
    return _normalizar(_titulo_nome(nome))


def _tipo_documento_registro(registro: Dict) -> str:
    if registro.get("tem_termo"):
        return "termo_nao_optante"
    if registro.get("tem_nf") and (registro.get("tem_declaracao") or registro.get("tem_comprovante")):
        return "nota_fiscal"
    if registro.get("tem_recibo") or registro.get("tem_comprovante"):
        return "recibo_comprovante"
    return "indefinido"


def _comparar_valores(valor_base: float, valor_comprovante: float) -> Dict[str, object]:
    valor_base = round(float(valor_base or 0.0), 2)
    valor_comprovante = round(float(valor_comprovante or 0.0), 2)
    if valor_base <= 0 or valor_comprovante <= 0:
        return {"diferenca": 0.0, "conferencia": "PENDENTE", "valor_ok": False}

    diferenca = round(valor_comprovante - valor_base, 2)
    valor_ok = abs(diferenca) <= 0.1
    return {
        "diferenca": diferenca,
        "conferencia": "OK" if valor_ok else "DIVERGENTE",
        "valor_ok": valor_ok,
    }


def _atualizar_registro(registro: Dict, texto: str, contexto: Dict[str, bool], assinatura_ok: bool, yolo_ok: bool, arquivo: str):
    if arquivo:
        registro["arquivos"].add(arquivo)
    registro["tem_termo"] = registro["tem_termo"] or contexto["tem_termo_nao_optante"]
    registro["tem_recibo"] = registro["tem_recibo"] or contexto["tem_recibo"]
    registro["tem_comprovante"] = registro["tem_comprovante"] or contexto["tem_comprovante"]
    registro["tem_nf"] = registro["tem_nf"] or contexto["tem_nf"]
    registro["tem_declaracao"] = registro["tem_declaracao"] or contexto["tem_declaracao"]
    registro["assinatura_ok"] = registro["assinatura_ok"] or assinatura_ok or yolo_ok

    valor_recibo = _extrair_valor_monetario(texto, ["RECIBO", "RECEBI", "RECEBIDO", "VALOR"])
    valor_comprovante = _extrair_valor_monetario(texto, ["COMPROVANTE", "TRANSFERENCIA", "PIX", "TED", "TEF", "PAGAMENTO"])
    valor_nf = _extrair_valor_monetario(texto, ["NOTA FISCAL", "NF-E", "NFE", "DANFE", "VALOR TOTAL", "TOTAL DA NOTA"])

    if contexto["tem_recibo"] and valor_recibo > 0:
        if registro.get("valor_recibo", 0.0) <= 0 or valor_recibo > registro["valor_recibo"]:
            registro["valor_recibo"] = valor_recibo
    if contexto["tem_comprovante"] and valor_comprovante > 0:
        if registro.get("valor_comprovante", 0.0) <= 0 or valor_comprovante > registro["valor_comprovante"]:
            registro["valor_comprovante"] = valor_comprovante
    if contexto["tem_nf"] and valor_nf > 0:
        if registro.get("valor_nf", 0.0) <= 0 or valor_nf > registro["valor_nf"]:
            registro["valor_nf"] = valor_nf


def _avaliar_registro(registro: Dict) -> Dict:
    nome = registro["nome"] or "COLABORADOR NAO IDENTIFICADO"
    tipo_documento = _tipo_documento_registro(registro)
    tem_termo = bool(registro["tem_termo"])
    tem_recibo = bool(registro["tem_recibo"])
    tem_comprovante = bool(registro["tem_comprovante"])
    tem_nf = bool(registro["tem_nf"])
    tem_declaracao = bool(registro["tem_declaracao"])
    assinatura_ok = bool(registro["assinatura_ok"])
    valor_recibo = round(float(registro.get("valor_recibo") or 0.0), 2)
    valor_comprovante = round(float(registro.get("valor_comprovante") or 0.0), 2)
    valor_nf = round(float(registro.get("valor_nf") or 0.0), 2)
    valor_base = valor_nf if tipo_documento == "nota_fiscal" else valor_recibo
    comparacao = _comparar_valores(valor_base, valor_comprovante)

    if tem_termo:
        status = "OK" if assinatura_ok else "Pendente"
        detalhe = (
            "Termo de nao optante localizado e validado"
            if status == "OK"
            else "Termo de nao optante localizado, mas sem assinatura digital ou OCR suficiente para validar"
        )
        fluxo = "termo_nao_optante"
    elif tem_recibo and tem_comprovante:
        if valor_recibo > 0 and valor_comprovante > 0 and abs(valor_recibo - valor_comprovante) > 0.1:
            status = "Pendente"
            detalhe = f"Valor do recibo divergente do comprovante ({valor_recibo:.2f} x {valor_comprovante:.2f})"
        elif valor_recibo > 0 and valor_comprovante > 0:
            status = "OK"
            detalhe = "Recibo e comprovante conferidos"
        else:
            status = "OK"
            detalhe = "Recibo e comprovante localizados"
        fluxo = "recibo_comprovante"
    elif tem_nf and tem_declaracao and tem_comprovante:
        if valor_nf > 0 and valor_comprovante > 0 and abs(valor_nf - valor_comprovante) > 0.1:
            status = "Pendente"
            detalhe = f"Valor da nota fiscal divergente do comprovante ({valor_nf:.2f} x {valor_comprovante:.2f})"
        elif valor_nf > 0 and valor_comprovante > 0:
            status = "OK"
            detalhe = "Nota fiscal, declaracao e comprovante conferidos"
        else:
            status = "OK"
            detalhe = "Nota fiscal, declaracao e comprovante localizados"
        fluxo = "nf_declaracao_comprovante"
    else:
        status = "Pendente"
        if tem_termo:
            detalhe = "Termo de nao optante localizado, mas sem assinatura valida"
        elif tem_recibo and not tem_comprovante:
            detalhe = "Recibo localizado sem comprovante"
        elif tem_comprovante and not tem_recibo:
            detalhe = "Comprovante localizado sem recibo"
        elif tem_nf and not tem_declaracao:
            detalhe = "Nota fiscal localizada sem declaracao com nomes dos colaboradores"
        elif tem_declaracao and not tem_comprovante:
            detalhe = "Declaracao localizada sem comprovante"
        else:
            detalhe = "Nao foi possivel enquadrar o documento em termo de nao optante, recibo+comprovante ou NF+declaracao+comprovante"
        fluxo = "indefinido"

    return {
        "nome": nome,
        "colaborador": nome,
        "tipo_documento": tipo_documento,
        "valor_base": valor_base,
        "status": status,
        "detalhe": detalhe,
        "fluxo": fluxo,
        "assinatura_digital": assinatura_ok,
        "valor_recibo": valor_recibo,
        "valor_comprovante": valor_comprovante,
        "valor_nf": valor_nf,
        "diferenca": comparacao["diferenca"],
        "conferencia": comparacao["conferencia"],
        "valor_ok": comparacao["valor_ok"],
    }


class VTValidator:
    def analisar(self, caminhos_pdf):
        caminhos_pdf = caminhos_pdf or []
        yolo_modelo_ok = yolo_disponivel()
        yolo_deteccoes_total = 0
        registros: Dict[str, Dict] = OrderedDict()
        texto_global = []

        for indice_arquivo, caminho in enumerate(caminhos_pdf):
            caminho_str = str(caminho or "")
            textos_paginas = _extrair_textos_paginas_pdf(caminho_str) or [""]
            texto_arquivo = "\n".join(txt for txt in textos_paginas if txt).strip()
            texto_global.append(texto_arquivo)

            contexto = _detectar_contexto_documental(texto_arquivo)
            assinatura_digital = bool(detectar_autenticacao_digital(texto_arquivo).get("assinatura_digital"))
            yolo_ok = False
            if yolo_modelo_ok:
                try:
                    dets = detectar_assinaturas_yolo(caminho_str)
                    yolo_deteccoes_total += len(dets)
                    yolo_ok = len(dets) > 0
                except Exception:
                    yolo_ok = False

            nomes = _extrair_nomes_colaboradores(texto_arquivo)
            if not nomes:
                if contexto["tem_termo_nao_optante"]:
                    nome_termo = _extrair_nome_termo(texto_arquivo)
                    if nome_termo:
                        nomes = [nome_termo]
                elif contexto["tem_recibo"] or contexto["tem_comprovante"]:
                    nome_recibo = _extrair_nome_recebimento(texto_arquivo)
                    if nome_recibo:
                        nomes = [nome_recibo]
                elif contexto["tem_nf"] or contexto["tem_declaracao"]:
                    nome_nf = _extrair_nome_nf(texto_arquivo)
                    if nome_nf:
                        nomes = [nome_nf]

            if not nomes:
                nomes = [f"ARQUIVO {indice_arquivo + 1}"]

            for nome in nomes:
                chave = _chave_nome(nome)
                if chave not in registros:
                    registros[chave] = {
                        "nome": _titulo_nome(nome),
                        "arquivos": set(),
                        "tem_termo": False,
                        "tem_recibo": False,
                        "tem_comprovante": False,
                        "tem_nf": False,
                        "tem_declaracao": False,
                        "assinatura_ok": False,
                        "valor_recibo": 0.0,
                        "valor_comprovante": 0.0,
                        "valor_nf": 0.0,
                    }
                _atualizar_registro(registros[chave], texto_arquivo, contexto, assinatura_digital, yolo_ok, caminho_str)

        if not registros:
            return {
                "status": "Pendente",
                "mensagem": "Nao foi possivel ler o documento de Vale Transporte.",
                "fluxo_aplicado": "indefinido",
                "validacoes": [
                    {
                        "colaborador": "Nao identificado",
                        "status": "Pendente",
                        "detalhe": "OCR sem texto util.",
                    }
                ],
                "colaboradores": [],
                "documentos": {},
                "autenticacao_digital": detectar_autenticacao_digital("\n".join(texto_global)),
                "assinatura_yolo": {
                    "modelo_disponivel": yolo_modelo_ok,
                    "detectada": False,
                    "deteccoes_totais": yolo_deteccoes_total,
                },
            }

        validacoes = [_avaliar_registro(registro) for registro in registros.values()]
        colaboradores_saida = _somente_nomes_colaboradores([item["nome"] for item in validacoes if item.get("nome")])
        colaboradores_detalhados = [
            {
                "nome": item.get("nome") or item.get("colaborador") or "",
                "tipo_documento": item.get("tipo_documento") or "indefinido",
                "valor_base": item.get("valor_base", 0.0),
                "valor_recibo": item.get("valor_recibo", 0.0),
                "valor_comprovante": item.get("valor_comprovante", 0.0),
                "valor_nf": item.get("valor_nf", 0.0),
                "diferenca": item.get("diferenca", 0.0),
                "conferencia": item.get("conferencia", "PENDENTE"),
                "status": item.get("status", "Pendente"),
                "detalhe": item.get("detalhe", ""),
                "fluxo": item.get("fluxo", "indefinido"),
                "assinatura_digital": item.get("assinatura_digital", False),
            }
            for item in validacoes
            if item.get("nome") or item.get("colaborador")
        ]

        fluxo_aplicado = "indefinido"
        if any(item["fluxo"] == "termo_nao_optante" for item in validacoes):
            fluxo_aplicado = "termo_nao_optante"
        elif any(item["fluxo"] == "recibo_comprovante" for item in validacoes):
            fluxo_aplicado = "recibo_comprovante"
        elif any(item["fluxo"] == "nf_declaracao_comprovante" for item in validacoes):
            fluxo_aplicado = "nf_declaracao_comprovante"

        documentos = {
            "Termo de nao optante": any(registro["tem_termo"] for registro in registros.values()),
            "Recibo": any(registro["tem_recibo"] for registro in registros.values()),
            "Comprovante": any(registro["tem_comprovante"] for registro in registros.values()),
            "Nota Fiscal": any(registro["tem_nf"] for registro in registros.values()),
            "Declaracao": any(registro["tem_declaracao"] for registro in registros.values()),
        }

        total = len(validacoes)
        ok = sum(1 for item in validacoes if item.get("status") == "OK")
        status_global = "Aprovado" if total and ok == total else ("Parcial" if ok > 0 else "Pendente")

        if fluxo_aplicado == "termo_nao_optante":
            mensagem = "Termo de nao optante identificado e validado."
        elif fluxo_aplicado == "recibo_comprovante":
            mensagem = "Recibo e comprovante identificados para Vale Transporte."
        elif fluxo_aplicado == "nf_declaracao_comprovante":
            mensagem = "Nota fiscal, declaracao e comprovante identificados para Vale Transporte."
        else:
            mensagem = "Documentos de Vale Transporte identificados com validacao parcial."

        return {
            "status": status_global,
            "mensagem": mensagem,
            "fluxo_aplicado": fluxo_aplicado,
            "validacoes": validacoes,
            "colaboradores": colaboradores_saida,
            "colaboradores_detalhados": colaboradores_detalhados,
            "documentos": documentos,
            "autenticacao_digital": detectar_autenticacao_digital("\n".join(texto_global)),
            "assinatura_yolo": {
                "modelo_disponivel": yolo_modelo_ok,
                "detectada": yolo_deteccoes_total > 0,
                "deteccoes_totais": yolo_deteccoes_total,
            },
        }
