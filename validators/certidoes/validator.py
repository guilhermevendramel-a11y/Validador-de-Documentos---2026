import re
from datetime import datetime, timedelta

from utils.ocr import extrair_texto_pdf_inteligente


class CNDValidator:
    TIPOS_ESPERADOS = {"CND INSS / CND Federal", "CNDT", "CRF FGTS"}

    def _normalizar_tipo(self, texto_upper):
        if "TRABALHIST" in texto_upper or "CNDT" in texto_upper:
            return "CNDT"
        if (
            "TRIBUTOS FEDERAIS" in texto_upper
            or "DIVIDA ATIVA DA UNIAO" in texto_upper
            or "DÍVIDA ATIVA DA UNIÃO" in texto_upper
            or "PROCURADORIA-GERAL DA FAZENDA NACIONAL" in texto_upper
        ):
            return "CND INSS / CND Federal"
        if "REGULARIDADE DO FGTS" in texto_upper or "CRF" in texto_upper:
            return "CRF FGTS"
        return "Desconhecido"

    def _extrair_cnpj(self, texto):
        match = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto or "")
        return match.group(0) if match else None

    def _extrair_razao_social(self, texto, tipo):
        texto = texto or ""
        linhas = [l.strip() for l in texto.splitlines() if l.strip()]
        linhas_upper = [l.upper() for l in linhas]

        for i, linha in enumerate(linhas_upper):
            if "RAZAO SOCIAL" in linha or "RAZÃO SOCIAL" in linha:
                atual = linhas[i]
                if ":" in atual and atual.split(":", 1)[1].strip():
                    return atual.split(":", 1)[1].strip()[:140]
                if i + 1 < len(linhas):
                    prox = linhas[i + 1].strip(": ").strip()
                    if prox and prox.upper() not in {"CNPJ", "INSCRICAO", "INSCRIÇÃO"}:
                        return prox[:140]

            if linha in {"RAZAO", "RAZÃO"}:
                if i + 2 < len(linhas) and linhas_upper[i + 1].startswith("SOCIAL"):
                    return linhas[i + 2].strip(": ").strip()[:140]

        padroes = [
            r"RAZAO\s+SOCIAL\s*[:\-]?\s*(.+)",
            r"NOME\s+EMPRESARIAL\s*[:\-]?\s*(.+)",
            r"NOME\s*[:\-]?\s*(.+)",
        ]
        for padrao in padroes:
            m = re.search(padrao, texto, re.IGNORECASE)
            if m:
                return m.group(1).strip()[:140]

        if tipo == "CNDT":
            for i, linha in enumerate(linhas):
                if "DEVEDOR" in linha.upper() and i + 1 < len(linhas):
                    return linhas[i + 1][:140]

        cnpj = self._extrair_cnpj(texto)
        if cnpj:
            for i, linha in enumerate(linhas):
                if cnpj in linha and i > 0:
                    candidato = linhas[i - 1]
                    if len(candidato) > 4:
                        return candidato[:140]

        return "Nao identificada"

    def _extrair_validade(self, texto, tipo):
        texto = texto or ""

        m = re.search(r"V[ÁA]LID[AO]\s*AT[EÉ]\s*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
        if m:
            return m.group(1)

        if tipo == "CRF FGTS":
            periodo = re.search(
                r"(\d{2}/\d{2}/\d{4})\s*(?:A|ATE|AT[EÉ]|-|–)\s*(\d{2}/\d{2}/\d{4})",
                texto,
                re.IGNORECASE,
            )
            if periodo:
                return periodo.group(2)

        datas = re.findall(r"(\d{2}/\d{2}/\d{4})", texto)
        return datas[-1] if datas else None

    def _fim_do_mes(self, dt_ref):
        primeiro_mes_seguinte = (dt_ref.replace(day=1) + timedelta(days=32)).replace(day=1)
        return primeiro_mes_seguinte - timedelta(days=1)

    def analisar(self, caminhos_pdf, cnpj_esperado, competencia_alvo=None):
        try:
            if competencia_alvo and len((competencia_alvo or "").strip()) >= 7:
                ref_date = datetime.strptime(competencia_alvo, "%m/%Y")
            else:
                ref_date = datetime.now()
        except Exception:
            ref_date = datetime.now()

        fim_mes_referencia = self._fim_do_mes(ref_date)

        resultados = []
        cnpj_esperado_limpo = re.sub(r"\D", "", cnpj_esperado or "")
        tipos_encontrados = set()

        for caminho in caminhos_pdf or []:
            texto = extrair_texto_pdf_inteligente(caminho) or ""
            texto_upper = texto.upper()

            tipo = self._normalizar_tipo(texto_upper)
            if tipo in self.TIPOS_ESPERADOS:
                tipos_encontrados.add(tipo)

            cnpj_encontrado = self._extrair_cnpj(texto)
            cnpj_encontrado_limpo = re.sub(r"\D", "", cnpj_encontrado) if cnpj_encontrado else ""
            cnpj_ok = True if not cnpj_esperado_limpo else cnpj_encontrado_limpo == cnpj_esperado_limpo

            razao_social = self._extrair_razao_social(texto, tipo)
            data_validade = self._extrair_validade(texto, tipo)

            vigente = False
            if data_validade:
                try:
                    dt_val = datetime.strptime(data_validade, "%d/%m/%Y")
                    vigente = dt_val >= fim_mes_referencia
                except ValueError:
                    vigente = False

            status_ok = cnpj_ok and vigente and tipo in self.TIPOS_ESPERADOS
            motivo = []
            if tipo == "Desconhecido":
                motivo.append("Tipo de certidao nao identificado")
            if not cnpj_ok:
                motivo.append("CNPJ divergente")
            if not vigente:
                motivo.append("Certidao fora da vigencia para a competencia")

            resultados.append(
                {
                    "item": tipo,
                    "razao_social": razao_social,
                    "cnpj": cnpj_encontrado or "Nao encontrado",
                    "validade": data_validade or "Nao encontrada",
                    "competencia_conferencia": ref_date.strftime("%m/%Y"),
                    "status": "OK" if status_ok else "Pendente",
                    "motivo": "; ".join(motivo),
                }
            )

        faltantes = sorted(list(self.TIPOS_ESPERADOS - tipos_encontrados))
        if faltantes:
            resultados.append(
                {
                    "item": "Documentos obrigatorios",
                    "razao_social": "-",
                    "cnpj": "-",
                    "validade": "-",
                    "competencia_conferencia": ref_date.strftime("%m/%Y"),
                    "status": "Pendente",
                    "motivo": f"Faltando: {', '.join(faltantes)}",
                }
            )

        qtd_ok = sum(
            1 for r in resultados if r.get("item") in self.TIPOS_ESPERADOS and r.get("status") == "OK"
        )

        return {
            "status": "Aprovado" if qtd_ok == 3 and not faltantes else "Reprovado",
            "mensagem": f"{qtd_ok}/3 certidao(oes) validas para a competencia {ref_date.strftime('%m/%Y')}",
            "validacoes": resultados,
        }
