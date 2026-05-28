from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.ocr import extrair_texto_pdf_inteligente
from utils.yolo_signature_detection import detectar_assinaturas_yolo, yolo_disponivel
from validators.rescisao.gfd_logic import extrair_dados_gfd
from validators.rescisao.trct_logic import extrair_dados_trct


class RescisaoValidator:
    def analisar(self, caminho_pdf, nome_esperado):
        texto_completo = extrair_texto_pdf_inteligente(caminho_pdf) or ""
        texto_upper = texto_completo.upper()
        auth_digital = detectar_autenticacao_digital(texto_completo)
        yolo_modelo_ok = yolo_disponivel()
        yolo_deteccoes = detectar_assinaturas_yolo(caminho_pdf) if yolo_modelo_ok else []
        assinatura_yolo_ok = len(yolo_deteccoes) > 0

        dados_trct = extrair_dados_trct(texto_completo)
        dados_gfd = extrair_dados_gfd(texto_completo)

        nome_ok = True
        if nome_esperado:
            nome_ok = nome_esperado.upper() in texto_upper

        termo_ok = any(x in texto_upper for x in ["TRCT", "TERMO DE RESCISAO", "TERMO DE RESCISÃO"])
        ponto_ok = any(x in texto_upper for x in ["PONTO", "CARTAO", "CARTÃO", "MARCACAO", "MARCAÇÃO"])
        pedido_demissao_doc_ok = any(
            x in texto_upper
            for x in [
                "PEDIDO DE DEMISSAO",
                "PEDIDO DE DEMISSÃO",
                "CARTA DE DEMISSAO",
                "CARTA DE DEMISSÃO",
                "DEMISSAO A PEDIDO",
                "DEMISSÃO A PEDIDO",
            ]
        )
        assinatura_manual_ok = any(
            x in texto_upper
            for x in [
                "ASSINATURA",
                "DECLARO TER RECEBIDO",
                "DECLARO ESTAR CIENTE",
            ]
        )
        pedido_demissao_assinado_ok = pedido_demissao_doc_ok and (assinatura_manual_ok or assinatura_yolo_ok)

        aviso_previo_ok = any(
            x in texto_upper
            for x in [
                "AVISO PREVIO",
                "AVISO PRÉVIO",
                "COMUNICACAO DE TERMINO DE CONTRATO",
                "COMUNICAÇÃO DE TÉRMINO DE CONTRATO",
                "COMUNICADO",
            ]
        )

        valor_liquido = dados_trct.get("valor_liquido")
        valor_trct_formatado = dados_trct.get("valor_formatado")

        if valor_liquido is None:
            comprovante_trct_ok = False
        elif valor_liquido == 0:
            comprovante_trct_ok = True
        else:
            comprovante_trct_ok = bool(valor_trct_formatado) and texto_completo.count(valor_trct_formatado) >= 2

        fgts_rescisorio_base_ok = (("FGTS" in texto_upper or "GUIA" in texto_upper) and any(x in texto_upper for x in ["RESCISORIO", "RESCISÓRIO"]))
        fgts_rescisorio_doc_ok = fgts_rescisorio_base_ok and "GUIA" in texto_upper

        gfd_ok = False
        if dados_gfd.get("valor_formatado"):
            gfd_ok = texto_completo.count(dados_gfd["valor_formatado"]) >= 2
        fgts_rescisorio_comprovante_ok = gfd_ok

        tipo_desligamento = dados_trct.get("tipo_desligamento", "indefinido")
        causa_afastamento = dados_trct.get("causa_afastamento", "")

        validacoes = [
            {"item": f"Colaborador: {nome_esperado or 'Nao informado'}", "ok": nome_ok},
            {"item": "Termo de Rescisao (TRCT)", "ok": termo_ok},
            {"item": "Cartao de Ponto", "ok": ponto_ok},
            {"item": "FGTS Digital Rescisorio (anexo)", "ok": fgts_rescisorio_base_ok},
            {"item": f"Autenticacao digital ({auth_digital.get('provedor')})", "ok": auth_digital.get("assinatura_digital")},
            {"item": f"Assinatura visual (YOLO) detectada: {len(yolo_deteccoes)}", "ok": assinatura_yolo_ok},
            {"item": f"Tipo de desligamento identificado: {tipo_desligamento}", "ok": tipo_desligamento != "indefinido"},
        ]

        if tipo_desligamento == "pedido_demissao":
            validacoes.extend([
                {"item": "Pedido de demissao assinado a mao", "ok": pedido_demissao_assinado_ok},
                {"item": f"Valor liquido no termo ({valor_trct_formatado or '---'}) e comprovante quando valor > 0", "ok": comprovante_trct_ok},
            ])
            obrigatorios_ok = termo_ok and ponto_ok and pedido_demissao_assinado_ok and comprovante_trct_ok

        elif tipo_desligamento == "dispensa":
            validacoes.extend([
                {"item": "Aviso previo / comunicado da dispensa", "ok": aviso_previo_ok},
                {"item": f"Valor liquido no termo ({valor_trct_formatado or '---'}) com comprovante", "ok": comprovante_trct_ok},
                {"item": "FGTS Digital Rescisorio (guia)", "ok": fgts_rescisorio_doc_ok},
                {"item": f"FGTS Digital Rescisorio (comprovante, valor {dados_gfd.get('valor_formatado') or '---'})", "ok": fgts_rescisorio_comprovante_ok},
            ])
            obrigatorios_ok = termo_ok and ponto_ok and aviso_previo_ok and comprovante_trct_ok and fgts_rescisorio_doc_ok and fgts_rescisorio_comprovante_ok
        else:
            validacoes.append({"item": "Nao foi possivel classificar se e pedido de demissao ou dispensa no termo", "ok": False})
            obrigatorios_ok = False

        status = "Aprovado" if nome_ok and obrigatorios_ok else "Reprovado"

        return {
            "status": status,
            "mensagem": "Kit validado com sucesso" if status == "Aprovado" else "Existem pendencias no Kit",
            "tipo_desligamento": tipo_desligamento,
            "causa_afastamento": causa_afastamento,
            "autenticacao_digital": auth_digital,
            "assinatura_yolo": {
                "modelo_disponivel": yolo_modelo_ok,
                "detectada": assinatura_yolo_ok,
                "deteccoes_totais": len(yolo_deteccoes),
            },
            "validacoes": validacoes,
        }
