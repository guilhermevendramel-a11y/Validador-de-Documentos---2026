import unittest
from unittest.mock import patch

from validators.seguro_vida.validator import SeguroVidaValidator


class TestSeguroVidaSimulado(unittest.TestCase):
    def test_analisar_detecta_comprovante_na_ultima_pagina_da_apolice(self):
        texto_apolice = """
        APOLICE COLETIVA
        RAZAO SOCIAL: FNEC CONSULTORIA E SERVICOS TECNICOS LTDA
        CNPJ 22.958.374/0001-57
        INICIO DE VIGENCIA 01/08/2025
        FIM DE VIGENCIA 31/07/2026

        \f
        CLAUSULAS GERAIS

        \f
        COMPROVANTE DE PAGAMENTO
        VALOR DO PAGAMENTO R$ 1.417,10
        DATA DE PAGAMENTO 31/07/2026
        AUTENTICACAO SISBB
        """

        with patch(
            "validators.seguro_vida.validator.extrair_texto_pdf_inteligente",
            return_value=texto_apolice,
        ):
            resultado = SeguroVidaValidator().analisar(["apolice.pdf"])

        self.assertEqual(resultado["tipo_apolice"], "GLOBAL")
        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["colaboradores"][0]["nome"], "APOLICE GLOBAL")
        self.assertTrue(resultado["colaboradores"][0]["comprovante_pagamento"])
        self.assertAlmostEqual(resultado["colaboradores"][0]["valor_comprovante"], 1417.10)
        self.assertEqual(
            next(v for v in resultado["validacoes"] if v["item"] == "Comprovante(s) de pagamento")["status"],
            "OK",
        )

    def test_analisar_mantem_comprovante_separado(self):
        texto_apolice = """
        APOLICE COLETIVA
        RAZAO SOCIAL: FNEC CONSULTORIA E SERVICOS TECNICOS LTDA
        CNPJ 22.958.374/0001-57
        INICIO DE VIGENCIA 01/08/2025
        FIM DE VIGENCIA 31/07/2026
        """
        texto_comprovante = """
        COMPROVANTE DE PAGAMENTO
        VALOR DO PAGAMENTO R$ 1.417,10
        DATA DE PAGAMENTO 31/07/2026
        """

        def _extrair_texto(path):
            return texto_apolice if path == "apolice.pdf" else texto_comprovante

        with patch(
            "validators.seguro_vida.validator.extrair_texto_pdf_inteligente",
            side_effect=_extrair_texto,
        ):
            resultado = SeguroVidaValidator().analisar(["apolice.pdf", "comprovante.pdf"])

        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["colaboradores"][0]["nome"], "APOLICE GLOBAL")
        self.assertTrue(resultado["colaboradores"][0]["comprovante_pagamento"])
        self.assertAlmostEqual(resultado["colaboradores"][0]["valor_comprovante"], 1417.10)
        self.assertEqual(
            next(v for v in resultado["validacoes"] if v["item"] == "Comprovante(s) de pagamento")["status"],
            "OK",
        )


if __name__ == "__main__":
    unittest.main()
