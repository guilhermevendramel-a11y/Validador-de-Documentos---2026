import unittest
from unittest.mock import patch

from validators.fgts.rules import validar_fgts
from validators.fgts.secoes import validar_secoes
from validators.fgts.validator import FGTSValidator


class TestFGTSSimulado(unittest.TestCase):
    def test_validar_secoes_reconhece_tomadores_de_servico(self):
        texto = """
        RELAÇÃO DE TRABALHADORES
        RELAÇÃO DE CATEGORIAS
        RELAÇÃO DE ESTABELECIMENTOS
        RELAÇÃO DE TIPOS DE VALOR
        RELAÇÃO DE TOMADORES DE SERVIÇO
        """

        secoes = validar_secoes(texto)

        self.assertTrue(secoes["Relação de Trabalhadores"])
        self.assertTrue(secoes["Relação de Categorias"])
        self.assertTrue(secoes["Relação de Estabelecimentos"])
        self.assertTrue(secoes["Relação de Tipos de Valor"])
        self.assertTrue(secoes["Relação de Tomadores"])

    def test_validar_fgts_trata_tomadores_como_excecao(self):
        relatorio = {
            "empresa": "EMPRESA TESTE LTDA",
            "competencia": "04/2026",
            "valor_total": 100.0,
            "documentos_detectados": {
                "relacao_trabalhadores": True,
                "relacao_categorias": True,
                "relacao_estabelecimentos": True,
                "relacao_tipo_valor": True,
                "relacao_tomadores": False,
            },
            "tomadores": [],
        }
        guia = {
            "empresa": "EMPRESA TESTE LTDA",
            "competencia": "04/2026",
            "valor_total": 100.0,
            "data_pagamento": "05/04/2026",
        }

        resultado = validar_fgts(relatorio, guia, {}, "04/2026")

        self.assertEqual(resultado["status"], "Parcial")
        self.assertTrue(any("Tomadores de Serviço" in aviso for aviso in resultado["avisos"]))
        self.assertFalse(any("Tomador" in erro for erro in resultado["erros"]))

    @patch("validators.fgts.validator.extrair_colaboradores_fgts_digital", return_value=[{"nome": "JOAO"}])
    @patch(
        "validators.fgts.validator.validar_secoes",
        return_value={
            "Relação de Trabalhadores": True,
            "Relação de Categorias": True,
            "Relação de Estabelecimentos": True,
            "Relação de Tipos de Valor": True,
            "Relação de Tomadores": False,
        },
    )
    @patch(
        "validators.fgts.validator.extrair_resumo_guia_comprovante",
        return_value={
            "empresa": "EMPRESA TESTE LTDA",
            "competencia": "04/2026",
            "valor_guia": 100.0,
            "valor_comprovante": 100.0,
            "data_pagamento": "05/04/2026",
        },
    )
    @patch(
        "validators.fgts.validator.extrair_resumo_fgts_digital",
        return_value={
            "empresa": "EMPRESA TESTE LTDA",
            "competencia": "04/2026",
            "valor_total": 100.0,
            "tomadores": [],
        },
    )
    @patch("validators.fgts.validator.extrair_texto_fgts", return_value="texto fgts")
    def test_fgts_validator_nao_reprova_quando_tomadores_nao_aparecem(
        self,
        _mock_texto,
        _mock_resumo_rel,
        _mock_resumo_guia,
        _mock_validar_secoes,
        _mock_colaboradores,
    ):
        resultado = FGTSValidator().analisar("relatorio.pdf", "guia.pdf", "04/2026")

        self.assertEqual(resultado["status"], "Parcial")
        self.assertTrue(any("Tomadores de Serviço" in aviso for aviso in resultado["avisos"]))
        self.assertFalse(any("Tomador" in erro for erro in resultado["erros"]))


if __name__ == "__main__":
    unittest.main()
