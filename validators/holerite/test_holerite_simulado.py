import unittest
from unittest.mock import patch

from services.holerite_service import extrair_valor_comprovante, limpar_nome, processar_holerite_comprovante
from services.model_rules import extrair_campos_por_modelo, limpar_nome_colaborador
from validators.holerite.engine_parser import (
    extrair_comprovante_do_bloco,
    extrair_holerite_do_bloco,
    extrair_nome_colaborador_holerite,
    extrair_nome_comprovante_robusto,
    _candidato_parece_nome,
)
from validators.holerite.parser_comprovante import extrair_pagamentos
from validators.holerite.parser_holerite import extrair_funcionarios
from validators.holerite.validador import validar_holerite_e_pagamento

HOLERITE_TEXTO = """
FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
22.958.374/0001-57
Codigo Nome do Funcionario CBO
101 OSVALDO CESAR VIOTTI 2143
ENGENHEIRO MECANICO
Folha Mensal Abril de 2026
Valor Liquido 2.358,91
ASSINATURA OU VISTO
07/05/2026

FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
22.958.374/0001-57
Codigo Nome do Funcionario CBO
102 IGOR AUGUSTO QUINTILIANO SILVA 2144
ANALISTA
Folha Mensal Abril de 2026
Valor Liquido 3.309,61
ASSINATURA E DATA: 08/05/2026

FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
22.958.374/0001-57
Codigo Nome do Funcionario CBO
103 GIULIANO LEO NATALE 2145
AUXILIAR
Folha Mensal Abril de 2026
Valor Liquido 2.358,91
RUBRICA
09/05/2026
"""

COMPROVANTE_TEXTO = """
Banco Itau - Comprovante de Transferencia
Dados da conta creditada:
Nome: OSVALDO CESAR VIOTTI
Valor: R$ 2.358,91
Transferencia efetuada em 07/05/2026 as 04:42:42

Banco Itau - Comprovante de Transferencia
Dados da conta creditada:
Nome: IGOR AUGUSTO QUINTILIANO SIL
Valor: R$ 3.309,61
Transferencia efetuada em 07/05/2026 as 04:45:12

Banco Itau - Comprovante de Transferencia
Dados da conta creditada:
Nome: GIULIANO LEO NATALE
Valor: R$ 2.358,91
Transferencia efetuada em 07/05/2026 as 04:48:22
"""


class TestHoleriteComprovanteSimulado(unittest.TestCase):
    def test_valor_liquido_e_pagamento_apos_rotulo(self):
        holerite = """
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        Valor Liquido R$ 1.417,10
        BASES SATORIO BASE SAL CONTR INSS BASE CALC FGTS FGTS DO MES 147,00
        """
        comprovante = """
        Banco Itau - Comprovante de Transferencia
        Nome: MILTON JORGE CUSTODIO
        Valor: R$ 1.417,10
        Transferencia efetuada em 07/05/2026 as 04:42:42
        """
        h = extrair_holerite_do_bloco(holerite, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        c = extrair_comprovante_do_bloco(comprovante, nome_arquivo="MILTON JORGE CUSTODIO - COMPROVANTE.pdf")
        self.assertEqual(h["valor_liquido"], 1417.10)
        self.assertEqual(c["valor_pago"], 1417.10)

    def test_nao_usar_total_de_vencimentos_como_valor_liquido(self):
        holerite = """
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        Total de Vencimentos R$ 9.999,99
        Valor Liquido
        R$ 1.417,10
        """
        h = extrair_holerite_do_bloco(holerite, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertEqual(h["valor_liquido"], 1417.10)

    def test_extrair_liquido_a_receber_no_modelo_02(self):
        holerite = """
        RECIBO DE PAGAMENTO DE SALARIO
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        Total de Vencimentos R$ 9.999,99
        Liquido a Receber
        R$ 1.314,61
        Assinatura e Data: 07/05/2026
        """
        h = extrair_holerite_do_bloco(holerite, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertEqual(h["valor_liquido"], 1314.61)
        self.assertEqual(h["valor_liquido_extraido"], 1314.61)
        self.assertTrue(h["assinatura"])
        self.assertEqual(h["data_assinatura"], "07/05/2026")

    def test_nao_usar_total_vencimentos_quando_existe_liquido_a_receber(self):
        holerite = """
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        Total de Vencimentos R$ 9.999,99
        Liquido a Receber
        R$ 1.314,61
        """
        h = extrair_holerite_do_bloco(holerite, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertEqual(h["valor_liquido"], 1314.61)

    def test_assinatura_inferior_com_data(self):
        holerite = """
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        Valor Liquido R$ 1.417,10
        ASSINATURA OU VISTO
        07/05/2026
        """
        h = extrair_holerite_do_bloco(holerite, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertTrue(h["assinatura"])
        self.assertEqual(h["data_assinatura"], "07/05/2026")

    def test_assinatura_lateral_com_data(self):
        holerite = """
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        Valor Liquido R$ 1.417,10
        ASSINATURA E DATA: 08/05/2026
        """
        h = extrair_holerite_do_bloco(holerite, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertTrue(h["assinatura"])
        self.assertEqual(h["data_assinatura"], "08/05/2026")

    def test_extracao_dois_blocos_mesma_pagina(self):
        texto = """
        RECIBO DE PAGAMENTO DE SALARIO
        NOME DO FUNCIONARIO
        JOSE DA SILVA
        Liquido a Receber
        R$ 1.000,00
        Assinatura
        01/06/2026

        ADIANTAMENTO
        NOME DO FUNCIONARIO
        JOSE DA SILVA
        Liquido a Receber
        R$ 300,00
        Assinatura ou Visto
        15/06/2026
        """
        regs = extrair_funcionarios(texto)
        self.assertEqual(len(regs), 2)
        self.assertEqual([round(r["valor_liquido"], 2) for r in regs], [1000.00, 300.00])

    def test_extracao_nome_holerite_apenas_colaborador(self):
        texto = """
        EMPRESA TESTE LTDA
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        BASES SATORIO BASE SAL CONTR INSS BASE CALC FGTS FGTS DO MES
        ASSINATURA
        """
        nome = extrair_nome_colaborador_holerite(texto, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertEqual(nome, "MILTON JORGE CUSTODIO")

        texto_sem_label = """
        EMPRESA TESTE LTDA
        BASES SATORIO BASE SAL CONTR INSS BASE CALC FGTS FGTS DO MES
        ASSINATURA
        """
        nome_sem_label = extrair_nome_colaborador_holerite(texto_sem_label, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertEqual(nome_sem_label, "MILTON JORGE CUSTODIO")

    def test_extracao_holerite(self):
        regs = extrair_funcionarios(HOLERITE_TEXTO)
        self.assertEqual(len(regs), 3)

    def test_extracao_comprovante(self):
        regs = extrair_pagamentos(COMPROVANTE_TEXTO)
        self.assertEqual(len(regs), 3)
        self.assertTrue(all(r["banco"] == "Itau" for r in regs))

    def test_extracao_comprovante_dados_da_conta_creditada(self):
        comprovante = """
        Banco Itau - Comprovante de Transferencia
        Dados da conta debitada:
        Nome da empresa: FNEC - CONSULTORIA E SERVICOS
        Agencia: 0026
        Conta corrente: 61333 - 1
        DADOS DA CONTA CREDITADA:
        NOME: MILTON JORGE CUSTODIO
        VALOR: R$ 1.417,10
        TRANSFERENCIA EFETUADA EM 07/05/2026 AS 04:42:42
        """
        dados = extrair_comprovante_do_bloco(comprovante, nome_arquivo="MILTON JORGE CUSTODIO - COMPROVANTE.pdf")
        self.assertEqual(dados["nome"], "MILTON JORGE CUSTODIO")
        self.assertEqual(dados["valor_pago"], 1417.10)
        self.assertNotEqual(dados["nome"], "FNEC CONSULTORIA SERVICOS")

    def test_extracao_holerite_nome_na_linha_seguinte_e_valor_liquido(self):
        holerite = """
        FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
        22.958.374/0001-57
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        ANALISTA
        Valor Liquido 422,30
        ASSINATURA OU VISTO
        07/05/2026
        """
        dados = extrair_holerite_do_bloco(holerite, nome_arquivo="arquivo.pdf")
        self.assertEqual(dados["nome"], "MILTON JORGE CUSTODIO")
        self.assertEqual(dados["valor_liquido"], 422.30)
        self.assertEqual(dados["metodo_nome"], "nome_linha_seguinte")
        self.assertEqual(dados["metodo_valor_liquido"], "valor_rotulo")
        self.assertIsNotNone(dados["evidencia_nome"])
        self.assertIsNotNone(dados["evidencia_valor_liquido"])

    def test_extracao_holerite_nome_mesma_linha_e_zero_expresso(self):
        holerite = """
        RECIBO DE PAGAMENTO DE SALARIO
        NOME DO FUNCIONARIO: MILTON JORGE CUSTODIO
        CARGO: AUXILIAR
        Liquido a Receber
        R$ 0,00
        ASSINATURA E DATA: 08/05/2026
        """
        dados = extrair_holerite_do_bloco(holerite, nome_arquivo="documento.pdf")
        self.assertEqual(dados["nome"], "MILTON JORGE CUSTODIO")
        self.assertEqual(dados["valor_liquido"], 0.0)
        self.assertEqual(dados["metodo_nome"], "nome_rotulo")
        self.assertIsNotNone(dados["evidencia_valor_liquido"])

    def test_extracao_holerite_codigo_nome_cargo(self):
        holerite = """
        EMPRESA TESTE LTDA
        111  MILTON JORGE CUSTODIO  2143
        ANALISTA DE SISTEMAS
        Valor Liquido R$ 1.250,00
        RUBRICA
        09/05/2026
        """
        dados = extrair_holerite_do_bloco(holerite, nome_arquivo="documento.pdf")
        self.assertEqual(dados["nome"], "MILTON JORGE CUSTODIO")
        self.assertNotEqual(dados["nome"], "EMPRESA TESTE LTDA")
        self.assertEqual(dados["valor_liquido"], 1250.00)
        self.assertEqual(dados["metodo_nome"], "nome_codigo")

    def test_extracao_holerite_total_vencimentos_descontos_fallback(self):
        holerite = """
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        TOTAL DOS VENCIMENTOS R$ 1.500,00
        TOTAL DOS DESCONTOS R$ 200,00
        ASSINATURA OU VISTO
        10/05/2026
        """
        dados = extrair_holerite_do_bloco(holerite, nome_arquivo="MILTON JORGE CUSTODIO.pdf")
        self.assertEqual(dados["valor_liquido"], 1300.00)
        self.assertEqual(dados["metodo_valor_liquido"], "total_calculado")
        self.assertIsNotNone(dados["evidencia_valor_liquido"])

    def test_validacao_completa(self):
        out = validar_holerite_e_pagamento(HOLERITE_TEXTO, [COMPROVANTE_TEXTO])
        self.assertEqual(out["debug"]["total_holerites_detectados"], 3)
        self.assertEqual(out["debug"]["total_comprovantes_detectados"], 3)
        self.assertEqual(out["resumo"]["total_holerite"], "R$ 8.027,43")
        self.assertEqual(out["resumo"]["total_pago"], "R$ 8.027,43")
        self.assertEqual(out["resumo"]["diferenca"], "R$ 0,00")
        self.assertTrue(all(c["valor_status"] == "Confere" for c in out["colaboradores"]))
        self.assertTrue(all(c["status"] in {"Aprovado", "Parcial"} for c in out["colaboradores"]))

    def test_validacao_modelo_02_com_comprovante(self):
        holerite = """
        RECIBO DE PAGAMENTO DE SALARIO
        NOME DO FUNCIONARIO
        MILTON JORGE CUSTODIO
        Total de Vencimentos R$ 9.999,99
        Liquido a Receber
        R$ 1.314,61
        ASSINATURA OU VISTO
        07/05/2026
        """
        comprovante = """
        Banco Itau - Comprovante de Transferencia
        Nome: MILTON JORGE CUSTODIO
        Valor: R$ 1.314,61
        Transferencia efetuada em 07/05/2026 as 04:42:42
        """
        out = validar_holerite_e_pagamento(holerite, [comprovante])
        self.assertEqual(out["colaboradores"][0]["valor_liquido"], "R$ 1.314,61")
        self.assertEqual(out["colaboradores"][0]["valor_pago"], "R$ 1.314,61")
        self.assertEqual(out["colaboradores"][0]["valor_status"], "Confere")
        self.assertTrue(out["colaboradores"][0]["assinatura_presente"])

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.91))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    def test_processar_holerite_prioriza_ocr_sobre_nome_do_arquivo(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerite_path = "arquivo_com_nome_errado.pdf"
        comprovante_path = "comprovante_ok.pdf"

        mock_extrair_documento_inteligente.return_value = {
            "texto": """
            NOME DO FUNCIONARIO
            MILTON JORGE CUSTODIO
            Valor Liquido R$ 1.417,10
            ASSINATURA OU VISTO
            07/05/2026
            """,
            "qualidade": 0.94,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_texto_comprovante.return_value = """
        Banco Itau - Comprovante de Transferencia
        Nome: MILTON JORGE CUSTODIO
        Valor: R$ 1.417,10
        Transferencia efetuada em 07/05/2026 as 04:42:42
        """

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "05/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertEqual(out["nome_holerite"], "MILTON JORGE CUSTODIO")
        self.assertEqual(out["colaboradores"][0]["nome_holerite"], "MILTON JORGE CUSTODIO")
        self.assertEqual(out["colaboradores"][0]["metodo_nome"], "nome_linha_seguinte")
        self.assertIsNotNone(out["evidencia_nome"])

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.92))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    def test_processar_comprovante_unico_com_multiplos_pagamentos_soma_valores(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerites = {
            "h1.pdf": """
            RECIBO DE PAGAMENTO DE SALARIO
            NOME DO FUNCIONARIO
            GIULIANO LEO NATALE
            Valor Liquido R$ 2.645,87
            ASSINATURA OU VISTO
            05/06/2026
            """,
            "h2.pdf": """
            RECIBO DE PAGAMENTO DE SALARIO
            NOME DO FUNCIONARIO
            IGOR AUGUSTO QUINTILIANO SILVA
            Valor Liquido R$ 2.813,26
            ASSINATURA OU VISTO
            05/06/2026
            """,
        }

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: {
            "texto": holerites[path],
            "qualidade": 0.94,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_texto_comprovante.return_value = """
        Banco Itau - Comprovante de Transferencia
        Dados da conta creditada:
        Nome: GIULIANO LEO NATALE
        Valor: R$ 2.645,87
        Transferencia efetuada em 05/06/2026 as 04:34:13

        Banco Itau - Comprovante de Transferencia
        Dados da conta creditada:
        Nome: IGOR AUGUSTO QUINTILIANO SILVA
        Valor: R$ 2.813,26
        Transferencia efetuada em 05/06/2026 as 04:53:52
        """

        out = processar_holerite_comprovante(["h1.pdf", "h2.pdf"], ["comprovante_unico.pdf"], "06/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertEqual(round(out["valor_comprovante"], 2), 5459.13)
        self.assertEqual(len(out["colaboradores"]), 2)
        self.assertTrue(all(c["valor_ok"] for c in out["colaboradores"]))

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.99))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    def test_processar_varios_holerites_e_comprovantes(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerites = {
            "h1.pdf": """
            RECIBO DE PAGAMENTO DE SALARIO
            NOME DO FUNCIONARIO
            JOSE DA SILVA
            Total de Vencimentos R$ 9.999,99
            Liquido a Receber
            R$ 1.000,00
            ASSINATURA OU VISTO
            01/06/2026
            """,
            "h2.pdf": """
            RECIBO DE PAGAMENTO DE SALARIO
            NOME DO FUNCIONARIO
            MARIA SOUZA
            Total de Vencimentos R$ 8.888,88
            Valor Liquido
            R$ 300,00
            ASSINATURA E DATA: 02/06/2026
            """,
        }
        comprovantes = {
            "c1.pdf": """
            Banco Itau - Comprovante de Transferencia
            Nome: JOSE DA SILVA
            Valor: R$ 1.000,00
            Transferencia efetuada em 01/06/2026 as 08:00:00
            """,
            "c2.pdf": """
            Banco Itau - Comprovante de Transferencia
            Nome: MARIA SOUZA
            Valor: R$ 300,00
            Transferencia efetuada em 02/06/2026 as 09:30:00
            """,
        }

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: (
            {
                "texto": holerites[path],
                "qualidade": 0.93,
                "metodo": "tesseract",
                "precisa_ia": False,
                "motivo_ia": "ocr_local_suficiente",
            }
            if path in holerites
            else {
                "texto": "",
                "qualidade": 0.0,
                "metodo": "falha",
                "precisa_ia": False,
                "motivo_ia": "sem_texto",
            }
        )
        mock_extrair_texto_comprovante.side_effect = lambda path: comprovantes[path]

        out = processar_holerite_comprovante(["h1.pdf", "h2.pdf"], ["c1.pdf", "c2.pdf"], "06/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertEqual(out["mensagem"], "2 colaborador(es) processado(s)")
        self.assertEqual(out["valor_holerite"], 1300.00)
        self.assertEqual(out["valor_comprovante"], 1300.00)
        self.assertEqual(len(out["colaboradores"]), 2)
        self.assertTrue(all(c["valor_ok"] for c in out["colaboradores"]))
        self.assertCountEqual(
            [c["nome_holerite"] for c in out["colaboradores"]],
            ["JOSE DA SILVA", "MARIA SOUZA"],
        )
        self.assertCountEqual(
            [round(c["valor_liquido"], 2) for c in out["colaboradores"]],
            [1000.00, 300.00],
        )

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.40))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    @patch("services.holerite_service.extrair_holerite_openai_pdf")
    def test_processar_holerite_usa_openai_quando_ocr_incompleto(
        self,
        mock_extrair_holerite_openai_pdf,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerite_path = "holerite_incompleto.pdf"
        comprovante_path = "comprovante_ok.pdf"

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: {
            "texto": """
            NOME DO FUNCIONARIO
            MILTON JORGE CUSTODIO
            Valor Liquido R$ 1.417,10
            """,
            "qualidade": 0.42,
            "metodo": "tesseract",
            "precisa_ia": True,
            "motivo_ia": "qualidade_ocr_baixa",
        } if path == holerite_path else {
            "texto": "",
            "qualidade": 0.0,
            "metodo": "falha",
            "precisa_ia": True,
            "motivo_ia": "arquivo_inexistente",
        }

        mock_extrair_holerite_openai_pdf.return_value = {
            "colaboradores": [
                {
                    "nome": "MILTON JORGE CUSTODIO",
                    "valor_liquido": 1417.10,
                    "competencia": "01/2026",
                    "assinatura": True,
                    "tipo_assinatura": "rubrica",
                    "data_assinatura": "07/05/2026",
                    "confianca": 0.93,
                    "observacoes": ["extraido via openai"],
                }
            ],
            "motivo": "ok",
        }

        mock_extrair_texto_comprovante.side_effect = lambda path: """
        Banco Itau - Comprovante de Transferencia
        Nome: MILTON JORGE CUSTODIO
        Valor: R$ 1.417,10
        Transferencia efetuada em 07/05/2026 as 04:42:42
        """

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "01/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertTrue(out["ia_fallback"])
        self.assertEqual(out["colaboradores"][0]["nome_holerite"], "MILTON JORGE CUSTODIO")
        self.assertEqual(round(out["colaboradores"][0]["valor_holerite"], 2), 1417.10)
        self.assertTrue(out["colaboradores"][0]["assinatura_presente"])
        self.assertEqual(out["colaboradores"][0]["datado"], "Sim")

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.92))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    def test_processar_holerite_match_com_nome_truncado_no_comprovante(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerite_path = "holerite_ok.pdf"
        comprovante_path = "comprovante_truncado.pdf"

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: {
            "texto": """
            RECIBO DE PAGAMENTO DE SALARIO
            NOME DO FUNCIONARIO
            MILTON JORGE CUSTODIO
            Valor Liquido R$ 1.417,10
            ASSINATURA OU VISTO
            07/05/2026
            """,
            "qualidade": 0.94,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_texto_comprovante.side_effect = lambda path: """
        Banco Itau - Comprovante de Transferencia
        Nome: MILTON JORGE CUSTOD
        Valor: R$ 1.417,10
        Transferencia efetuada em 07/05/2026 as 04:42:42
        """

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "05/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertTrue(out["colaboradores"][0]["nome_ok"])
        self.assertTrue(out["colaboradores"][0]["valor_ok"])
        self.assertEqual(out["colaboradores"][0]["nome_comprovante"], "MILTON JORGE CUSTODIO")

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.93))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=993.91)
    def test_processar_holerite_usa_valor_arquivo_quando_ocr_texto_falha(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerite_path = "holerite_vinicius.pdf"
        comprovante_path = "comprovante_vinicius.pdf"

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: {
            "texto": """
            RECIBO DE PAGAMENTO DE SALARIO
            NOME DO FUNCIONARIO
            VINICIUS VICENTE FIRMINO BUZZO
            Valor Liquido R$ 993,91
            ASSINATURA OU VISTO
            05/02/2026
            """,
            "qualidade": 0.92,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_texto_comprovante.return_value = """
        Comprovante de transferência
        Dados de quem está pagando:
        Dados de quem está recebendo:
        Nome: VINICIUS VICENTE FIRMINO BUZZO
        Dados da transação:
        Valor: RESTO aee]
        Data da transferência: 05/02/2026
        """

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "02/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertEqual(round(out["valor_comprovante"], 2), 993.91)
        self.assertEqual(round(out["colaboradores"][0]["valor_comprovante"], 2), 993.91)
        self.assertTrue(out["colaboradores"][0]["valor_ok"])

    def test_model_rules_holerite_02_prioriza_nome_do_funcionario(self):
        texto = """
        FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
        22.958.374/0001-57
        RECIBO DE PAGAMENTO DE SALARIO
        CODIGO NOME DO FUNCIONARIO CBO
        101 MILTON JORGE CUSTODIO 2143
        VALOR LIQUIDO
        R$ 1.417,10
        REFERENTE AO MES / ANO
        01/2026
        ASSINATURA DO FUNCIONARIO
        """
        resultado = extrair_campos_por_modelo(texto, "holerite")
        self.assertEqual(resultado["modelo_id"], "holerite_generico_salario")
        self.assertEqual(resultado["campos"].get("nome_colaborador"), "MILTON JORGE CUSTODIO")
        self.assertEqual(round(float(resultado["campos"].get("valor_liquido", 0.0)), 2), 1417.10)
        self.assertEqual(resultado["campos"].get("competencia"), "01/2026")
        self.assertTrue(resultado["confianca"] >= 0.35)

    def test_model_rules_comprovante_prioriza_valor_mais_proximo_do_label(self):
        texto = """
        COMPROVANTE DE TRANSFERENCIA
        DADOS DA TRANSACAO
        DADOS DE QUEM ESTA RECEBENDO
        FAVORECIDO: JOSE DA SILVA
        VALOR
        R$ 1.417,10
        DATA DA TRANSFERENCIA
        07/05/2026
        AUTENTICACAO NO COMPROVANTE
        """
        resultado = extrair_campos_por_modelo(texto, "comprovante")
        self.assertEqual(resultado["modelo_id"], "comprovante_transferencia_generico")
        self.assertEqual(round(float(resultado["campos"].get("valor_comprovante", 0.0)), 2), 1417.10)
        self.assertEqual(resultado["campos"].get("nome_colaborador"), "JOSE DA SILVA")

    def test_limpeza_de_nome_remove_prefixo_rua_e_descarta_ruido_de_folha(self):
        self.assertEqual(limpar_nome("RUA JOAO PACULDINO"), "JOAO PACULDINO")
        self.assertEqual(limpar_nome_colaborador("RUA JOAO PACULDINO"), "JOAO PACULDINO")
        self.assertEqual(limpar_nome("SALDO SAL CONTRI CAL DO MES FAIXA"), None)
        self.assertEqual(limpar_nome_colaborador("SALDO SAL CONTRI CAL DO MES FAIXA"), "")
        self.assertFalse(_candidato_parece_nome("TER IMPORTANCIA DISCRIMINADA NESTE"))

    def test_valor_comprovante_usa_ancoras_genericas(self):
        texto = """
        COMPROVANTE DE TRANSFERENCIA
        DADOS DA TRANSACAO
        FAVORECIDO: JOAO PACULDINO
        VALOR
        R$ 1.580,17
        DATA DA TRANSFERENCIA
        05/05/2026
        AUTENTICACAO NO COMPROVANTE
        """
        self.assertEqual(round(extrair_valor_comprovante(texto), 2), 1580.17)

    def test_comprovante_prioriza_recebedor_em_vez_do_pagador(self):
        texto = """
        Comprovante de Transferencia
        dados do pagador
        nome do pagador: SOLLO PRODUCOES E EVENTOS LTDA
        dados do recebedor
        nome do recebedor: LUIZ GUILHERME ALMEIDA TRINDADE
        dados da transacao
        valor: R$ 1.645,97
        data da transferencia: 05/06/2026
        """
        nome, debug = extrair_nome_comprovante_robusto(texto)
        self.assertEqual(nome, "LUIZ GUILHERME ALMEIDA TRINDADE")
        self.assertIn("nome_recebedor", debug)
        resultado = extrair_comprovante_do_bloco(texto, nome_arquivo="")
        self.assertEqual(resultado.get("nome"), "LUIZ GUILHERME ALMEIDA TRINDADE")
        self.assertEqual(round(float(resultado.get("valor_pago", 0.0)), 2), 1645.97)

    def test_extracao_holerite_ignora_ruido_de_evento_e_cargo(self):
        texto_montador = """
        00749 SOLLO PRODUCOES E EVENTOS LTDA 21183848000173 Demonstrativo de Pagamento de Salario
        RUA JOAO PACULDINO, 168
        01/05/2026 a 31/05/2026 NOVO NORDISK PRODUCAO FARMACEUT 16.921.603/0001-66
        001013 LUIZ GUILHERME ALMEIDA TRINDADE Montador
        Salario Base 031,00
        DECLARO TER RECEBIDO A IMPORTANCIA LIQUIDA DISCRIMINADA NESTE RECIBO
        ASSINATURA DO FUNCIONARIO
        """
        resultado_montador = extrair_holerite_do_bloco(texto_montador, nome_arquivo="")
        self.assertEqual(resultado_montador.get("nome"), "LUIZ GUILHERME ALMEIDA TRINDADE")

        texto_evento = """
        10749 SOLLO PRODUCOES E EVENTOS LTDA 21183848000173 Demonstrativo de Pagamento de Salario
        RUA JOAO PACULDINO. 168
        01/05/2026 a 31/05/2026 NOVO NORDISK PRODUCAO FARMACEUT 16.921.603/0001-66
        001 [Salario Base 031,00 1.621,00
        039 [Cesta Basica 340.00
        101 Ajuda de Custo 239.00
        903 [INSS Folha 121.57
        DECLARO TER RECEBIDO A IMPORTANCIA LIQUIDA DISCRIMINADA NESTE RECIBO
        ASSINATURA DO FUNCIONARIO
        """
        resultado_evento = extrair_holerite_do_bloco(texto_evento, nome_arquivo="")
        self.assertIsNone(resultado_evento.get("nome"))

    @patch("services.holerite_service.extrair_campos_por_modelo")
    @patch(
        "services.holerite_service.analisar_assinatura_data",
        return_value={
            "assinatura_ok": True,
            "assinatura_detalhe": "Rubrica/assinatura identificada",
            "data_manuscrita_ok": True,
            "data_detalhe": "Data identificada: 07/05/2026",
            "data_identificada": "07/05/2026",
            "modelo_assinatura": "inferior",
            "rotulo_assinatura": "ASSINATURA OU VISTO",
        },
    )
    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.93))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    def test_processar_holerite_expoe_modelo_regras_sem_quebrar_retorno(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
        _mock_analisar_assinatura_data,
        mock_extrair_campos_por_modelo,
    ):
        holerite_path = "holerite_modelo_regras.pdf"
        comprovante_path = "comprovante_modelo_regras.pdf"

        def _ocr_side_effect(path, tipo_documento=None, usar_ocr=True):
            if path == holerite_path:
                return {
                    "texto": """
                    FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
                    22.958.374/0001-57
                    RECIBO DE PAGAMENTO DE SALARIO
                    CODIGO NOME DO FUNCIONARIO CBO
                    101 MILTON JORGE CUSTODIO 2143
                    VALOR LIQUIDO
                    R$ 1.417,10
                    REFERENTE AO MES / ANO
                    01/2026
                    ASSINATURA DO FUNCIONARIO
                    07/05/2026
                    """,
                    "qualidade": 0.96,
                    "metodo": "tesseract",
                    "precisa_ia": False,
                    "motivo_ia": "ocr_local_suficiente",
                }
            return {
                "texto": "",
                "qualidade": 0.0,
                "metodo": "falha",
                "precisa_ia": False,
                "motivo_ia": "sem_texto",
            }

        mock_extrair_documento_inteligente.side_effect = _ocr_side_effect
        mock_extrair_texto_comprovante.return_value = """
        Banco Itau - Comprovante de Transferencia
        Nome: MILTON JORGE CUSTODIO
        Valor: R$ 1.417,10
        Transferencia efetuada em 07/05/2026 as 04:42:42
        """
        mock_extrair_campos_por_modelo.return_value = {
            "modelo_id": "holerite_generico_salario",
            "confianca": 0.84,
            "campos": {
                "nome_colaborador": "MILTON JORGE CUSTODIO",
                "valor_liquido": 1417.10,
                "competencia": "01/2026",
                "assinatura_regiao": "bloco_superior_assinatura",
            },
            "evidencias": [
                {"campo": "nome_colaborador", "regiao": "bloco_superior"},
                {"campo": "valor_liquido", "regiao": "bloco_superior_rodape"},
                {"campo": "competencia", "regiao": "bloco_superior"},
            ],
        }

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "01/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertEqual(out["modelo_regras"], "holerite_generico_salario")
        self.assertGreaterEqual(out["confianca_modelo_regras"], 0.84)
        self.assertEqual(out["campos_modelo_regras"].get("nome_colaborador"), "MILTON JORGE CUSTODIO")
        self.assertEqual(out["colaboradores"][0]["modelo_id"], "holerite_generico_salario")
        self.assertEqual(out["colaboradores"][0]["origem_extracao"], "modelo_regras")
        self.assertEqual(out["colaboradores"][0]["nome_holerite"], "MILTON JORGE CUSTODIO")

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.93))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_dados_comprovante_do_bloco")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=993.91)
    def test_processar_holerite_prefere_valor_arquivo_quando_bloco_erra_valor(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_documento_inteligente,
        mock_extrair_dados_comprovante_do_bloco,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerite_path = "holerite_vinicius.pdf"
        comprovante_path = "comprovante_vinicius.pdf"

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: {
            "texto": """
            RECIBO DE PAGAMENTO DE SALARIO
            NOME DO FUNCIONARIO
            VINICIUS VICENTE FIRMINO BUZZO
            Valor Liquido R$ 993,91
            ASSINATURA OU VISTO
            05/02/2026
            """,
            "qualidade": 0.92,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_texto_comprovante.return_value = """
        Comprovante de transferÃªncia
        Dados de quem estÃ¡ pagando:
        Dados de quem estÃ¡ recebendo:
        Nome: VINICIUS VICENTE FIRMINO BUZZO
        Dados da transaÃ§Ã£o:
        Valor: RESTO aee]
        Data da transferÃªncia: 05/02/2026
        """
        mock_extrair_dados_comprovante_do_bloco.return_value = {
            "nome": "VINICIUS VICENTE FIRMINO BUZZO",
            "valor_pago": 147.00,
            "data_pagamento": "05/02/2026",
            "banco": "Itau",
            "empresa_pagadora": None,
            "fonte": "comprovante",
            "confianca": 0.72,
            "debug": {"padroes": ["valor_linha"]},
        }

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "02/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertEqual(round(out["valor_comprovante"], 2), 993.91)
        self.assertEqual(round(out["colaboradores"][0]["valor_comprovante"], 2), 993.91)
        self.assertTrue(out["colaboradores"][0]["valor_ok"])

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.93))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_comprovante_openai_pdf")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    def test_processar_holerite_usa_openai_no_comprovante_quando_ocr_e_ruim(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_comprovante_openai_pdf,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerite_path = "holerite_vinicius.pdf"
        comprovante_path = "comprovante_vinicius.pdf"

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: (
            {
                "texto": """
                RECIBO DE PAGAMENTO DE SALARIO
                NOME DO FUNCIONARIO
                VINICIUS VICENTE FIRMINO BUZZO
                Valor Liquido R$ 993,91
                ASSINATURA OU VISTO
                05/02/2026
                """,
                "qualidade": 0.92,
                "metodo": "tesseract",
                "precisa_ia": False,
                "motivo_ia": "ocr_local_suficiente",
            }
            if path == holerite_path
            else {
                "texto": """
                Comprovante de transferência
                Dados de quem está pagando:
                Dados de quem está recebendo:
                Nome: VINICIUS VICENTE FIRMINO BUZZO
                Dados da transação:
                Valor: R$ 147,00
                Data da transferência: 05/02/2026
                """,
                "qualidade": 0.31,
                "metodo": "tesseract",
                "precisa_ia": True,
                "motivo_ia": "qualidade_ocr_baixa",
            }
        )
        mock_extrair_texto_comprovante.return_value = """
        Comprovante de transferência
        Dados de quem está pagando:
        Dados de quem está recebendo:
        Nome: VINICIUS VICENTE FIRMINO BUZZO
        Dados da transação:
        Valor: R$ 147,00
        Data da transferência: 05/02/2026
        """
        mock_extrair_comprovante_openai_pdf.return_value = {
            "pagamentos": [
                {
                    "nome": "VINICIUS VICENTE FIRMINO BUZZO",
                    "valor_pago": 993.91,
                    "data_pagamento": "05/02/2026",
                    "banco": "Itau",
                    "empresa_pagadora": "KIPLACA",
                    "confianca": 0.96,
                    "observacoes": ["extraido via openai"],
                }
            ],
            "motivo": "ok",
        }

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "02/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertTrue(out["ia_fallback"])
        self.assertEqual(round(out["valor_comprovante"], 2), 993.91)
        self.assertEqual(round(out["colaboradores"][0]["valor_comprovante"], 2), 993.91)
        self.assertTrue(out["colaboradores"][0]["valor_ok"])
        self.assertEqual(out["colaboradores"][0]["nome_comprovante"], "VINICIUS VICENTE FIRMINO BUZZO")

    @patch("services.holerite_service.yolo_disponivel", return_value=False)
    @patch("services.holerite_service.detectar_rubricas_por_colaborador", return_value={})
    @patch("services.holerite_service.detectar_autenticacao_digital", return_value={"assinatura_digital": False})
    @patch("services.holerite_service.aprender_documento", return_value=({"modelo": "layout_teste"}, False))
    @patch("services.holerite_service.encontrar_layout", return_value=({"modelo": "layout_teste"}, 0.93))
    @patch("services.holerite_service.extrair_texto_comprovante")
    @patch("services.holerite_service.extrair_documento_inteligente")
    @patch("services.holerite_service.extrair_comprovante_openai_pdf")
    @patch("services.holerite_service.extrair_valor_comprovante_arquivo", return_value=0.0)
    def test_processar_holerite_usa_openai_no_comprovante_quando_ocr_e_so_razoavel(
        self,
        _mock_valor_comprovante_arquivo,
        mock_extrair_comprovante_openai_pdf,
        mock_extrair_documento_inteligente,
        mock_extrair_texto_comprovante,
        _mock_encontrar_layout,
        _mock_aprender_documento,
        _mock_detectar_autenticacao_digital,
        _mock_detectar_rubricas,
        _mock_yolo_disponivel,
    ):
        holerite_path = "holerite_vinicius.pdf"
        comprovante_path = "comprovante_vinicius_razoavel.pdf"

        mock_extrair_documento_inteligente.side_effect = lambda path, tipo_documento=None, usar_ocr=True: (
            {
                "texto": """
                RECIBO DE PAGAMENTO DE SALARIO
                NOME DO FUNCIONARIO
                VINICIUS VICENTE FIRMINO BUZZO
                Valor Liquido R$ 993,91
                ASSINATURA OU VISTO
                05/02/2026
                """,
                "qualidade": 0.92,
                "metodo": "tesseract",
                "precisa_ia": False,
                "motivo_ia": "ocr_local_suficiente",
            }
            if path == holerite_path
            else {
                "texto": """
                Comprovante de transferÃªncia
                Dados de quem estÃ¡ pagando:
                Dados de quem estÃ¡ recebendo:
                Nome: VINICIUS VICENTE FIRMINO BUZZO
                Dados da transaÃ§Ã£o:
                Valor: R$ 147,00
                Data da transferÃªncia: 05/02/2026
                """,
                "qualidade": 0.77,
                "metodo": "tesseract",
                "precisa_ia": False,
                "motivo_ia": "ocr_local_suficiente",
            }
        )
        mock_extrair_texto_comprovante.return_value = """
        Comprovante de transferÃªncia
        Dados de quem estÃ¡ pagando:
        Dados de quem estÃ¡ recebendo:
        Nome: VINICIUS VICENTE FIRMINO BUZZO
        Dados da transaÃ§Ã£o:
        Valor: R$ 147,00
        Data da transferÃªncia: 05/02/2026
        """
        mock_extrair_comprovante_openai_pdf.return_value = {
            "pagamentos": [
                {
                    "nome": "VINICIUS VICENTE FIRMINO BUZZO",
                    "valor_pago": 993.91,
                    "data_pagamento": "05/02/2026",
                    "banco": "Itau",
                    "empresa_pagadora": "KIPLACA",
                    "confianca": 0.96,
                }
            ],
            "motivo": "ok",
        }

        out = processar_holerite_comprovante([holerite_path], [comprovante_path], "02/2026")

        self.assertEqual(out["status"], "Aprovado")
        self.assertTrue(out["ia_fallback"])
        self.assertEqual(round(out["valor_comprovante"], 2), 993.91)
        self.assertEqual(round(out["colaboradores"][0]["valor_comprovante"], 2), 993.91)
        self.assertEqual(out["colaboradores"][0]["nome_comprovante"], "VINICIUS VICENTE FIRMINO BUZZO")


if __name__ == "__main__":
    unittest.main()
