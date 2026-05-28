import os
import shutil
import pytesseract

"""
Configuração centralizada do Tesseract.
Projeto CLOUD-FIRST (Linux).
Windows fica apenas como fallback para debug local.
"""

def _primeiro_existente(caminhos):
    for caminho in caminhos:
        if caminho and os.path.exists(caminho):
            return caminho
    return None


if os.name == "nt":  # Windows (apenas debug local)
    local_appdata = os.getenv("LOCALAPPDATA")
    tesseract_cmd = _primeiro_existente([
        os.getenv("TESSERACT_CMD"),
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(local_appdata, "Programs", "Tesseract-OCR", "tesseract.exe") if local_appdata else None,
        r"C:\Users\Notebook\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
        r"C:\Users\notebook\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ])

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
else:  # Linux / Cloud (Cloud Shell, Cloud Run, VM, Docker)
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
