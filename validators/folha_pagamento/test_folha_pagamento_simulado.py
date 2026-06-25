import unittest
from unittest.mock import patch

from services.folha_service import processar_folha_pagamento
from validators.folha_pagamento.regras import (
    extrair_colaboradores,
    extrair_competencia_folha,
    extrair_empresa,
)
from validators.folha_pagamento.parser_relacao_calculo import (
    eh_layout_relacao_calculo,
    extrair_dados_relacao_calculo,
)
from validators.folha_pagamento.parser_extrato_mensal import (
    eh_layout_extrato_mensal,
    extrair_dados_extrato_mensal,
)
from validators.folha_pagamento.parser_scivisual import (
    eh_layout_scivisual,
    extrair_dados_scivisual,
)
from validators.folha_pagamento.parser_espelho_resumo_folha import (
    eh_layout_espelho_resumo_folha,
    extrair_dados_espelho_resumo_folha,
)
from validators.folha_pagamento.parser_folha_cabecalho_nome import (
    eh_layout_folha_cabecalho_nome,
    extrair_dados_folha_cabecalho_nome,
)
from validators.folha_pagamento.parser_folha_analitica import (
    eh_layout_folha_analitica,
    extrair_dados_folha_analitica,
)
from validators.folha_pagamento.parser_folha_femav import (
    eh_layout_folha_femav,
    extrair_dados_folha_femav,
)
from validators.folha_pagamento.parser_folha_delphos import (
    eh_layout_folha_delphos,
    extrair_dados_folha_delphos,
)
from validators.folha_pagamento.folha_model_extractor import extrair_folha_pagamento_de_texto


class TestFolhaPagamentoSimulado(unittest.TestCase):

    def test_regras_ignoram_calculo_como_empresa_e_trazem_varios_nomes(self):
        texto = """
        Empresa: Cálculo:
        FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
        Folha Mensal
        Junho de 2026
        BRUNO MACEDO ALVES
        CARLOS ALBERTO DIAS MARTINS
        FRANCISCO GERALDO DA SILVA NETO
        VALDER DE SOUSA VIEIRA
        NO. ESTAGIÁRIOS:
        """

        self.assertEqual(extrair_empresa(texto), "FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA")
        self.assertEqual(extrair_competencia_folha(texto), "06/2026")

        colaboradores = extrair_colaboradores(texto, empresa="FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA")
        nomes = [c["nome"] for c in colaboradores]

        self.assertCountEqual(
            nomes,
            [
                "Bruno Macedo Alves",
                "Carlos Alberto Dias Martins",
                "Francisco Geraldo Da Silva Neto",
                "Valder De Sousa Vieira",
            ],
        )
        self.assertNotIn("Cálculo", " ".join(nomes))
        self.assertNotIn("Estagiários", " ".join(nomes))

    def test_regras_extram_nome_competencia_e_nome_sem_cbo(self):
        texto = """
        FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
        CNPJ: 22.958.374/0001-57
        Folha Mensal
        Maio de 2026
        Nome do Funcionário
        2 GIULIANO LEO NATALE
        ENGENHEIRO MECANICO
        CBO
        214405
        Valor Liquido
        4.696,54
        """

        self.assertEqual(extrair_empresa(texto), "FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA")
        self.assertEqual(extrair_competencia_folha(texto), "05/2026")

        colaboradores = extrair_colaboradores(texto, empresa="FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA")
        nomes = [c["nome"] for c in colaboradores]

        self.assertEqual(nomes, ["Giuliano Leo Natale"])
        self.assertNotIn("CBO", " ".join(nomes))
        self.assertNotIn("Engenheiro Mecanico", " ".join(nomes))

    @patch("services.folha_service.extrair_documento_inteligente")
    @patch("services.folha_service.extrair_folha_inteligente")
    def test_processar_folha_pagamento_usa_payload_com_nome_e_valor(
        self,
        mock_extrair_folha_inteligente,
        mock_extrair_documento_inteligente,
    ):
        mock_extrair_documento_inteligente.return_value = {
            "texto": """
            FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
            CNPJ: 22.958.374/0001-57
            Folha Mensal
            Maio de 2026
            Nome do Funcionário
            2 GIULIANO LEO NATALE
            ENGENHEIRO MECANICO
            CBO 214405
            Valor Liquido R$ 4.696,54
            Nome do Funcionário
            27 IGOR AUGUSTO QUINTILIANO SILVA
            ANALISTA DE ENGENHARIA JUNIOR
            CBO 312105
            Valor Liquido R$ 2.813,26
            """,
            "qualidade": 0.92,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_folha_inteligente.return_value = {
            "empresa": "FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA",
            "competencia": "05/2026",
            "colaboradores": [
                {
                    "nome": "GIULIANO LEO NATALE",
                },
                {
                    "nome": "IGOR AUGUSTO QUINTILIANO SILVA",
                },
            ],
        }

        resultado = processar_folha_pagamento("folha_teste.pdf", "05/2026")

        self.assertEqual(resultado["status"], "Aprovado")
        self.assertFalse(resultado["ia_fallback"])
        self.assertEqual(resultado["competencia"], "05/2026")
        self.assertEqual(len(resultado["colaboradores"]), 2)
        self.assertEqual(resultado["colaboradores"][0]["nome"], "GIULIANO LEO NATALE")
        self.assertEqual(resultado["colaboradores"][1]["nome"], "IGOR AUGUSTO QUINTILIANO SILVA")
        self.assertCountEqual(resultado["ia_payload"]["campos_esperados"], ["nome", "competencia", "empresa"])

    @patch("services.folha_service.extrair_documento_inteligente")
    @patch("services.folha_service.extrair_folha_inteligente")
    def test_processar_folha_pagamento_traz_todos_os_nomes_e_empresa_correta(
        self,
        mock_extrair_folha_inteligente,
        mock_extrair_documento_inteligente,
    ):
        mock_extrair_documento_inteligente.return_value = {
            "texto": """
            Empresa: Cálculo:
            FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
            Folha Mensal
            Junho de 2026
            BRUNO MACEDO ALVES
            CARLOS ALBERTO DIAS MARTINS
            FRANCISCO GERALDO DA SILVA NETO
            VALDER DE SOUSA VIEIRA
            NO. ESTAGIÁRIOS:
            """,
            "qualidade": 0.95,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_folha_inteligente.return_value = {}

        resultado = processar_folha_pagamento("folha_teste.pdf", "06/2026")

        self.assertEqual(resultado["status"], "Aprovado")
        self.assertFalse(resultado["ia_fallback"])
        self.assertEqual(resultado["empresa"], "FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA")
        self.assertEqual(resultado["competencia"], "06/2026")
        self.assertCountEqual(
            [c["nome"] for c in resultado["colaboradores"]],
            [
                "BRUNO MACEDO ALVES",
                "CARLOS ALBERTO DIAS MARTINS",
                "FRANCISCO GERALDO DA SILVA NETO",
                "VALDER DE SOUSA VIEIRA",
            ],
        )

    @patch("services.folha_service.extrair_documento_inteligente")
    @patch("services.folha_service.extrair_folha_inteligente")
    @patch("services.folha_service.deve_chamar_ia")
    def test_processar_folha_pagamento_ignora_rubricas_e_mantem_so_nomes(
        self,
        mock_deve_chamar_ia,
        mock_extrair_folha_inteligente,
        mock_extrair_documento_inteligente,
    ):
        mock_extrair_documento_inteligente.return_value = {
            "texto": """
            Empresa: Cálculo:
            GESTAO EMPRESARIAL LTDA
            Competencia: 06/2026
            BRUNO MACEDO ALVES
            CARLOS ALBERTO DIAS MARTINS
            FRANCISCO GERALDO DA SILVA NETO
            VALDER DE SOUSA VIEIRA
            MSE SERVICE - SERVICOS E MANUTENCAO LTDA
            DESC VALE ALIMENTACAO
            REFLEXO EXTRAS DSR
            CONTRIBUICAO ASSIST. - SITRAMON
            VALE ALIMENTACAO INFORMATIVA
            """,
            "qualidade": 0.96,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_folha_inteligente.return_value = {}
        mock_deve_chamar_ia.return_value = (False, "ocr_local_suficiente")

        resultado = processar_folha_pagamento("folha_ruidosa.pdf", "06/2026")

        self.assertEqual(resultado["empresa"], "GESTAO EMPRESARIAL LTDA")
        self.assertEqual(resultado["competencia"], "06/2026")
        self.assertCountEqual(
            [c["nome"] for c in resultado["colaboradores"]],
            [
                "BRUNO MACEDO ALVES",
                "CARLOS ALBERTO DIAS MARTINS",
                "FRANCISCO GERALDO DA SILVA NETO",
                "VALDER DE SOUSA VIEIRA",
            ],
        )
        nomes_texto = " ".join(c["nome"] for c in resultado["colaboradores"])
        self.assertNotIn("MSE SERVICE", nomes_texto)
        self.assertNotIn("VALE ALIMENTACAO", nomes_texto)
        self.assertNotIn("REFLEXO EXTRAS", nomes_texto)
        self.assertNotIn("SITRAMON", nomes_texto)

    def test_extrair_colaboradores_layout_extrato_mensal_com_codigo_e_ruido(self):
        texto = """
        EXTRATO MENSAL
        05/2026
        Empresa:
        Competência:
        Folha Mensal
        44.913.506/0001-67
        201 - MSE SERVICE - SERVICOS E MANUTENCAO LTDA
        CNPJ:
        C.Custo: 905 - CP261 - NN - REFORÇO EST. METÁLICAS AP
        2266 ADAILTON DOMINGOS SANTOS DA SILVA
        Empr.:
        22/04/2026
        CPF:
        Situação:
        8781 DIAS NORMAIS
        250 REFLEXO EXTRAS DSR
        998
        697,26 D
        P
        400,29
        6,00
        1895 ALEJANDRO SERRA DA ROCHA
        Empr.:
        02/03/2026
        CPF:
        Situação:
        25 ADICIONAL NOTURNO (INFOR)
        HORAS MÊS:
        """

        colaboradores = extrair_colaboradores(texto, empresa="GESTAO EMPRESARIAL LTDA")
        nomes = [c["nome"] for c in colaboradores]

        self.assertIn("Adailton Domingos Santos Da Silva", nomes)
        self.assertIn("Alejandro Serra Da Rocha", nomes)
        self.assertNotIn("Dias Normais", nomes)
        self.assertNotIn("Adicional Noturno (Infor)", nomes)
        self.assertNotIn("Horas Mês:", nomes)
        self.assertNotIn("Extrato Mensal", nomes)

    def test_extrair_colaboradores_so_retornam_pessoas_em_linha_ruidosa(self):
        texto = """
        WINICIUS ALVES DIAS
        HORAS FALTAS PARCIAL
        IMPOSTO DE RENDA
        DESC ADT PASS FOLGA CAMPO
        AFASTADO DIREITOS INTEGRAIS:
        AFASTADO ACIDENTE DE TRABALHO:
        AFASTADO SERVICO MILITAR:
        PARTIC. CURSO/PROGRAMA DE QUALIFICAÇÃO:
        """

        colaboradores = extrair_colaboradores(texto, empresa="GESTAO EMPRESARIAL LTDA")
        nomes = [c["nome"] for c in colaboradores]

        self.assertEqual(nomes, ["Winicius Alves Dias"])

    def test_extrair_colaboradores_nao_descarta_nome_com_sufixo_junior(self):
        texto = """
        GESTAO EMPRESARIAL LTDA
        1937 OSMAR PEREIRA JUNIOR
        Empr.:
        CPF:
        2048 JOAO DA SILVA
        Empr.:
        CPF:
        """

        colaboradores = extrair_colaboradores(texto, empresa="GESTAO EMPRESARIAL LTDA")
        nomes = [c["nome"] for c in colaboradores]

        self.assertIn("Osmar Pereira Junior", nomes)
        self.assertIn("Joao Da Silva", nomes)

    def test_extrair_colaboradores_ignora_linha_de_resumo_de_rubricas(self):
        texto = """
        GESTAO EMPRESARIAL LTDA
        2 GIULIANO LEO NATALE
        Empr.:
        CPF:
        27 IGOR AUGUSTO QUINTILIANO SILVA
        Empr.:
        CPF:
        5 OSVALDO CESAR VIOTTI
        Empr.:
        CPF:
        RESUMO POR RUBRICAS DO SERVICO
        """

        colaboradores = extrair_colaboradores(texto, empresa="GESTAO EMPRESARIAL LTDA")
        nomes = [c["nome"] for c in colaboradores]

        self.assertCountEqual(
            nomes,
            [
                "Giuliano Leo Natale",
                "Igor Augusto Quintiliano Silva",
                "Osvaldo Cesar Viotti",
            ],
        )
        self.assertNotIn("Resumo Por Rubricas Do Servico", nomes)

    def test_extrair_colaboradores_ignora_linhas_de_resumo_contabil(self):
        texto = """
        EXTRATO MENSAL
        05/2026
        101 GIULIANO LEO NATALE
        Empr.:
        CPF:
        102 IGOR AUGUSTO QUINTILIANO SILVA
        Empr.:
        CPF:
        APURAÇÃO TRIBUTOS FEDERAIS
        SALDO A COMPENSAR
        SALDO A RECOLHER
        SALDO REMANESCENTE À RESTITUIR
        APURAÇÃO DO ENCARGO
        VALORES PAGOS A COOPERATIVAS
        """

        colaboradores = extrair_colaboradores(texto, empresa="GESTAO EMPRESARIAL LTDA")
        nomes = [c["nome"] for c in colaboradores]

        self.assertCountEqual(
            nomes,
            [
                "Giuliano Leo Natale",
                "Igor Augusto Quintiliano Silva",
            ],
        )
        self.assertNotIn("Apuração Tributos Federais", nomes)
        self.assertNotIn("Saldo A Compensar", nomes)
        self.assertNotIn("Saldo A Recolher", nomes)
        self.assertNotIn("Valores Pagos A Cooperativas", nomes)

    @patch("services.folha_service.extrair_documento_inteligente")
    @patch("services.folha_service.extrair_folha_inteligente")
    @patch("services.folha_service.deve_chamar_ia")
    def test_processar_folha_pagamento_retorna_na_ordem_da_folha(
        self,
        mock_deve_chamar_ia,
        mock_extrair_folha_inteligente,
        mock_extrair_documento_inteligente,
    ):
        mock_extrair_documento_inteligente.return_value = {
            "texto": """
            EXTRATO MENSAL
            06/2026
            101 ANA LIMA SILVA
            Empr.:
            CPF:
            102 BRUNO SOUSA DIAS
            Empr.:
            CPF:
            103 CARLA MENDES COSTA
            Empr.:
            CPF:
            """,
            "qualidade": 0.95,
            "metodo": "tesseract",
            "precisa_ia": True,
            "motivo_ia": "forcar_ordenacao",
        }
        mock_deve_chamar_ia.return_value = (True, "forcar_ia")
        mock_extrair_folha_inteligente.return_value = {
            "empresa": "GESTAO EMPRESARIAL LTDA",
            "competencia": "06/2026",
            "colaboradores": [
                {"nome": "CARLA MENDES COSTA"},
                {"nome": "BRUNO SOUSA DIAS"},
                {"nome": "ANA LIMA SILVA"},
            ],
        }

        resultado = processar_folha_pagamento("folha_ordem.pdf", "06/2026")

        self.assertEqual(
            [c["nome"] for c in resultado["colaboradores"]],
            ["ANA LIMA SILVA", "BRUNO SOUSA DIAS", "CARLA MENDES COSTA"],
        )

    @patch("services.folha_service.extrair_documento_inteligente")
    @patch("services.folha_service.extrair_folha_inteligente")
    @patch("services.folha_service.deve_chamar_ia")
    def test_processar_folha_pagamento_prioriza_competencia_da_primeira_pagina(
        self,
        mock_deve_chamar_ia,
        mock_extrair_folha_inteligente,
        mock_extrair_documento_inteligente,
    ):
        mock_extrair_documento_inteligente.return_value = {
            "texto": """
            EXTRATO MENSAL
            06/2026
            101 ANA LIMA SILVA
            Empr.:
            CPF:
            \f
            EXTRATO MENSAL
            07/2026
            102 BRUNO SOUSA DIAS
            Empr.:
            CPF:
            """,
            "paginas": [
                {"pagina": 1, "texto": "EXTRATO MENSAL\n06/2026\n101 ANA LIMA SILVA\nEmpr.:\nCPF:"},
                {"pagina": 2, "texto": "EXTRATO MENSAL\n07/2026\n102 BRUNO SOUSA DIAS\nEmpr.:\nCPF:"},
            ],
            "qualidade": 0.96,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_deve_chamar_ia.return_value = (False, "ocr_local_suficiente")
        mock_extrair_folha_inteligente.return_value = {}

        resultado = processar_folha_pagamento("folha_duas_paginas.pdf", "06/2026")

        self.assertEqual(resultado["competencia"], "06/2026")
        self.assertEqual([c["nome"] for c in resultado["colaboradores"]], ["ANA LIMA SILVA", "BRUNO SOUSA DIAS"])

    def test_extrair_competencia_ignora_data_de_emissao_e_pega_cabecalho(self):
        texto = """
        Página:
        181/224
        Emissão:
        06/06/2026
        Horas:
        08:51:14
        EXTRATO MENSAL
        05/2026
        Empresa:
        Competência:
        Folha Mensal
        """

        self.assertEqual(extrair_competencia_folha(texto), "05/2026")


    def test_regras_nao_usam_extrato_mensal_como_empresa(self):
        texto = """
        EXTRATO MENSAL
        05/2026
        FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
        """

        empresa = extrair_empresa(texto)

        self.assertEqual(empresa, "FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA")
        self.assertNotEqual(empresa, "EXTRATO MENSAL")

    def test_regras_usam_estabelecimento_como_ancora_de_empresa(self):
        texto = """
        ESTABELECIMENTO:
        FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA
        HORAS SEMANAIS:
        """

        empresa = extrair_empresa(texto)

        self.assertEqual(empresa, "FNEC - CONSULTORIA E SERVICOS TECNICOS LTDA")
        self.assertNotEqual(empresa, "HORAS SEMANAIS")

    def test_extrair_colaboradores_ignora_horas_semanais_e_itens_de_resumo(self):
        texto = """
        EXTRATO MENSAL
        Horas Semanais:
        ELDI PEREIRA COSTA
        ERIK LUCAS MARIA DOS SANTOS
        GILBERTO ALVES DA SILVA
        MARCIO ALVES MARQUES
        MILTON JORGE CUSTODIO
        OSVALDO DOMINGUES DA SILVA
        SIDNEY PEREIRA COSTA
        VINICIUS VICENTE FIRMINO BUZZO
        ZENILSON DIAS COSTA
        VALOR DE PIS
        NÚMERO DE DIRETORES
        NÚMERO DE AUTÔNOMOS
        """

        empresa = extrair_empresa(texto)
        colaboradores = extrair_colaboradores(texto, empresa=empresa)
        nomes = [c["nome"] for c in colaboradores]

        self.assertNotEqual(empresa, "Horas Semanais")
        self.assertNotEqual(empresa, "Horas Semanais:")
        self.assertCountEqual(
            nomes,
            [
                "Eldi Pereira Costa",
                "Erik Lucas Maria Dos Santos",
                "Gilberto Alves Da Silva",
                "Marcio Alves Marques",
                "Milton Jorge Custodio",
                "Osvaldo Domingues Da Silva",
                "Sidney Pereira Costa",
                "Vinicius Vicente Firmino Buzzo",
                "Zenilson Dias Costa",
            ],
        )
        self.assertNotIn("Valor De Pis", nomes)
        self.assertNotIn("Numero De Diretores", nomes)
        self.assertNotIn("Numero De Autonomos", nomes)

    def test_parser_relacao_calculo_extrai_empresa_competencia_e_colaboradores(self):
        texto = """
        Empresa: 0192 - JM MONTAGENS LTDA 13/02/2026 10:59 Pág:0001
        Inscrição Federal: 56.823.979/0001-52 Telefone: (11) 4193-2198
        Endereço: Rua RIO TUBARAO 16 Complemento:
        Bairro: JARDIM PIRITUBA Município: São Paulo - SP
        Relação de Cálculo - Período: 01/01/2026 a 31/01/2026 - Mensal
        0192 - JM MONTAGENS LTDA
        Analítico Contratos
        Func: 12 BALTAZAR CARONE Adm 06/01/2026 Dem Dep.IR: 00 Dedução IR.: 0,00 Dep.SF: 00
        Cargo: ENCARREGADO C.H.M: 220:00 Salário: 6.000,00 Cbo: 710205 Sind: 0001 F.Reg: Situação: Trabalhando
        Filial: 0001 - CNPJ/CPF: 56.823.979/0001-52 Organograma: 001 - OPERACIONAL
        Func: 13 FRANCEILDO RAIMUNDO SOBRINHO Adm 06/01/2026 Dem Dep.IR: 00 Dedução IR.: 0,00 Dep.SF: 00
        Cargo: ENCANADOR I C.H.M: 220:00 Salário: 6.000,00 Cbo: 724110 Sind: 0001 F.Reg: Situação: Trabalhando
        Filial: 0001 - CNPJ/CPF: 56.823.979/0001-52 Organograma: 001 - OPERACIONAL
        Func: 14 INOCENCIO VITOR DA SILVA Adm 06/01/2026 Dem Dep.IR: 00 Dedução IR.: 0,00 Dep.SF: 00
        Cargo: ENCANADOR C.H.M: 220:00 Salário: 6.000,00 Cbo: 724110 Sind: 0001 F.Reg: Situação: Trabalhando
        Filial: 0001 - CNPJ/CPF: 56.823.979/0001-52 Organograma: 001 - OPERACIONAL
        Total Empresa: 0192 - JM MONTAGENS LTDA
        Resumo FGTS Digital
        """

        self.assertTrue(eh_layout_relacao_calculo(texto))
        dados = extrair_dados_relacao_calculo(texto)

        self.assertEqual(dados["empresa"], "JM MONTAGENS LTDA")
        self.assertEqual(dados["competencia"], "01/2026")
        self.assertEqual(
            [c["nome"] for c in dados["colaboradores"]],
            [
                "Baltazar Carone",
                "Franceildo Raimundo Sobrinho",
                "Inocencio Vitor Da Silva",
            ],
        )

    def test_parser_extrato_mensal_extrai_empresa_e_somente_colaboradores(self):
        texto = """
        Página:
        1/6
        Emissão:
        15/04/2026
        Horas:
        19:57:22
        Serviços: 23
        EXTRATO MENSAL
        03/2026
        Empresa:
        Competência:
        Cálculo:
        Folha Mensal
        44.413.036/0001-72
        13 - MORAIS CONSTRULOK CONSTRUCOES E LOCACOES
        CNPJ:
        Serviço: 23 - AUDITORIO SIRIUS
        Matr. eSocial:
        1219
        1219 ANDERSON RODRIGUES SILVA
        Empr.:
        20/02/2026
        Adm:
        166.531.214-96
        Trabalhando
        CPF:
        Situação:
        Celetista
        Vínculo:
        220,00
        Horas Mês:
        1
        1
        Depto:
        CC:
        Cargo:
        66 ENCARREGADO DE OBRAS
        C.B.O:
        710205
        Sistema licenciado para WALLACE CRISTINO BISPO
        Matr. eSocial:
        1217
        1217 AURICIO DOS SANTOS MARCELO
        Empr.:
        19/02/2026
        Adm:
        072.570.413-69
        Trabalhando
        CPF:
        Situação:
        Celetista
        Vínculo:
        220,00
        Horas Mês:
        1
        1
        Depto:
        CC:
        Cargo:
        75 SERVENTE DE OBRAS
        C.B.O:
        717020
        Resumo por Rubricas do Serviço
        Totais por Centro de Custos
        """

        self.assertTrue(eh_layout_extrato_mensal(texto))
        dados = extrair_dados_extrato_mensal(texto)

        self.assertEqual(dados["empresa"], "MORAIS CONSTRULOK CONSTRUCOES E LOCACOES")
        self.assertEqual(dados["competencia"], "03/2026")
        self.assertEqual(
            [c["nome"] for c in dados["colaboradores"]],
            [
                "Anderson Rodrigues Silva",
                "Auricio Dos Santos Marcelo",
            ],
        )
        nomes = " ".join(c["nome"] for c in dados["colaboradores"])
        self.assertNotIn("Sistema Licenciado", nomes)
        self.assertNotIn("Totais Por Centro De Custos", nomes)

    def test_parser_scivisual_extrai_funcionarios_de_folha_analitica(self):
        texto = """
        Folha Analitica de Abril/2026  Lote 1 a 99999999 Emitida em: 24/04/2026 16:01:16 Pagina: 001
        Emp-Fil:001-001 EFETIVA RH - SERVICOS TEMPORARIOS LTDA                                (33.069.317/0001-33)
        -----------------------------------------------------------------------------------------------------------
        Funcionario 177821 MARCELO MOLINARI                              Salario Mes     5.632,00  220,00 Horas Mes
        CPF: 154.936.008-62
        Funcão:  TECNICO SEG.TRABALHO                 Admissão 04/12/2024 Dep.SF: 00 Dep.IR: 00
        Lote(s): B.01043
        Funcionário 177822 CARLOS HENRIQUE ALMEIDA                        Salario Mes     4.112,00  220,00 Horas Mes
        CPF: 154.936.008-63
        Funcão:  TECNICO SEG.TRABALHO                 Admissão 04/12/2024 Dep.SF: 00 Dep.IR: 00
        """

        self.assertTrue(eh_layout_scivisual(texto))
        dados = extrair_dados_scivisual(texto)

        self.assertEqual(dados["empresa"], "EFETIVA RH - SERVICOS TEMPORARIOS LTDA")
        self.assertEqual(dados["competencia"], "04/2026")
        self.assertEqual(
            [c["nome"] for c in dados["colaboradores"]],
            [
                "Marcelo Molinari",
                "Carlos Henrique Almeida",
            ],
        )

    def test_parser_scivisual_extrai_empresa_local_e_colaborador(self):
        texto = """
        Pág:5
        Folha de Pagamento
        MENDES E ARAUJO HIDRAULICA DE AR CONDI
        CNPJ/CEI: 09.450.086/0001-29
        Período de: 01/04/2026 a 30/04/2026
        Endereço:
        Bairro:
        Cidade:
        UF:SP
        Nova Cerejeira
        Atibaia
        Rua das Açucenas 40
        Apelido:
        Razão Social:
        1000
        Local: 58 - MSE ENGENHARIA LTDA
        Cód:
        Nome:
        Função:
        Salário:
        Dep. IR:
        0
        5.450,00
        ENCARREGADO
        ALMIR ARAUJO LUCAS
        5
        Admissão: 05/01/2009
        Ativo
        Situação:
        """

        self.assertTrue(eh_layout_scivisual(texto))
        dados = extrair_dados_scivisual(texto)

        self.assertEqual(dados["empresa"], "MENDES E ARAUJO HIDRAULICA DE AR CONDI")
        self.assertEqual(dados["competencia"], "04/2026")
        self.assertIn("Almir Araujo Lucas", [c["nome"] for c in dados["colaboradores"]])

    def test_parser_espelho_resumo_folha_extrai_empresa_competencia_e_colaboradores(self):
        texto = """
        Espelho e resumo da folha mensal referente ao mês de ABRIL/2026 Página: 1
        Empresa: 10121 - A.L BUGUISKI CONTROLE TECNOLOGICO E SERVICOS LTDA Araquari/SC - CNPJ:43.105.124/0001-44
        NOME DO COLABORADOR SF IR
        PROVENTOS REFERÊNCIA VALOR DESCONTOS REFERÊNCIA VALOR
        900000 ANDERSON LUIZ BUGUISKI o o Admissão em 12/08/2021 Salário base 7.786,02. Horas mensais: 220,00
        33 CAMILA MARIA DE SOUZA SANTOS O O Admissão em 30/10/2025 Salário base 3.100,00 Horas mensais: 220,00
        7 DEISE PAMELA DE DEEKE 1 2 Admissão em 14/09/2022 Salário base 3.797,90 Horas mensais: 220,00
        24 FRANCISCO EVANDIR MELO DE
        SOUZA
        16 GABRIEL LINCOLN DE MIRA DA SILVA o o Admissão em 16/05/2024 Salário base 2.500,00 Horas mensais: 220,00
        Total de proventos - > 7.786,02 Total de descontos - > 1.853,36
        Base INSS Valor INSS Base FGTS Valor FGTS Base IRRF Base Rais Base salário família
        Folha 7.786,02 856,46 0,00 0,00 6.929,56 0,00 0,00 Líquido - > 5.932,66
        BREIS ESCRITORIO DE CONTABILIDADE 08/05/2026 10:25 - SCI Ambiente Contábil ÚNICO
        """

        self.assertTrue(eh_layout_espelho_resumo_folha(texto))
        dados = extrair_dados_espelho_resumo_folha(texto)

        self.assertEqual(dados["empresa"], "A.L BUGUISKI CONTROLE TECNOLOGICO E SERVICOS LTDA")
        self.assertEqual(dados["competencia"], "04/2026")
        self.assertEqual(
            [c["nome"] for c in dados["colaboradores"]],
            [
                "Anderson Luiz Buguiski",
                "Camila Maria De Souza Santos",
                "Deise Pamela De Deeke",
                "Francisco Evandir Melo De Souza",
                "Gabriel Lincoln De Mira Da Silva",
            ],
        )
        nomes = " ".join(c["nome"] for c in dados["colaboradores"])
        self.assertNotIn("Breis Escritorio De Contabilidade", nomes)

    def test_parser_folha_analitica_extrai_empresa_e_colaboradores(self):
        texto = """
        FOLHA DE PAGAMENTO ANALÍTICA
        Empresa : SOLLO PRODUCOES E EVENTOS LTDA ( 00749) Página : 0000
        End. : RUA JOAO PACULDINO, 168 CNPJ/CEI: 21183848000173
        Ref.: 01/04/2026 a 30/04/2026 Dpto : NOVO NORDISK PRODUÇÃO FARM/
        001013 LUIZ GUILHERME ALMEIDA TRINDADE 1.621,00 Função : Montador Livro: 0000 Folha.: OC
        Admissão : 08/12/2021 DepIR: 1 Dep SF:
        001 Salário Base 030,00 1.621,00
        039 Cesta Básica 340,00
        101 Ajuda de Custo 539,00
        406 Adiantamento Salarial 800,00
        599 Salário Família 001,00 67,54
        606 Adiantamento 800,00
        903 INSS Folha 121,57
        Resumo do Liquido 3.367,54 921,57 ******2 445,97
        Base INSS 1.621,00 Base FGTS 1.621,00 FGTS 129,68 Base IRRF 1.642,0
        OO1018 CHARLES EDUARDO FELIX MARTINS 1.724,89 Fun??o : Encarregado Servicos Livro: 0000 Folha.: OO
        Admiss?o : 13/11/2023 DepIR: O DepSF:
        010124 ROGERIO DA CRUZ SANTOS 1.976,51 Função : Motorista de carro d Livro: 0000 Folha.: OOO
        Admissão : 09/10/2024 DepIR: O DepSF: O
        010130 AROLDO CESAR QUARESMA 1.621,00 Função : Montador Livro: 0000 Folha. :10130
        Admissão :08/11/2025 DepIR: O DepSF: O
        """

        self.assertTrue(eh_layout_folha_analitica(texto))
        dados = extrair_dados_folha_analitica(texto)

        self.assertEqual(dados["empresa"], "SOLLO PRODUCOES E EVENTOS LTDA")
        self.assertEqual(dados["competencia"], "04/2026")
        self.assertEqual(
            [c["nome"] for c in dados["colaboradores"]],
            [
                "Luiz Guilherme Almeida Trindade",
                "Charles Eduardo Felix Martins",
                "Rogerio Da Cruz Santos",
                "Aroldo Cesar Quaresma",
            ],
        )

    def test_parser_folha_cabecalho_nome_extrai_empresa_competencia_e_colaboradores(self):
        texto = """
        Folha de Pagamento 05/05/2026 09:41:46
        Apelido: 1185 Razão Social: CIVIL AR EQUIPAMENTOS LTDA Pág:20
        CNPJ/CEI: 01.363.941/0001-52 Inscrição: 145.117.496.115 Período de: 01/04/2026 a 30/04/2026
        Cód: 607 Nome: DEMERSON MENDES ROCHA Função: 1/2 OFICIAL DE AR COND "A" Dep. IR: 1
        Admissão: 09/03/2026 Situação: Ativo Ocorrência: 1 Salário: 2.214,00
        Cód: 336 Nome: JOSE CARLOS MENDES DOS SANTOS Função: 1/2 OFICIAL DE AR COND "A" Dep. IR: 1
        Admissão: 02/05/2014 Situação: Ativo Ocorrência: 1 Salário: 2.471,00
        """

        self.assertTrue(eh_layout_folha_cabecalho_nome(texto))
        dados = extrair_dados_folha_cabecalho_nome(texto)

        self.assertEqual(dados["empresa"], "CIVIL AR EQUIPAMENTOS LTDA")
        self.assertEqual(dados["competencia"], "04/2026")
        self.assertEqual(
            [c["nome"] for c in dados["colaboradores"]],
            [
                "Demerson Mendes Rocha",
                "Jose Carlos Mendes Dos Santos",
            ],
        )

    def test_parser_folha_femav_extrai_empresa_competencia_e_colaboradores(self):
        texto = """
        * F 0 L H A   D E   P A G A M E N T O   D E   E M P R E G A D O S *
        Competência: Abril/2026
        Empresa:
        0155 - FEMAV LOCACAO DE MAQUINAS E EQUIPAMENTOS LTDA
        DIVISÃO RH   N.REG        CPF      NOME                                                 CBO     FUNÇÃO                      SALARIO
        002.000.000  00029  150.367.116-02 ANDERSON MIGUEL LEAL DE ABREU                       314410 - TEC.MANUT.PLENO             Mensal
        """

        self.assertTrue(eh_layout_folha_femav(texto))
        dados = extrair_dados_folha_femav(texto)

        self.assertEqual(dados["empresa"], "FEMAV LOCACAO DE MAQUINAS E EQUIPAMENTOS LTDA")
        self.assertEqual(dados["competencia"], "04/2026")
        self.assertEqual([c["nome"] for c in dados["colaboradores"]], ["Anderson Miguel Leal De Abreu"])

    def test_parser_folha_delphos_extrai_empresa_competencia_e_colaboradores(self):
        texto = """
        DELPHOS
        EMPREGADOR: N.PJ. Referência
        009 DELPHOS SERV EMPRES COM EQUIP ELET LTDA 08.288.889/0001-66 04/2026
        Registro Nome Cargo CPF CCusto Dir/Dep/Set/Sec
        098407-0 ROBERTO RODRIGUES VIGIA 091.657.158-02 5 00/99984/0D000/00013
        """

        self.assertTrue(eh_layout_folha_delphos(texto))
        dados = extrair_dados_folha_delphos(texto)

        self.assertEqual(dados["empresa"], "DELPHOS SERV EMPRES COM EQUIP ELET LTDA")
        self.assertEqual(dados["competencia"], "04/2026")
        self.assertEqual([c["nome"] for c in dados["colaboradores"]], ["Roberto Rodrigues"])

    def test_folha_model_extractor_extrai_modelo_razao_social_competencia_e_nomes(self):
        texto = """
        Empresa:
        0568 - PREMIER TOPOGRAFIA E PROJETOS LTDA
        24/04/2026 11:13 PÃ¡g:0001
        Competencia: 03/2026
        RelaÃ§Ã£o de CÃ¡lculo - PerÃ­odo: 01/03/2026 a 31/03/2026 - Mensal
        Func: 18 ERIK RITTER MARIATI Adm 05/03/2026 Dem Dep.IR: 00
        Cargo: ENGENHEIRO CIVIL
        Func: 27 BRUNO SOUSA DIAS Adm 07/03/2026 Dem Dep.IR: 00
        Cargo: AJUDANTE
        """

        dados = extrair_folha_pagamento_de_texto(texto)

        self.assertEqual(dados.modelo, "relacao_calculo_analitico")
        self.assertGreaterEqual(dados.confianca_modelo, 0.2)
        self.assertEqual(dados.razao_social, "PREMIER TOPOGRAFIA E PROJETOS LTDA")
        self.assertEqual(dados.competencia, "03/2026")
        self.assertEqual(
            dados.nomes,
            [
                "ERIK RITTER MARIATI",
                "BRUNO SOUSA DIAS",
            ],
        )

    @patch("services.folha_service.extrair_documento_inteligente")
    @patch("services.folha_service.extrair_folha_modelo_de_texto")
    @patch("services.folha_service.deve_chamar_ia")
    def test_processar_folha_pagamento_usa_extrator_modelo_auxiliar(
        self,
        mock_deve_chamar_ia,
        mock_extrair_folha_modelo_de_texto,
        mock_extrair_documento_inteligente,
    ):
        mock_extrair_documento_inteligente.return_value = {
            "texto": """
            DOCUMENTO DE FOLHA COM LAYOUT NOVO
            BLOCO DE TESTE SEM ANCHORS DO PARSER ANTIGO
            VALIDAÇÃO PADRÃO DO MODELO NOVO
            """,
            "qualidade": 0.93,
            "metodo": "tesseract",
            "precisa_ia": False,
            "motivo_ia": "ocr_local_suficiente",
        }
        mock_extrair_folha_modelo_de_texto.return_value = {
            "modelo": "layout_novo",
            "confianca_modelo": 0.91,
            "razao_social": "EMPRESA MODELO LTDA",
            "competencia": "06/2026",
            "nomes": ["ANA LIMA SILVA", "BRUNO SOUZA DIAS"],
            "evidencias": {
                "razao_social": {"origem": "mock"},
                "competencia": {"origem": "mock"},
                "nomes": {"origem": "mock"},
            },
            "avisos": ["mock"],
        }
        mock_deve_chamar_ia.return_value = (False, "ocr_local_suficiente")

        resultado = processar_folha_pagamento("folha_modelo_novo.pdf", "06/2026")

        self.assertEqual(resultado["empresa"], "EMPRESA MODELO LTDA")
        self.assertEqual(resultado["competencia"], "06/2026")
        self.assertEqual([c["nome"] for c in resultado["colaboradores"]], ["ANA LIMA SILVA", "BRUNO SOUZA DIAS"])
        self.assertEqual(resultado["folha_modelo"], "layout_novo")
        self.assertEqual(resultado["folha_confianca_modelo"], 0.91)
        self.assertEqual(resultado["folha_evidencias"]["razao_social"]["origem"], "mock")
        self.assertEqual(resultado["folha_avisos"], ["mock"])


if __name__ == "__main__":
    unittest.main()
