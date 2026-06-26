import re

from validators.fgts.guia.parser import extrair_resumo_guia_comprovante
from validators.fgts.relatorio.parser import extrair_colaboradores_fgts_digital, extrair_resumo_fgts_digital
from validators.fgts.secoes import validar_secoes
from utils.gemini.fgts import extrair_fgts
from utils.ocr.ocr_fgts import extrair_texto_fgts


class FGTSValidator:
    def __init__(self):
        self.regex_gfd = r"(\d{16}-\d)"

    def limpar_numero(self, texto):
        if not texto:
            return ""
        return re.sub(r"[^\d]", "", str(texto))

    def normalizar_nome_empresa(self, texto):
        if not texto:
            return ""
        texto = re.sub(r"[^A-Z0-9 ]", " ", str(texto).upper())
        return " ".join(texto.split())

    def valores_iguais(self, primeiro, segundo, tolerancia=0.01):
        try:
            return abs(float(primeiro or 0) - float(segundo or 0)) <= tolerancia
        except (TypeError, ValueError):
            return False

    def remover_duplicados(self, lista):
        vistos = set()
        resultado = []

        for item in lista:
            chave = (item.get("nome"), item.get("tomador"))
            if chave not in vistos:
                vistos.add(chave)
                resultado.append(item)

        return resultado

    def analisar(self, relatorio_pdf, guia_pdf, competencia_esperada, tomador_alvo=None):
        print("\n================= FGTS VALIDATOR =================")

        print("[FGTS] Lendo GUIA...")
        texto_guia = extrair_texto_fgts(guia_pdf)

        print("[FGTS] Lendo RELATORIO...")
        texto_rel = extrair_texto_fgts(relatorio_pdf)

        print("[FGTS] Extraindo resumo do FGTS Digital...")
        dados_rel = extrair_resumo_fgts_digital(texto_rel)

        print("[FGTS] Extraindo resumo da guia + comprovante...")
        dados_guia = extrair_resumo_guia_comprovante(texto_guia)

        dados_ia_rel = {}
        dados_ia_guia = {}

        if not dados_rel.get("empresa") or not dados_rel.get("competencia") or not dados_rel.get("valor_total"):
            print("[FGTS] Gemini fallback para relatorio...")
            dados_ia_rel = extrair_fgts(texto_rel) or {}
            dados_rel["empresa"] = dados_rel.get("empresa") or dados_ia_rel.get("empresa")
            dados_rel["competencia"] = dados_rel.get("competencia") or dados_ia_rel.get("competencia")
            dados_rel["valor_total"] = dados_rel.get("valor_total") or float(dados_ia_rel.get("valor_total", 0) or 0)

        if not dados_guia.get("empresa") or not dados_guia.get("competencia") or not dados_guia.get("valor_guia"):
            print("[FGTS] Gemini fallback para guia...")
            dados_ia_guia = extrair_fgts(texto_guia) or {}
            dados_guia["empresa"] = dados_guia.get("empresa") or dados_ia_guia.get("empresa")
            dados_guia["competencia"] = dados_guia.get("competencia") or dados_ia_guia.get("competencia")
            dados_guia["valor_guia"] = dados_guia.get("valor_guia") or float(dados_ia_guia.get("valor_total", 0) or 0)
            dados_guia["valor_total"] = dados_guia.get("valor_total") or dados_guia.get("valor_guia")

        valor_fgts_digital = dados_rel.get("valor_total") or 0
        valor_guia = dados_guia.get("valor_guia") or dados_guia.get("valor_total") or 0
        valor_comprovante = dados_guia.get("valor_comprovante") or valor_guia

        empresa_ok = True
        if dados_rel.get("empresa") and dados_guia.get("empresa"):
            empresa_ok = (
                self.normalizar_nome_empresa(dados_rel["empresa"])
                == self.normalizar_nome_empresa(dados_guia["empresa"])
            )

        competencia_doc = dados_rel.get("competencia") or dados_guia.get("competencia")
        competencia_ok = True
        if competencia_esperada:
            competencia_ok = competencia_doc == competencia_esperada

        tomador_informado = tomador_alvo or ""
        tomador_ok = True
        tomador_input_norm = self.limpar_numero(tomador_alvo)
        if tomador_input_norm:
            tomador_ok = tomador_input_norm in self.limpar_numero(texto_rel)

        fgts_guia_ok = self.valores_iguais(valor_fgts_digital, valor_guia)
        guia_comprovante_ok = self.valores_iguais(valor_guia, valor_comprovante)
        valor_ok = fgts_guia_ok and guia_comprovante_ok

        erros = []
        avisos = []

        if not dados_rel.get("empresa"):
            erros.append("Empresa nao identificada no FGTS Digital")
        if not competencia_doc:
            erros.append("Competencia nao identificada")
        if competencia_esperada and not competencia_ok:
            erros.append(f"Competencia divergente ({competencia_doc or '-'})")
        if not valor_fgts_digital:
            erros.append("Valor a pagar nao identificado no FGTS Digital")
        if not valor_guia:
            erros.append("Valor da guia nao identificado")
        if tomador_input_norm and not tomador_ok:
            erros.append("Tomador informado nao encontrado no FGTS Digital")
        if dados_rel.get("empresa") and dados_guia.get("empresa") and not empresa_ok:
            erros.append("Empresa divergente entre FGTS Digital e guia")
        if valor_fgts_digital and valor_guia and not fgts_guia_ok:
            erros.append("Valor do FGTS Digital diverge da guia e comprovante")
        if valor_guia and valor_comprovante and not guia_comprovante_ok:
            erros.append("Valor da guia divergente do comprovante")

        documentos_status = validar_secoes(texto_rel)
        documentos_pendentes = [
            nome for nome, ok in documentos_status.items()
            if not ok
        ]
        for documento in documentos_pendentes:
            if documento == "Relação de Tomadores":
                avisos.append("Relação de Tomadores de Serviço não identificada; validação considerada até a Relação de Tipos de Valor")
                continue
            erros.append(f"Documento pendente: {documento}")

        trabalhadores_exibicao = extrair_colaboradores_fgts_digital(texto_rel, tomador_alvo)
        if not trabalhadores_exibicao:
            trabalhadores_exibicao = self._extrair_trabalhadores_para_exibicao(dados_ia_rel, tomador_alvo)
        linhas = self._montar_linhas_dashboard(erros, avisos, texto_rel)

        if erros:
            status = "Reprovado"
        elif avisos:
            status = "Parcial"
        else:
            status = "Aprovado"

        if status == "Aprovado":
            mensagem = "FGTS validado com sucesso!"
        elif status == "Parcial" and any("Tomadores de Serviço" in aviso for aviso in avisos):
            mensagem = "Relação de Tomadores de Serviço não identificada; validação considerada até a Relação de Tipos de Valor."
        elif guia_comprovante_ok and valor_fgts_digital and valor_guia and not fgts_guia_ok:
            mensagem = (
                "Valor da guia e comprovante conferem entre si, "
                "mas divergem do valor do FGTS Digital."
            )
        else:
            mensagem = "Divergencias identificadas."

        return {
            "status": status,
            "mensagem": mensagem,
            "empresa": dados_rel.get("empresa"),
            "competencia": competencia_doc,
            "data_pagamento": dados_guia.get("data_pagamento"),
            "tomador_informado": tomador_informado,
            "tomador_ok": tomador_ok,
            "valor_a_pagar": valor_fgts_digital,
            "valor_fgts_digital": valor_fgts_digital,
            "valor_guia": valor_guia,
            "valor_comprovante": valor_comprovante,
            "empresa_ok": empresa_ok,
            "competencia_ok": competencia_ok,
            "valor_ok": valor_ok,
            "guia_comprovante_ok": guia_comprovante_ok,
            "documentos": documentos_status,
            "trabalhadores": trabalhadores_exibicao,
            "colaboradores": trabalhadores_exibicao,
            "linhas": linhas,
            "erros": erros,
            "avisos": avisos,
        }

    def _extrair_trabalhadores_para_exibicao(self, dados_ia_rel, tomador_alvo=None):
        trabalhadores = []
        tomador_input_norm = self.limpar_numero(tomador_alvo)

        for tomador in dados_ia_rel.get("tomadores", []):
            tomador_raw = tomador.get("cnpj_ou_cno")
            tomador_doc = self.limpar_numero(tomador_raw)

            if not tomador_doc:
                continue

            if tomador_input_norm and tomador_doc != tomador_input_norm:
                continue

            for colaborador in tomador.get("colaboradores", []):
                trabalhadores.append(
                    {
                        "nome": colaborador.get("nome"),
                        "valor": float(colaborador.get("valor", 0) or 0),
                        "tomador": tomador_raw,
                    }
                )

        return self.remover_duplicados(trabalhadores)

    def _montar_linhas_dashboard(self, erros, avisos, texto_rel):
        linhas = []

        for erro in erros:
            linhas.append({"item": erro, "ok": False})

        for aviso in avisos:
            linhas.append({"item": aviso, "ok": True})

        secoes = validar_secoes(texto_rel)
        for nome, ok in secoes.items():
            linhas.append({"item": f"Relatorio (OCR): {nome}", "ok": ok})

        return linhas
