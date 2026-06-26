import os
import re
import tempfile
import zipfile
import csv
import unicodedata


def _normalizar(texto):
    texto = str(texto or "")
    texto = "".join(
        ch for ch in unicodedata.normalize("NFD", texto)
        if unicodedata.category(ch) != "Mn"
    ).upper()
    texto = (
        texto.replace("Ã‡", "C")
        .replace("Ç", "C")
        .replace("Ãƒ", "A")
        .replace("Ã•", "O")
        .replace("Õ", "O")
        .replace("Ã‰", "E")
        .replace("É", "E")
        .replace("Ã", "A")
        .replace("Á", "A")
        .replace("À", "A")
        .replace("Â", "A")
        .replace("Ê", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ô", "O")
        .replace("Ú", "U")
    )
    return texto


def _normalizar_basico(texto):
    texto = str(texto or "").strip().lower()
    texto = "".join(
        ch for ch in unicodedata.normalize("NFD", texto)
        if unicodedata.category(ch) != "Mn"
    )
    return texto


def _competencia_por_caminho(caminho):
    match = re.search(r"COMP\.\s*(\d{2})-(\d{4})", _normalizar(caminho))
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None


def _arquivo_pdf(caminho):
    return caminho.lower().endswith(".pdf")


def _classificar(caminho_relativo, caminho_absoluto, grupos):
    texto = _normalizar(caminho_relativo)
    arquivo = _normalizar(os.path.basename(caminho_relativo))

    if "CARTAO PONTO" in texto or "CARTÃO PONTO" in texto:
        grupos["cartao_ponto"]["file"] = caminho_absoluto
        return

    if "FOLHA DE PAGAMENTO" in texto:
        grupos["folha_pagamento"]["file"] = caminho_absoluto
        return

    if "HOLERITE" in texto:
        if "COMPROVANTE" in texto:
            grupos["holerite"].setdefault("comprovantes", []).append(caminho_absoluto)
        else:
            grupos["holerite"].setdefault("holerites", []).append(caminho_absoluto)
        return

    if "INSS" in texto or "DCTFWEB" in texto:
        if "DCTFWEB" in texto:
            grupos["inss"]["dctfweb"] = caminho_absoluto
        else:
            grupos["inss"]["guia_inss"] = caminho_absoluto
        return

    if "FGTS" in texto:
        if "DIGITAL" in arquivo:
            grupos["fgts"]["relatorio_fgts"] = caminho_absoluto
        elif "GUIA" in arquivo or "COMPROVANTE" in arquivo:
            grupos["fgts"]["guia_fgts"] = caminho_absoluto
        else:
            grupos["fgts"]["guia_fgts"] = caminho_absoluto
        return

    if "CERTID" in texto or "CND" in texto or "CNDT" in texto or "CRF" in texto:
        grupos["cnd"].setdefault("cnds", []).append(caminho_absoluto)
        return

    if "VALE TRANSPORTE" in texto:
        grupos["vt"].setdefault("comprovantes", []).append(caminho_absoluto)
        return

    if "VALE ALIMENTACAO" in texto or "VALE ALIMENTAÇÃO" in texto:
        grupos["va"].setdefault("comprovantes", []).append(caminho_absoluto)
        return

    if "SEGURO" in texto or "APOLICE" in texto or "APÓLICE" in texto:
        grupos["seguro_vida"].setdefault("comprovantes", []).append(caminho_absoluto)
        return

    grupos["nao_classificados"].append(caminho_absoluto)


def _nome(path):
    return os.path.basename(path) if path else ""


def _resumo_grupos(grupos):
    def _somente_validos(lista):
        return [item for item in lista if item]

    return {
        "cartao_ponto": _somente_validos([_nome(grupos["cartao_ponto"].get("file"))]),
        "folha_pagamento": _somente_validos([_nome(grupos["folha_pagamento"].get("file"))]),
        "holerite": _somente_validos([
            *[_nome(p) for p in grupos["holerite"].get("holerites", [])],
            *[_nome(p) for p in grupos["holerite"].get("comprovantes", [])],
        ]),
        "inss": _somente_validos([_nome(grupos["inss"].get("guia_inss")), _nome(grupos["inss"].get("dctfweb"))]),
        "fgts": _somente_validos([_nome(grupos["fgts"].get("relatorio_fgts")), _nome(grupos["fgts"].get("guia_fgts"))]),
        "cnd": _somente_validos([_nome(p) for p in grupos["cnd"].get("cnds", [])]),
        "vt": _somente_validos([_nome(p) for p in grupos["vt"].get("comprovantes", [])]),
        "va": _somente_validos([_nome(p) for p in grupos["va"].get("comprovantes", [])]),
        "seguro_vida": _somente_validos([_nome(p) for p in grupos["seguro_vida"].get("comprovantes", [])]),
        "nao_classificados": _somente_validos([_nome(p) for p in grupos["nao_classificados"]]),
    }


def _carregar_regras_assinatura_csv():
    caminho = os.path.join(os.getcwd(), "regras_assinatura_iniciais.csv")
    if not os.path.exists(caminho):
        return {}

    regras = {}
    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f):
            arquivo = _normalizar_basico(linha.get("arquivo_modelo", ""))
            if not arquivo:
                continue
            regra = {
                "assinatura_obrigatoria": (linha.get("assinatura_obrigatoria") or "").strip().lower() == "sim",
                "quem_assina": (linha.get("quem_assina") or "").strip(),
                "observacao_inicial": (linha.get("observacao_inicial") or "").strip(),
            }
            regras[arquivo] = regra
            regras.setdefault(os.path.basename(arquivo), regra)
    return regras


def _mapear_regras_assinatura_por_documento_classificado(grupos):
    regras_csv = _carregar_regras_assinatura_csv()
    if not regras_csv:
        return {}

    mapeamento = {}
    for chave, arquivos in _resumo_grupos(grupos).items():
        if chave == "nao_classificados":
            continue
        selecionadas = []
        for nome_arquivo in arquivos:
            regra = regras_csv.get(_normalizar_basico(nome_arquivo))
            if regra:
                selecionadas.append({"arquivo": nome_arquivo, **regra})
        if selecionadas:
            mapeamento[chave] = selecionadas
    return mapeamento


def _resultado_item(nome, status, mensagem, resultado=None):
    return {
        "documento": nome,
        "status": status,
        "mensagem": mensagem,
        "resultado": resultado or {},
    }


def _grupos_vazios():
    return {
        "cartao_ponto": {},
        "folha_pagamento": {},
        "holerite": {"holerites": [], "comprovantes": []},
        "inss": {},
        "fgts": {},
        "cnd": {"cnds": []},
        "vt": {"comprovantes": []},
        "va": {"comprovantes": []},
        "seguro_vida": {"comprovantes": []},
        "nao_classificados": [],
    }


def _classificar_arquivos_em_pasta(raiz_base, grupos):
    competencia = None

    for raiz, _, arquivos in os.walk(raiz_base):
        for arquivo in arquivos:
            caminho_abs = os.path.join(raiz, arquivo)
            caminho_rel = os.path.relpath(caminho_abs, raiz_base)
            competencia = competencia or _competencia_por_caminho(caminho_rel) or _competencia_por_caminho(caminho_abs)
            if _arquivo_pdf(caminho_abs):
                _classificar(caminho_rel, caminho_abs, grupos)
            else:
                grupos["nao_classificados"].append(caminho_abs)

    return competencia


def _classificar_lista_arquivos(caminhos, grupos):
    caminhos = [str(caminho) for caminho in caminhos if caminho]
    if not caminhos:
        return None

    raiz_base = os.path.commonpath(caminhos)
    if os.path.isfile(raiz_base):
        raiz_base = os.path.dirname(raiz_base)

    competencia = None
    for caminho_abs in caminhos:
        caminho_rel = os.path.relpath(caminho_abs, raiz_base)
        competencia = competencia or _competencia_por_caminho(caminho_rel) or _competencia_por_caminho(caminho_abs)
        if _arquivo_pdf(caminho_abs):
            _classificar(caminho_rel, caminho_abs, grupos)
        else:
            grupos["nao_classificados"].append(caminho_abs)

    return competencia


def _executar_validacoes(grupos, competencia):
    validacoes = []

    if grupos["cartao_ponto"].get("file"):
        from services.cartao_ponto_service import processar_cartao_ponto

        validacoes.append(_resultado_item(
            "Cartao Ponto",
            "Processado",
            "Arquivo classificado e validado",
            processar_cartao_ponto(grupos["cartao_ponto"]["file"], competencia),
        ))

    if grupos["folha_pagamento"].get("file"):
        from services.folha_service import processar_folha_pagamento

        validacoes.append(_resultado_item(
            "Folha de Pagamento",
            "Processado",
            "Arquivo classificado e validado",
            processar_folha_pagamento(grupos["folha_pagamento"]["file"], competencia),
        ))

    if grupos["holerite"].get("holerites") and grupos["holerite"].get("comprovantes"):
        from services.holerite_service import processar_holerite_comprovante

        validacoes.append(_resultado_item(
            "Holerite + Comprovante",
            "Processado",
            "Arquivos classificados e validados",
            processar_holerite_comprovante(
                grupos["holerite"]["holerites"],
                grupos["holerite"]["comprovantes"],
                competencia,
            ),
        ))

    if grupos["fgts"].get("relatorio_fgts") and grupos["fgts"].get("guia_fgts"):
        from validators.fgts import FGTSValidator

        validacoes.append(_resultado_item(
            "FGTS",
            "Processado",
            "Arquivos classificados e validados",
            FGTSValidator().analisar(
                grupos["fgts"]["relatorio_fgts"],
                grupos["fgts"]["guia_fgts"],
                competencia,
            ),
        ))

    if groups_inss_ok := (grupos["inss"].get("guia_inss") and grupos["inss"].get("dctfweb")):
        from services.inss_service import processar_inss

        validacoes.append(_resultado_item(
            "INSS",
            "Processado",
            "Arquivos classificados e validados",
            processar_inss(
                grupos["inss"]["guia_inss"],
                grupos["inss"]["dctfweb"],
                competencia,
            ),
        ))

    if grupos["va"].get("comprovantes"):
        from validators.vale_alimentacao.validator import VAValidator

        validacoes.append(_resultado_item(
            "Vale Alimentacao",
            "Processado",
            "Arquivos classificados e validados",
            VAValidator().analisar(grupos["va"]["comprovantes"]),
        ))

    return validacoes


def importar_pacote(caminhos_pacote):
    if not caminhos_pacote:
        return {
            "status": "Processado",
            "mensagem": "Sem arquivos enviados. Nenhuma validacao executada.",
            "competencia": None,
            "documentos_classificados": _resumo_grupos(_grupos_vazios()),
            "validacoes": [],
            "regras_assinatura_referencia": {},
        }

    if isinstance(caminhos_pacote, str):
        caminhos_pacote = [caminhos_pacote]

    grupos = {
        **_grupos_vazios()
    }

    zip_paths = [caminho for caminho in caminhos_pacote if zipfile.is_zipfile(caminho)]
    if zip_paths:
        with tempfile.TemporaryDirectory(prefix="mse-pacote-") as temp_dir:
            with zipfile.ZipFile(zip_paths[0]) as pacote:
                pacote.extractall(temp_dir)
            competencia = _classificar_arquivos_em_pasta(temp_dir, grupos)
            validacoes = _executar_validacoes(grupos, competencia)
    else:
        competencia = _classificar_lista_arquivos(caminhos_pacote, grupos)
        validacoes = _executar_validacoes(grupos, competencia)

    regras_assinatura = _mapear_regras_assinatura_por_documento_classificado(grupos)

    mensagem = f"{len(validacoes)} validacao(oes) executada(s)"
    if not validacoes:
        mensagem = "Sem PDF compativel para validacao. Envie os documentos em PDF para processar."

    return {
        "status": "Processado",
        "mensagem": mensagem,
        "competencia": competencia,
        "documentos_classificados": _resumo_grupos(grupos),
        "validacoes": validacoes,
        "regras_assinatura_referencia": regras_assinatura,
    }
