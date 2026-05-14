# =========================
# CORE
# =========================
import os
import re
import uuid
import tempfile

# =========================
# FLASK
# =========================
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

# =========================
# OCR / IA
# =========================
from utils.ocr.ocr_inss import extrair_texto_inss
from utils.gemini.inss import extrair_inss_inteligente

# =========================
# VALIDATORS
# =========================
from validators.inss.validator import INSSValidator
from validators.fgts import FGTSValidator
from validators.vale_transporte.validator import VTValidator

# =========================
# SERVICES
# =========================
from services.cartao_ponto_service import processar_cartao_ponto
from services.holerite_service import processar_holerite_comprovante
from services.inss_service import processar_inss
from services.folha_service import processar_folha_pagamento

# =========================
# UTIL
# =========================
from rapidfuzz import fuzz

# =====================================
# CONFIGURAÇÃO FLASK
# =====================================
app = Flask(__name__, static_folder="static", template_folder="templates")

app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# =====================================
# FUNÇÕES AUXILIARES (INTEGRAIS)
# =====================================

def extrair_data_pagamento(texto):
    if not texto:
        return ""
    match = re.search(r"\d{2}/\d{2}/\d{4}", texto)
    return match.group(0) if match else ""


def extrair_valor_pagamento(texto):
    if not texto:
        return 0.0

    match = re.search(r"Valor:\s*R?\$?\s*([\d\.,]+)", texto)

    if match:
        valor = match.group(1)
        valor = valor.replace(".", "").replace(",", ".")
        return float(valor)

    return 0.0


def validar_prazo_pagamento(data):
    if not data:
        return "Fora"

    try:
        dia = int(data.split("/")[0])
        return "OK" if dia <= 5 else "Fora"
    except:
        return "Fora"


def salvar_arquivo_temporario(arquivo):
    temp_dir = tempfile.gettempdir()
    nome_seguro = secure_filename(arquivo.filename)
    caminho = os.path.join(temp_dir, nome_seguro)
    arquivo.save(caminho)
    return caminho


def normalizar_competencia(comp):
    if not comp:
        return ""

    comp = comp.lower().strip()

    meses = {
        "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
        "abril": "04", "maio": "05", "junho": "06", "julho": "07",
        "agosto": "08", "setembro": "09", "outubro": "10",
        "novembro": "11", "dezembro": "12"
    }

    if re.match(r"\d{2}/\d{4}", comp):
        return comp

    match = re.search(r"([a-zçãé]+)[/ ](\d{4})", comp)

    if match:
        mes = meses.get(match.group(1), "")
        ano = match.group(2)
        if mes:
            return f"{mes}/{ano}"

    return comp


def detectar_competencia_documento(texto):
    if not texto:
        return ""

    texto = texto.lower()

    # Busca padrão 00/0000
    match = re.search(r"\b(\d{2}/\d{4})\b", texto)
    if match:
        return match.group(1)

    # Busca mês por extenso
    match = re.search(
        r"(janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)[/ ](\d{4})",
        texto
    )

    if match:
        meses = {
            "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
            "abril": "04", "maio": "05", "junho": "06", "julho": "07",
            "agosto": "08", "setembro": "09", "outubro": "10",
            "novembro": "11", "dezembro": "12"
        }

        mes = meses.get(match.group(1), "")
        ano = match.group(2)

        if mes:
            return f"{mes}/{ano}"

    return ""

def formatar_resposta_universal(resultado):
    """
    Mantém o formato original do validator
    e garante apenas que trabalhadores exista
    """

    if not isinstance(resultado, dict):
        return {
            "status": "Erro",
            "mensagem": "Resultado inválido",
            "trabalhadores": [],
            "documentos": {}
        }

    # 🔥 GARANTIAS PARA O FRONT
    resultado.setdefault("status", "Erro")
    resultado.setdefault("mensagem", "")
    resultado.setdefault("empresa", "")
    resultado.setdefault("competencia", "")
    resultado.setdefault("valor", 0)
    resultado.setdefault("data_pagamento", "")
    resultado.setdefault("trabalhadores", [])
    resultado.setdefault("documentos", {})

    return resultado


# =====================================
# ROTAS
# =====================================

@app.route("/")
def index():
    return render_template("index.html")


# =========================
# CARTÃO DE PONTO
# =========================
import traceback

@app.route("/validar_cartao_ponto", methods=["POST"])
def validar_cartao_ponto():

    print("\n🚀 ===== NOVA REQUISIÇÃO CARTÃO PONTO =====")

    arquivo = request.files.get("file")

    if not arquivo:
        return jsonify({
            "status": "Erro",
            "mensagem": "Arquivo não enviado"
        }), 400

    competencia_esperada = request.form.get("competencia")

    print("📅 Competência recebida:", competencia_esperada)

    if competencia_esperada:
        competencia_esperada = competencia_esperada.strip()

    caminho = None  # 🔥 IMPORTANTE

    try:
        caminho = salvar_arquivo_temporario(arquivo)
        print("📁 Arquivo salvo em:", caminho)

    except Exception as e:
        print("❌ Erro ao salvar arquivo:")
        traceback.print_exc()

        return jsonify({
            "status": "Erro",
            "mensagem": "Erro ao salvar arquivo"
        }), 500

    try:

        resultado = processar_cartao_ponto(
            caminho,
            competencia_esperada=competencia_esperada
        )

        print("📊 RESULTADO SERVICE:")
        print(resultado)

        resposta = formatar_resposta_universal(resultado)

        return jsonify(resposta)

    except Exception as e:

        print("❌ ERRO NO PROCESSAMENTO:")
        traceback.print_exc()

        return jsonify({
            "status": "Erro",
            "mensagem": "Erro ao processar cartão ponto",
            "detalhe": str(e)
        }), 500

    finally:
        try:
            if caminho and os.path.exists(caminho):
                os.remove(caminho)
                print("🧹 Arquivo temporário removido")
        except Exception as e:
            print("⚠️ Erro ao remover arquivo:", e)
            
# =========================
# FGTS
# =========================
@app.route("/validar_fgts", methods=["POST"])
def validar_fgts():
    relatorio = request.files.get("relatorio_fgts")
    guia = request.files.get("guia_fgts")

    print("RELATORIO:", relatorio.filename if relatorio else None)
    print("GUIA:", guia.filename if guia else None)

    if not relatorio or not guia:
        return jsonify({"status": "Erro", "mensagem": "Arquivos insuficientes"}), 400

    c_rel = salvar_arquivo_temporario(relatorio)
    c_guia = salvar_arquivo_temporario(guia)

    try:
        validador = FGTSValidator()
        competencia = request.form.get("competencia")
        resultado = validador.analisar(c_rel, c_guia, competencia)
        return jsonify(formatar_resposta_universal(resultado))
    finally:
        for c in [c_rel, c_guia]:
            if os.path.exists(c):
                os.remove(c)


# =========================
# INSS (REVISADO 🚀)
# =========================
@app.route("/validar_inss", methods=["POST"])
def validar_inss():
    guia = request.files.get("guia_inss")
    dctf = request.files.get("dctfweb")
    competencia_esperada = request.form.get("competencia")

    if not guia or not dctf:
        return jsonify({"status": "Erro", "mensagem": "Arquivos insuficientes"}), 400

    if not guia.filename or not dctf.filename:
        return jsonify({"status": "Erro", "mensagem": "Arquivos inválidos"}), 400

    c_guia = salvar_arquivo_temporario(guia)
    c_dctf = salvar_arquivo_temporario(dctf)

    try:
        resultado = processar_inss(
            c_guia,
            c_dctf,
            competencia_esperada
        )

        return jsonify(formatar_resposta_universal(resultado))

    finally:
        for c in [c_guia, c_dctf]:
            if os.path.exists(c):
                os.remove(c)

# =========================
# FOLHA DE PAGAMENTO
# =========================
@app.route("/validar_folha_pagamento", methods=["POST"])
def validar_folha_pagamento():

    arquivo = request.files.get("file")
    competencia_esperada = request.form.get("competencia")

    if not arquivo:
        return jsonify({
            "status": "Erro",
            "mensagem": "Arquivo não enviado"
        }), 400

    caminho = salvar_arquivo_temporario(arquivo)

    try:
        resultado = processar_folha_pagamento(
            caminho,
            competencia_esperada
        )

        return jsonify(resultado)

    except Exception as e:
        print(f"❌ ERRO FOLHA: {e}")

        return jsonify({
            "status": "Erro",
            "mensagem": f"Erro ao processar folha: {str(e)}"
        }), 500

    finally:
        if os.path.exists(caminho):
            os.remove(caminho)                

# =========================
# HOLERITE
# =========================
import uuid
from services.holerite_service import processar_holerite_comprovante


@app.route("/validar_holerite", methods=["POST"])
def validar_holerite_route():

    holerite = request.files.get("holerite")
    comprovantes = request.files.getlist("comprovantes")
    competencia = request.form.get("competencia")

    if not holerite or not comprovantes:
        return jsonify({"status": "Erro", "mensagem": "Envie os arquivos"})

    path_h = f"/tmp/{uuid.uuid4()}_{holerite.filename}"
    holerite.save(path_h)

    paths = []

    for c in comprovantes:
        path = f"/tmp/{uuid.uuid4()}_{c.filename}"
        c.save(path)
        paths.append(path)

    resultado = processar_holerite_comprovante(path_h, paths, competencia)

    return jsonify(resultado)

# =========================
# MOCKS / ROTAS ADICIONAIS
# =========================
@app.route("/validar_cnd", methods=["POST"])
@app.route("/validar_va", methods=["POST"])
@app.route("/validar_seguro_vida", methods=["POST"])
def rota_mock_generica():
    # Retorna sucesso básico para funcionalidades ainda não implementadas
    return jsonify({"status": "Aprovado", "colaboradores": []})


@app.route("/validar_vt", methods=["POST"])
def validar_vt():
    arquivos = request.files.getlist("comprovantes")
    if not arquivos:
        arquivo_unico = request.files.get("file")
        if arquivo_unico:
            arquivos = [arquivo_unico]

    if not arquivos:
        return jsonify({"status": "Erro", "mensagem": "Envie ao menos um PDF de vale transporte"}), 400

    caminhos = []
    try:
        for arquivo in arquivos:
            if not arquivo or not arquivo.filename:
                continue
            caminhos.append(salvar_arquivo_temporario(arquivo))

        if not caminhos:
            return jsonify({"status": "Erro", "mensagem": "Nenhum arquivo válido enviado"}), 400

        resultado = VTValidator().analisar(caminhos)
        return jsonify(resultado)
    finally:
        for caminho in caminhos:
            if caminho and os.path.exists(caminho):
                os.remove(caminho)


# =====================================
# START
# =====================================
if __name__ == "__main__":
    # Host 0.0.0.0 é obrigatório para o Docker expor a porta corretamente
    app.run(host="0.0.0.0", port=8000, debug=True)
