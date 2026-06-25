import unittest
from unittest.mock import patch

from scripts.next_validator_bridge import montar_data_table
from validators.vale_alimentacao.parser_va import extrair_dados_va
from validators.vale_alimentacao.validator import (
    VAValidator,
    _detectar_contexto_documental,
    _detectar_tipo_documento,
)


class TestValeAlimentacaoSimulado(unittest.TestCase):
    def test_extrair_dados_va_identifica_nome_e_valor_sem_cpf(self):
        texto = """
        RECIBO DE PAGAMENTO
        BENEFICIARIO: MILTON JORGE CUSTODIO
        VALOR PAGO R$ 147,00
        DATA: 01/06/2026
        """

        dados = extrair_dados_va(texto)

        self.assertEqual(len(dados["colaboradores"]), 1)
        self.assertEqual(dados["colaboradores"][0]["nome"], "Milton Jorge Custodio")
        self.assertEqual(len(dados["colaboradores_detalhados"]), 1)
        self.assertEqual(dados["colaboradores_detalhados"][0]["nome"], "Milton Jorge Custodio")
        self.assertEqual(dados["colaboradores_detalhados"][0]["valor"], 147.00)
        self.assertEqual(dados["soma_extraida"], 147.00)
        self.assertEqual(dados["total_documento"], 147.00)

    def test_extrair_dados_va_ignora_frases_que_nao_sao_nome(self):
        texto = """
        DECLARO PARA OS DEVIDOS FINS
        REFERENTE AO PERIODO DE 01/04/2026 A 30/04/2026
        BANCO ITAU - COMPROVANTE DE TRANSFERENCIA
        DADOS DA CONTA CREDITADA
        NOME: MILTON JORGE CUSTODIO
        VALOR: R$ 485,00
        """

        dados = extrair_dados_va(texto)
        nomes = [c["nome"] for c in dados["colaboradores"]]

        self.assertEqual(nomes, ["Milton Jorge Custodio"])
        self.assertEqual(dados["colaboradores_detalhados"][0]["valor"], 485.00)

    def test_detectar_tipo_documento_classifica_comprovante_sem_nf(self):
        texto = """
        COMPROVANTE DE PAGAMENTO
        NOME: MILTON JORGE CUSTODIO
        VALOR LIQUIDO R$ 147,00
        """

        self.assertEqual(_detectar_tipo_documento(texto), "comprovante_colaborador")

    def test_contexto_documental_prioriza_pedido_sobre_comprovante(self):
        texto = """
        PEDIDO DE VALE ALIMENTACAO
        COLABORADOR: MILTON JORGE CUSTODIO
        COMPROVANTE DE PAGAMENTO
        """

        contexto = _detectar_contexto_documental(texto, "")
        self.assertEqual(contexto["tipo_documento"], "pedido")

    def test_contexto_documental_prioriza_nota_fiscal_no_pacote(self):
        texto = """
        NOTA FISCAL ELETRONICA
        COMPROVANTE DE PAGAMENTO
        DECLARO O RECEBIMENTO DO VALE ALIMENTACAO
        """

        contexto = _detectar_contexto_documental(texto, "")
        self.assertEqual(contexto["tipo_documento"], "nota_fiscal")

    def test_analisar_preserva_valor_quando_tem_cpf(self):
        texto = """
        RECIBO DE PAGAMENTO
        NOME CPF ASSINATURA
        MILTON JORGE CUSTODIO 123.456.789-00
        VALOR PAGO R$ 147,00
        ASSINADO DIGITALMENTE
        """

        with (
            patch("validators.vale_alimentacao.validator.extrair_texto_pdf_inteligente", return_value=texto),
            patch("validators.vale_alimentacao.validator._extrair_texto_fallback_pdf", return_value=""),
            patch("validators.vale_alimentacao.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_alimentacao.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VAValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["tipo_documento"], "comprovante_colaborador")
        self.assertEqual(resultado["colaboradores"], [{"nome": "Milton Jorge Custodio"}])
        self.assertEqual(resultado["validacoes"][0]["colaborador"], "Milton Jorge Custodio")
        self.assertEqual(resultado["validacoes"][0]["valor"], 147.00)
        self.assertEqual(
            resultado["resumo_financeiro"]["valores_separados"],
            [{
                "nome": "Milton Jorge Custodio",
                "valor_recibo": 147.0,
                "valor_comprovante": 147.0,
                "valor": 147.0,
                "status": "OK",
                "detalhe": "Recibo e comprovante conferidos por colaborador",
            }],
        )
        self.assertEqual(resultado["status"], "Aprovado")

    def test_analisar_usa_fallback_openai_quando_ocr_nao_encontra_nome(self):
        texto = """
        RECIBO DE PAGAMENTO
        SEM TEXTO UTIL
        VALOR PAGO R$ 147,00
        """

        with (
            patch("validators.vale_alimentacao.validator.extrair_texto_pdf_inteligente", return_value=texto),
            patch("validators.vale_alimentacao.validator._extrair_texto_fallback_pdf", return_value=""),
            patch("validators.vale_alimentacao.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_alimentacao.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
            patch(
                "validators.vale_alimentacao.validator._extrair_colaboradores_openai",
                return_value=[{"nome": "Milton Jorge Custodio", "valor": 147.0}],
            ),
        ):
            resultado = VAValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["tipo_documento"], "comprovante_colaborador")
        self.assertEqual(resultado["colaboradores"], [{"nome": "Milton Jorge Custodio"}])
        self.assertEqual(resultado["validacoes"][0]["colaborador"], "Milton Jorge Custodio")
        self.assertEqual(resultado["validacoes"][0]["valor"], 147.00)
        self.assertEqual(
            resultado["resumo_financeiro"]["valores_separados"],
            [{
                "nome": "Milton Jorge Custodio",
                "valor_recibo": 147.0,
                "valor_comprovante": 147.0,
                "valor": 147.0,
                "status": "OK",
                "detalhe": "Recibo e comprovante conferidos por colaborador",
            }],
        )
        self.assertEqual(resultado["status"], "Aprovado")

    def test_analisar_extrai_competencia_do_documento(self):
        texto = """
        VALE ALIMENTACAO
        COMPETENCIA: 04/2026
        NOME: MILTON JORGE CUSTODIO
        VALOR: R$ 147,00
        """

        with (
            patch("validators.vale_alimentacao.validator.extrair_texto_pdf_inteligente", return_value=texto),
            patch("validators.vale_alimentacao.validator._extrair_texto_fallback_pdf", return_value=""),
            patch("validators.vale_alimentacao.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_alimentacao.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VAValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["competencia"], "04/2026")
        self.assertEqual(resultado["resumo_financeiro"]["competencia"], "04/2026")

    def test_analisar_nota_fiscal_exige_declaracao_e_comprovante(self):
        texto = """
        NOTA FISCAL ELETRONICA
        VALOR TOTAL DA NOTA R$ 485,00
        COMPROVANTE DE PAGAMENTO R$ 485,00
        DECLARO PARA OS DEVIDOS FINS
        NOME CPF ASSINATURA
        MILTON JORGE CUSTODIO 123.456.789-00
        ASSINADO DIGITALMENTE
        """

        with (
            patch("validators.vale_alimentacao.validator.extrair_texto_pdf_inteligente", return_value=texto),
            patch("validators.vale_alimentacao.validator._extrair_texto_fallback_pdf", return_value=""),
            patch("validators.vale_alimentacao.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_alimentacao.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": True},
            ),
        ):
            resultado = VAValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["tipo_documento"], "nota_fiscal")
        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["colaboradores"], [{"nome": "Milton Jorge Custodio"}])
        self.assertEqual(
            resultado["resumo_financeiro"]["valores_separados"],
            [{
                "nome": "Milton Jorge Custodio",
                "valor_recibo": 485.0,
                "valor_comprovante": 485.0,
                "valor": 485.0,
                "status": "OK",
                "detalhe": "Recibo e comprovante conferidos por colaborador",
            }],
        )
        self.assertTrue(resultado["resumo_financeiro"]["tem_declaracao"])
        self.assertTrue(resultado["resumo_financeiro"]["tem_recibo_ou_comprovante"])
        self.assertTrue(resultado["resumo_financeiro"]["valores_conferem"])

    def test_analisar_pedido_exige_colaboradores_e_comprovante(self):
        texto = """
        PEDIDO DE VALE ALIMENTACAO
        COLABORADOR: MILTON JORGE CUSTODIO
        VALOR TOTAL DO PEDIDO R$ 485,00
        COMPROVANTE DE PAGAMENTO R$ 485,00
        """

        with (
            patch("validators.vale_alimentacao.validator.extrair_texto_pdf_inteligente", return_value=texto),
            patch("validators.vale_alimentacao.validator._extrair_texto_fallback_pdf", return_value=""),
            patch("validators.vale_alimentacao.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_alimentacao.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VAValidator().analisar(["fake.pdf"])

        self.assertEqual(resultado["tipo_documento"], "pedido")
        self.assertEqual(resultado["status"], "Aprovado")
        self.assertEqual(resultado["colaboradores"], [{"nome": "Milton Jorge Custodio"}])
        self.assertEqual(
            resultado["resumo_financeiro"]["valores_separados"],
            [{
                "nome": "Milton Jorge Custodio",
                "valor_recibo": 485.0,
                "valor_comprovante": 485.0,
                "valor": 485.0,
                "status": "OK",
                "detalhe": "Recibo e comprovante conferidos por colaborador",
            }],
        )
        self.assertTrue(resultado["resumo_financeiro"]["tem_colaboradores"])
        self.assertTrue(resultado["resumo_financeiro"]["tem_recibo_ou_comprovante"])

    def test_analisar_agrupa_colaboradores_por_pagina(self):
        paginas = [
            """
            À
            MSE ENGENHARIA LTDA
            Assunto: Vale Refeição
            Eu, GIULIANO LEO NATALE, declaro para os devidos fins
            que recebi reembolso de refeição no valor de R$ 485,00
            """,
            """
            Banco Itaú - Comprovante de Transferência
            Dados da conta creditada:
            Nome: GIULIANO LEO NATALE
            Valor: R$ 485,00
            """,
            """
            Eu, OSVALDO CESAR VIOTTI, declaro para os devidos fins
            que recebi reembolso de refeição no valor de R$ 485,00
            """,
            """
            Banco Itaú - Comprovante de Transferência
            Dados da conta creditada:
            Nome: OSVALDO CESAR VIOTTI
            Valor: R$ 485,00
            """,
        ]

        with (
            patch("validators.vale_alimentacao.validator._extrair_textos_paginas_pdf", return_value=paginas),
            patch("validators.vale_alimentacao.validator.extrair_texto_pdf_inteligente", return_value=""),
            patch("validators.vale_alimentacao.validator._extrair_texto_fallback_pdf", return_value=""),
            patch("validators.vale_alimentacao.validator.yolo_disponivel", return_value=False),
            patch(
                "validators.vale_alimentacao.validator.detectar_autenticacao_digital",
                return_value={"assinatura_digital": False},
            ),
        ):
            resultado = VAValidator().analisar(["fake.pdf"])

        nomes = [c["nome"] for c in resultado["colaboradores"]]
        self.assertEqual(nomes, ["Giuliano Leo Natale", "Osvaldo Cesar Viotti"])
        self.assertEqual(len(resultado["resumo_financeiro"]["valores_separados"]), 2)
        self.assertEqual(resultado["resumo_financeiro"]["valores_separados"][0]["valor_recibo"], 485.0)
        self.assertEqual(resultado["resumo_financeiro"]["valores_separados"][0]["valor_comprovante"], 485.0)

    def test_bridge_va_ignora_tabela_de_validacoes(self):
        resultado = {
            "status": "Aprovado",
            "mensagem": "ok",
            "colaboradores": [{"nome": "MILTON JORGE CUSTODIO", "valor": 147.0, "evidencia": "linha"}],
            "validacoes": [{"colaborador": "X", "valor": 1, "status": "OK", "detalhe": "teste"}],
        }

        tabela = montar_data_table(resultado, endpoint="va")
        titulos = [item.get("titulo") for item in tabela]
        colaboradores = next(item for item in tabela if item.get("titulo") == "Colaboradores")

        self.assertNotIn("Validacoes", titulos)
        self.assertIn("Colaboradores", titulos)
        self.assertEqual(colaboradores["columns"], ["nome"])
        self.assertEqual(colaboradores["rows"], [{"nome": "MILTON JORGE CUSTODIO"}])


if __name__ == "__main__":
    unittest.main()
