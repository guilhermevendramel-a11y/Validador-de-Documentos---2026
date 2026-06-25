import unittest
from unittest.mock import patch

from validators.inss.dctfweb import validar_dctfweb
from validators.inss.validator import INSSValidator


class TestINSSSimulado(unittest.TestCase):
    def test_validar_dctfweb_mantem_relatorio_creditos_como_falso_quando_ausente(self):
        texto = """
        RECIBO DE ENTREGA DA DCTFWEB
        DECLARACAO COMPLETA
        RELATORIO DE DEBITOS
        """

        dados = validar_dctfweb(texto, "04/2026")

        self.assertFalse(dados["relatorio_creditos"])

    def test_validar_dctfweb_prioriza_valor_total_do_debito(self):
        texto = """
        DCTFWEB
        PERIODO DE APURACAO 05/2026
        SALDO A PAGAR 3.105,73
        TOTAL R$ 56.554,26 R$ 56.554,26
        RECIBO DE ENTREGA
        DECLARACAO COMPLETA
        RELATORIO DE DEBITOS
        """

        dados = validar_dctfweb(texto, "05/2026")

        self.assertEqual(dados["valor"], "56.554,26")
        self.assertEqual(dados["valor_float"], 56554.26)

    @patch("validators.inss.validator.extrair_texto_inss")
    @patch("validators.inss.validator.validar_dctfweb")
    @patch("validators.inss.validator.validar_guia_comprovante")
    def test_inss_validator_aceita_dctf_sem_relatorio_creditos(
        self,
        mock_validar_guia_comprovante,
        mock_validar_dctfweb,
        mock_extrair_texto_inss,
    ):
        mock_extrair_texto_inss.side_effect = [
            "GUIA INSS\nEMPRESA TESTE LTDA\nVALOR: R$ 100,00",
            "DCTFWEB\nEMPRESA TESTE LTDA\nRECIBO DE ENTREGA\nDECLARACAO COMPLETA\nRELATORIO DE DEBITOS",
        ]
        mock_validar_guia_comprovante.return_value = {
            "empresa": "EMPRESA TESTE LTDA",
            "empresa_nome": "EMPRESA TESTE LTDA",
            "cnpj": "00.000.000/0001-00",
            "competencia": "04/2026",
            "valor_guia": 100.0,
            "valor_comprovante": 100.0,
            "data_pagamento": "05/04/2026",
            "pagamento_identificado": True,
            "valor": 100.0,
            "erro": False,
        }
        mock_validar_dctfweb.return_value = {
            "empresa": "EMPRESA TESTE LTDA",
            "empresa_nome": "EMPRESA TESTE LTDA",
            "cnpj": "00.000.000/0001-00",
            "competencia": "04/2026",
            "valor": "100,00",
            "valor_float": 100.0,
            "recibo_entrega": True,
            "relatorio_debitos": True,
            "relatorio_creditos": False,
            "declaracao_completa": True,
            "resumo_debitos": True,
            "declaracao": True,
        }

        resultado = INSSValidator().analisar("guia.pdf", "dctf.pdf", "04/2026")

        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["relatorio_creditos_ok"], "NA")
        self.assertTrue(resultado["estrutura_dctf_ok"])
        self.assertFalse(any("Creditos" in erro or "Cr" in erro for erro in resultado["erros"]))
        self.assertTrue(
            any(
                str(item.get("item", "")).lower().startswith("relat")
                and item.get("ok") == "NA"
                for item in resultado["validacoes"]
            )
        )

    def test_inss_validator_aprova_empresa_quando_nome_e_identificado_nos_dois_documentos(self):
        texto_guia = """
        GUIA INSS
        RAZAO SOCIAL: FNEC CONSULTORIA E SERVICOS TECNICOS LTDA
        CNPJ: 22.958.374/0001-57
        PERIODO DE APURACAO 05/2026
        VALOR TOTAL DO DOCUMENTO
        56.554,26
        COMPROVANTE DE PAGAMENTO
        VALOR PAGO: 56.554,26
        PAGO EM 20/06/2026
        """
        texto_dctf = """
        DCTFWEB
        NOME DO CONTRIBUINTE FNEC CONSULTORIA E SERVICOS TECNICOS LTDA
        CNPJ 22.958.374/0001-57
        PERIODO DE APURACAO 05/2026
        TOTAL R$ 56.554,26
        RECIBO DE ENTREGA
        DECLARACAO COMPLETA
        RELATORIO DE DEBITOS
        """

        with patch("validators.inss.validator.extrair_texto_inss", side_effect=[texto_guia, texto_dctf]):
            resultado = INSSValidator().analisar("guia.pdf", "dctf.pdf", "05/2026")

        self.assertEqual(resultado["empresa"], "FNEC CONSULTORIA E SERVICOS TECNICOS LTDA")
        self.assertTrue(resultado["empresa_ok"])
        self.assertEqual(
            next(item for item in resultado["validacoes"] if item["item"] == "Empresa")["ok"],
            True,
        )
        self.assertEqual(resultado["status"], "Aprovado")


if __name__ == "__main__":
    unittest.main()
