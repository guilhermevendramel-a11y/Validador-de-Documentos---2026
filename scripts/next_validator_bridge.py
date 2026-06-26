import json
import os
import sys
import traceback
from contextlib import redirect_stdout

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def status_texto(valor):
    if isinstance(valor, bool):
        return "OK" if valor else "Pendente"
    if isinstance(valor, str) and valor.upper() == "NA":
        return "NA"
    if valor is None or valor == "":
        return "-"
    return str(valor)


def valor_formatado(valor):
    if isinstance(valor, bool):
        return "Sim" if valor else "Nao"
    if valor is None or valor == "":
        return "-"
    return valor


def add_resumo(rows, label, valor, ok=None):
    if valor is None or valor == "":
        return
    row = {"campo": label, "valor": valor_formatado(valor)}
    if ok is not None:
        row["status"] = status_texto(ok)
    rows.append(row)


def colunas_objetos(items, preferidas=None):
    preferidas = preferidas or []
    colunas = []
    for coluna in preferidas:
        if any(isinstance(item, dict) and coluna in item for item in items):
            colunas.append(coluna)
    for item in items:
        if not isinstance(item, dict):
            continue
        for coluna in item.keys():
            if coluna not in colunas:
                colunas.append(coluna)
    return colunas


def montar_data_table(resultado, endpoint=None):
    if not isinstance(resultado, dict):
        return []

    tabelas = []
    resumo = []
    add_resumo(resumo, "Status", resultado.get("status"))
    add_resumo(resumo, "Mensagem", resultado.get("mensagem"))
    add_resumo(resumo, "Empresa", resultado.get("empresa"), resultado.get("empresa_ok"))
    add_resumo(resumo, "Competencia", resultado.get("competencia"), resultado.get("competencia_ok"))
    add_resumo(resumo, "Data Pagamento", resultado.get("data_pagamento"))
    add_resumo(resumo, "Tomador informado", resultado.get("tomador_informado"), resultado.get("tomador_ok"))
    add_resumo(resumo, "Valor FGTS", resultado.get("valor_fgts_digital") or resultado.get("valor_a_pagar"), resultado.get("valor_ok"))
    add_resumo(resumo, "Valor INSS", resultado.get("valor_inss") or resultado.get("valor_guia"), resultado.get("valor_ok"))
    add_resumo(resumo, "Valor Guia", resultado.get("valor_guia"), resultado.get("valor_ok"))
    add_resumo(resumo, "Valor Comprovante", resultado.get("valor_comprovante"), resultado.get("guia_comprovante_ok") if "guia_comprovante_ok" in resultado else resultado.get("comprovante_ok"))
    add_resumo(resumo, "Valor DCTF", resultado.get("valor_dctf"), resultado.get("valor_ok"))
    add_resumo(resumo, "Nome no holerite", resultado.get("nome_holerite"))
    add_resumo(resumo, "Nome no comprovante", resultado.get("nome_comprovante"))
    add_resumo(resumo, "Valor no holerite", resultado.get("valor_holerite"))

    if resumo:
        tabelas.append({
            "titulo": "Resumo",
            "columns": ["campo", "valor", "status"],
            "rows": resumo,
        })

    documentos = resultado.get("documentos")
    if isinstance(documentos, dict) and documentos:
        ordem_fgts = [
            "Relação de Trabalhadores",
            "Relação de Categorias",
            "Relação de Estabelecimentos",
            "Relação de Tipos de Valor",
            "Relação de Tomadores de Serviço",
        ]
        chaves = [chave for chave in ordem_fgts if chave in documentos]
        chaves.extend([chave for chave in documentos.keys() if chave not in chaves])
        tabelas.append({
            "titulo": "Documentos",
            "columns": ["documento", "status"],
            "rows": [{"documento": chave, "status": status_texto(documentos.get(chave))} for chave in chaves],
        })

    validacoes = None if endpoint in ("va", "vt") else (resultado.get("validacoes") or resultado.get("linhas"))
    if isinstance(validacoes, list) and validacoes:
        validacoes_rows = []
        for item in validacoes:
            if isinstance(item, dict):
                if set(item.keys()) - {"item", "ok"}:
                    validacoes_rows.append({chave: valor_formatado(valor) for chave, valor in item.items()})
                else:
                    validacoes_rows.append({
                        "item": item.get("item", item.get("campo", "")),
                        "status": status_texto(item.get("ok")) if "ok" in item else "-",
                    })
            else:
                validacoes_rows.append({"item": str(item), "status": "-"})

        tabelas.append({
            "titulo": "Validacoes",
            "columns": colunas_objetos(validacoes_rows, ["item", "razao_social", "cnpj", "validade", "competencia_conferencia", "status", "motivo"]),
            "rows": validacoes_rows,
        })

    colaboradores = resultado.get("colaboradores") or resultado.get("trabalhadores")
    if isinstance(colaboradores, list) and colaboradores:
        linhas = []
        for item in colaboradores:
            if isinstance(item, dict):
                nome = item.get("nome") or item.get("nome_colaborador") or item.get("colaborador") or ""
            else:
                nome = item

            if endpoint in ("va", "vt"):
                nome = str(nome or "").strip()
                if nome:
                    linhas.append({"nome": nome})
                continue

            if isinstance(item, dict):
                linhas.append({chave: valor_formatado(valor) for chave, valor in item.items()})
            else:
                linhas.append({"nome": str(item)})
        tabelas.append({
            "titulo": "Colaboradores",
            "columns": ["nome"] if endpoint in ("va", "vt") else (
                ["nome", "tipo_documento", "valor_base", "valor_recibo", "valor_comprovante", "valor_nf", "diferenca", "conferencia", "status", "detalhe", "fluxo", "assinatura_digital"]
                if endpoint == "vt"
                else colunas_objetos(
                    linhas,
                    [
                        "nome",
                        "competencia",
                        "competencia_ok",
                        "marcacoes",
                        "assinatura",
                        "assinatura_tipo",
                        "assinatura_origem",
                        "assinatura_confianca",
                        "assinatura_paginas",
                        "assinatura_bbox",
                        "assinatura_zona",
                        "assinatura_motivo",
                        "tomador",
                        "valor_fgts",
                        "valor",
                        "holerite",
                        "comprovante",
                        "diferenca",
                    ],
                )
            ),
            "rows": linhas,
        })

    if endpoint == "vt":
        detalhes_vt = resultado.get("colaboradores_detalhados")
        if isinstance(detalhes_vt, list) and detalhes_vt:
            tabelas.append({
                "titulo": "Conferencia VT",
                "columns": colunas_objetos(
                    detalhes_vt,
                    [
                        "nome",
                        "tipo_documento",
                        "valor_base",
                        "valor_recibo",
                        "valor_comprovante",
                        "valor_nf",
                        "diferenca",
                        "conferencia",
                        "status",
                        "detalhe",
                        "fluxo",
                        "assinatura_digital",
                    ],
                ),
                "rows": [
                    {chave: valor_formatado(valor) for chave, valor in item.items()}
                    for item in detalhes_vt
                    if isinstance(item, dict)
                ],
            })

    anexos = resultado.get("anexos")
    if isinstance(anexos, list) and anexos:
        tabelas.append({
            "titulo": "Anexos",
            "columns": colunas_objetos(anexos, ["destino", "arquivos"]),
            "rows": anexos,
        })

    erros = resultado.get("erros")
    if isinstance(erros, list) and erros:
        tabelas.append({
            "titulo": "Erros",
            "columns": ["erro"],
            "rows": [{"erro": erro} for erro in erros],
        })

    avisos = resultado.get("avisos")
    if isinstance(avisos, list) and avisos:
        tabelas.append({
            "titulo": "Avisos",
            "columns": ["aviso"],
            "rows": [{"aviso": aviso} for aviso in avisos],
        })

    return tabelas


def formatar_resposta_universal(resultado, endpoint=None):
    if not isinstance(resultado, dict):
        resposta = {
            "status": "Erro",
            "mensagem": "Resultado invalido",
            "trabalhadores": [],
            "documentos": {},
        }
        resposta["data_table"] = montar_data_table(resposta, endpoint)
        return resposta

    resultado.setdefault("status", "Erro")
    resultado.setdefault("mensagem", "")
    resultado.setdefault("empresa", "")
    resultado.setdefault("competencia", "")
    resultado.setdefault("valor", 0)
    resultado.setdefault("data_pagamento", "")
    resultado.setdefault("trabalhadores", [])
    resultado.setdefault("colaboradores", [])
    resultado.setdefault("documentos", {})
    resultado["data_table"] = montar_data_table(resultado, endpoint)
    return resultado


def validar(payload):
    endpoint = payload.get("endpoint")
    fields = payload.get("fields") or {}
    files = payload.get("files") or {}

    if endpoint == "cartao_ponto":
        from services.cartao_ponto_service import processar_cartao_ponto

        return processar_cartao_ponto(
            files.get("file"),
            competencia_esperada=fields.get("competencia"),
        )

    if endpoint == "fgts":
        from validators.fgts import FGTSValidator

        return FGTSValidator().analisar(
            files.get("relatorio_fgts"),
            files.get("guia_fgts"),
            fields.get("competencia"),
            fields.get("tomador"),
        )

    if endpoint == "inss":
        from services.inss_service import processar_inss

        return processar_inss(
            files.get("guia_inss"),
            files.get("dctfweb"),
            fields.get("competencia"),
        )

    if endpoint == "folha_pagamento":
        from services.folha_service import processar_folha_pagamento

        return processar_folha_pagamento(
            files.get("file"),
            fields.get("competencia"),
        )

    if endpoint == "holerite":
        from services.holerite_service import processar_holerite_comprovante

        return processar_holerite_comprovante(
            files.get("holerite"),
            files.get("comprovantes") or [],
            fields.get("competencia"),
        )

    if endpoint == "pacote_documentos":
        from services.package_import_service import importar_pacote

        return importar_pacote(files.get("pacote") or [])

    if endpoint == "kit_rescisao":
        from validators.rescisao.validator import RescisaoValidator

        return RescisaoValidator().analisar(
            files.get("kit_unico"),
            fields.get("nome_colaborador", ""),
        )

    if endpoint == "cnd":
        from validators.certidoes.validator import CNDValidator

        return CNDValidator().analisar(
            files.get("cnds") or [],
            fields.get("cnpj_esperado", ""),
            fields.get("competencia"),
        )

    if endpoint == "cnd_inss":
        from validators.certidoes.validator import CNDValidator

        return CNDValidator().analisar(
            [files.get("cnd_inss")] if files.get("cnd_inss") else [],
            fields.get("cnpj_esperado", ""),
            fields.get("competencia"),
            {"CND INSS / CND Federal"},
        )

    if endpoint == "cndt":
        from validators.certidoes.validator import CNDValidator

        return CNDValidator().analisar(
            [files.get("cndt")] if files.get("cndt") else [],
            fields.get("cnpj_esperado", ""),
            fields.get("competencia"),
            {"CNDT"},
        )

    if endpoint == "crf_fgts":
        from validators.certidoes.validator import CNDValidator

        return CNDValidator().analisar(
            [files.get("crf_fgts")] if files.get("crf_fgts") else [],
            fields.get("cnpj_esperado", ""),
            fields.get("competencia"),
            {"CRF FGTS"},
        )

    if endpoint == "seguro_vida":
        from validators.seguro_vida.validator import SeguroVidaValidator

        return SeguroVidaValidator().analisar(
            files.get("comprovantes") or [],
        )

    if endpoint == "vt":
        from validators.vale_transporte.validator import VTValidator

        return VTValidator().analisar(
            files.get("comprovantes") or [],
        )

    if endpoint == "va":
        from validators.vale_alimentacao.validator import VAValidator

        return VAValidator().analisar(
            files.get("comprovantes") or [],
        )

    return {"status": "Erro", "mensagem": f"Endpoint desconhecido: {endpoint}"}


def main():
    try:
        payload = json.loads(sys.argv[1])
        with redirect_stdout(sys.stderr):
            resultado = formatar_resposta_universal(validar(payload), payload.get("endpoint"))
        print(json.dumps(resultado, ensure_ascii=False))
    except Exception as exc:
        resultado = {
            "status": "Erro",
            "mensagem": "Erro no processamento Python",
            "detalhe": str(exc),
            "traceback": traceback.format_exc(),
        }
        resultado["data_table"] = montar_data_table(resultado)
        print(
            json.dumps(
                resultado,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
