import unittest
from unittest.mock import patch

from validators.vale_transporte.validator import VTValidator


class TestValeTransporteSimulado(unittest.TestCase):
    def test_analisar_termo_nao_optante_valida_primeiro(self):
        texto = """
        TERMO DE NAO OPTANTE DO VALE TRANSPORTE
        EU, MILTON JORGE CUSTODIO, DECLARO QUE NAO UTILIZAREI O VALE TRANSPORTE
        ASSINATURA DIGITALIZADA
        """

        with (
            patch("validators.vale_transporte.validator._extrair_textos_paginas_pdf", return_value=[texto]),
            patch("validators.vale_transporte.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_transporte.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": True},
            ),
        ):
            resultado = VTValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["fluxo_aplicado"], "termo_nao_optante")
        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["colaboradores"], [{"nome": "Milton Jorge Custodio"}])
        self.assertEqual(resultado["colaboradores_detalhados"][0]["tipo_documento"], "termo_nao_optante")
        self.assertEqual(resultado["validacoes"][0]["fluxo"], "termo_nao_optante")
        self.assertEqual(resultado["validacoes"][0]["status"], "OK")

    def test_analisar_recibo_e_comprovante_compara_valores(self):
        texto = """
        RECIBO VALE TRANSPORTE
        NOME: MILTON JORGE CUSTODIO
        VALOR RECEBIDO R$ 147,00

        COMPROVANTE DE TRANSFERENCIA
        NOME: MILTON JORGE CUSTODIO
        VALOR R$ 147,00
        """

        with (
            patch("validators.vale_transporte.validator._extrair_textos_paginas_pdf", return_value=[texto]),
            patch("validators.vale_transporte.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_transporte.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VTValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["fluxo_aplicado"], "recibo_comprovante")
        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["colaboradores"], [{"nome": "Milton Jorge Custodio"}])
        self.assertEqual(resultado["colaboradores_detalhados"][0]["tipo_documento"], "recibo_comprovante")
        self.assertEqual(resultado["colaboradores_detalhados"][0]["valor_base"], 147.0)
        self.assertEqual(resultado["colaboradores_detalhados"][0]["valor_comprovante"], 147.0)
        self.assertEqual(resultado["colaboradores_detalhados"][0]["conferencia"], "OK")
        self.assertEqual(resultado["validacoes"][0]["fluxo"], "recibo_comprovante")
        self.assertEqual(resultado["validacoes"][0]["valor_recibo"], 147.0)
        self.assertEqual(resultado["validacoes"][0]["valor_comprovante"], 147.0)
        self.assertEqual(resultado["validacoes"][0]["status"], "OK")

    def test_analisar_nota_fiscal_com_declaracao_e_comprovante(self):
        texto = """
        NOTA FISCAL ELETRONICA
        VALOR TOTAL R$ 485,00
        DECLARACAO DE COLABORADORES
        MILTON JORGE CUSTODIO
        COMPROVANTE DE PAGAMENTO
        VALOR R$ 485,00
        """

        with (
            patch("validators.vale_transporte.validator._extrair_textos_paginas_pdf", return_value=[texto]),
            patch("validators.vale_transporte.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_transporte.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VTValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["fluxo_aplicado"], "nf_declaracao_comprovante")
        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["colaboradores"], [{"nome": "Milton Jorge Custodio"}])
        self.assertEqual(resultado["colaboradores_detalhados"][0]["tipo_documento"], "nota_fiscal")
        self.assertEqual(resultado["colaboradores_detalhados"][0]["valor_base"], 485.0)
        self.assertEqual(resultado["colaboradores_detalhados"][0]["valor_comprovante"], 485.0)
        self.assertEqual(resultado["colaboradores_detalhados"][0]["conferencia"], "OK")
        self.assertEqual(resultado["validacoes"][0]["fluxo"], "nf_declaracao_comprovante")
        self.assertEqual(resultado["validacoes"][0]["valor_nf"], 485.0)
        self.assertEqual(resultado["validacoes"][0]["valor_comprovante"], 485.0)
        self.assertEqual(resultado["validacoes"][0]["status"], "OK")

    def test_analisar_lista_varios_colaboradores_no_mesmo_pdf(self):
        texto = """
        TERMO DE DISPENSA DO VALE TRANSPORTE
        EU, MILTON JORGE CUSTODIO, DECLARO NAO UTILIZAREI O VALE TRANSPORTE
        EU, VINICIUS VICENTE FIRMINO BUZZO, DECLARO NAO UTILIZAREI O VALE TRANSPORTE
        ASSINATURA DIGITALIZADA
        """

        with (
            patch("validators.vale_transporte.validator._extrair_textos_paginas_pdf", return_value=[texto]),
            patch("validators.vale_transporte.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_transporte.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": True},
            ),
        ):
            resultado = VTValidator().analisar(["fake.pdf"])

        self.assertEqual(
            resultado["colaboradores"],
            [
                {"nome": "Milton Jorge Custodio"},
                {"nome": "Vinicius Vicente Firmino Buzzo"},
            ],
        )
        self.assertEqual(
            [c["tipo_documento"] for c in resultado["colaboradores_detalhados"]],
            ["termo_nao_optante", "termo_nao_optante"],
        )
        self.assertEqual(resultado["status"], "Aprovado")

    def test_analisar_ignora_razao_social_e_textos_operacionais(self):
        texto = """
        MSE ENGENHARIA LTDA
        IDENTIFICACAO NO EXTRATO: SISPAG SALARIOS
        FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
        IGOR AUGUSTO QUINTILIANO SILVA
        """

        with (
            patch("validators.vale_transporte.validator._extrair_textos_paginas_pdf", return_value=[texto]),
            patch("validators.vale_transporte.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_transporte.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VTValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["colaboradores"], [{"nome": "Igor Augusto Quintiliano Silva"}])
        self.assertEqual(resultado["colaboradores_detalhados"][0]["nome"], "Igor Augusto Quintiliano Silva")
        self.assertIn(resultado["colaboradores_detalhados"][0]["tipo_documento"], {"indefinido", "recibo_comprovante"})

    def test_analisar_ignora_frase_informacoes_fornecidas_pelo_e_nome_truncado(self):
        texto = """
        INFORMACOES FORNECIDAS PELO
        IGOR AUGUSTO QUINTILIANO SILVA
        IGOR AUGUSTO QUINTILIANO SIL
        COMPROVANTE DE TRANSFERENCIA
        VALOR R$ 548,00
        """

        with (
            patch("validators.vale_transporte.validator._extrair_textos_paginas_pdf", return_value=[texto]),
            patch("validators.vale_transporte.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_transporte.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VTValidator().analisar(["fake.pdf"])

        nomes = [item["nome"] for item in resultado["colaboradores"]]
        self.assertEqual(nomes, ["Igor Augusto Quintiliano Silva"])
        detalhes = [item["nome"] for item in resultado["colaboradores_detalhados"]]
        self.assertEqual(detalhes, ["Igor Augusto Quintiliano Silva"])

    def test_analisar_prioriza_termo_mesmo_com_recibo_e_comprovante_no_mesmo_texto(self):
        texto = """
        TERMO DE DISPENSA DO VALE TRANSPORTE
        EU, MILTON JORGE CUSTODIO, DECLARO NAO OPTAR PELO BENEFICIO
        RECIBO VALE TRANSPORTE
        COMPROVANTE DE TRANSFERENCIA
        """

        with (
            patch("validators.vale_transporte.validator._extrair_textos_paginas_pdf", return_value=[texto]),
            patch("validators.vale_transporte.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_transporte.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VTValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["fluxo_aplicado"], "termo_nao_optante")
        self.assertEqual(resultado["validacoes"][0]["fluxo"], "termo_nao_optante")
        self.assertEqual(resultado["validacoes"][0]["status"], "Pendente")
        self.assertIn("Termo de nao optante", resultado["validacoes"][0]["detalhe"])


if __name__ == "__main__":
    unittest.main()
