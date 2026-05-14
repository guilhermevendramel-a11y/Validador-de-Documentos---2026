import json
import os
import sys
import traceback
from contextlib import redirect_stdout

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def formatar_resposta_universal(resultado):
    if not isinstance(resultado, dict):
        return {
            "status": "Erro",
            "mensagem": "Resultado invalido",
            "trabalhadores": [],
            "documentos": {},
        }

    resultado.setdefault("status", "Erro")
    resultado.setdefault("mensagem", "")
    resultado.setdefault("empresa", "")
    resultado.setdefault("competencia", "")
    resultado.setdefault("valor", 0)
    resultado.setdefault("data_pagamento", "")
    resultado.setdefault("trabalhadores", [])
    resultado.setdefault("colaboradores", [])
    resultado.setdefault("documentos", {})
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
            resultado = formatar_resposta_universal(validar(payload))
        print(json.dumps(resultado, ensure_ascii=False))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "Erro",
                    "mensagem": "Erro no processamento Python",
                    "detalhe": str(exc),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
