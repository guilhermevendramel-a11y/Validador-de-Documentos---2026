import subprocess
import sys
from pathlib import Path

import fitz
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename


ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "datasets" / "assinaturas_cvat" / "images"
LABEL_DIR = ROOT / "datasets" / "assinaturas_yolo" / "labels"
CLASS_FILE = ROOT / "datasets" / "assinaturas_yolo" / "classes.txt"

app = Flask(__name__)


def ensure_dirs():
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    CLASS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CLASS_FILE.exists():
        CLASS_FILE.write_text("assinatura\n", encoding="utf-8")


def safe_stem(name):
    stem = Path(name).stem
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in stem)
    return stem.strip("_") or "documento"


def label_path(image_name):
    return LABEL_DIR / f"{Path(image_name).stem}.txt"


def save_pdf_pages(file_storage, dpi=180):
    ensure_dirs()
    original = secure_filename(file_storage.filename)
    temp_pdf = IMAGE_DIR / f"_upload_{original}"
    file_storage.save(temp_pdf)

    created = []
    with fitz.open(temp_pdf) as doc:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        prefix = safe_stem(original)
        for index, page in enumerate(doc, start=1):
            out = IMAGE_DIR / f"{prefix}_pagina_{index:03d}.jpg"
            page.get_pixmap(matrix=matrix, alpha=False).save(out)
            created.append(out.name)

    temp_pdf.unlink(missing_ok=True)
    return created


def save_image(file_storage):
    ensure_dirs()
    original = secure_filename(file_storage.filename)
    out = IMAGE_DIR / original
    file_storage.save(out)
    return [out.name]


def list_images():
    ensure_dirs()
    return [
        file.name
        for file in sorted(IMAGE_DIR.iterdir())
        if file.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]


@app.get("/")
def index():
    return """
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>YOLO Assinaturas</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f3f4f6; color: #111827; }
    header { background: #8b0000; color: #fff; padding: 12px 18px; font-weight: 700; }
    main { max-width: 1280px; margin: 16px auto 40px; padding: 0 16px; display: grid; gap: 12px; }
    section { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; }
    h2 { color: #8b0000; font-size: 17px; margin: 0 0 10px; }
    input, button { min-height: 34px; }
    input[type=file] { border: 1px solid #d1d5db; border-radius: 4px; padding: 6px; flex: 1; min-width: 280px; }
    button { background: #8b0000; color: #fff; border: 0; border-radius: 4px; font-weight: 700; padding: 7px 12px; cursor: pointer; }
    button.secondary { background: #374151; }
    code { background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 4px; padding: 2px 5px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .status { background: #ecfdf5; border: 1px solid #bbf7d0; color: #14532d; border-radius: 4px; padding: 8px; display: none; }
    .small { color: #4b5563; font-size: 13px; }
    .layout { display: grid; grid-template-columns: 260px 1fr; gap: 12px; align-items: start; }
    .gallery { display: grid; gap: 8px; max-height: 74vh; overflow: auto; }
    .thumb { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden; cursor: pointer; }
    .thumb.active { border-color: #8b0000; box-shadow: 0 0 0 2px rgba(139, 0, 0, .15); }
    .thumb img { display: block; width: 100%; height: 130px; object-fit: contain; background: #f9fafb; }
    .thumb span { display: block; font-size: 11px; padding: 5px; overflow-wrap: anywhere; }
    .canvas-wrap { max-height: 74vh; overflow: auto; border: 1px solid #d1d5db; background: #e5e7eb; padding: 10px; }
    canvas { display: block; background: #fff; max-width: 100%; height: auto; cursor: crosshair; }
    .boxes { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }
    .tag { background: #fee2e2; border: 1px solid #fecaca; border-radius: 4px; color: #7f1d1d; padding: 4px 6px; font-size: 12px; }
    @media (max-width: 860px) { .layout { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>YOLO - Anotador de Assinaturas/Rubricas</header>
  <main>
    <section>
      <h2>1. Enviar PDF ou imagens</h2>
      <div class="row">
        <input id="files" type="file" multiple accept=".pdf,.jpg,.jpeg,.png" />
        <button id="uploadBtn">Enviar e converter</button>
      </div>
      <p class="small">PDFs viram imagens JPG. Imagens JPG/PNG entram direto no dataset.</p>
      <div id="status" class="status"></div>
    </section>

    <section>
      <h2>2. Anotar no navegador</h2>
      <p class="small">Clique numa imagem, arraste sobre a rubrica/assinatura e salve. A classe e sempre <code>assinatura</code>.</p>
      <div class="row">
        <button id="undoBtn" class="secondary">Desfazer caixa</button>
        <button id="clearBtn" class="secondary">Limpar imagem</button>
        <button id="saveLabelBtn">Salvar anotacao YOLO</button>
        <span id="selectedName" class="small">Nenhuma imagem selecionada.</span>
      </div>
      <div id="boxes" class="boxes"></div>
      <div class="layout">
        <div id="gallery" class="gallery"></div>
        <div class="canvas-wrap"><canvas id="annotatorCanvas"></canvas></div>
      </div>
    </section>

    <section>
      <h2>3. Treinar YOLO</h2>
      <p class="small">Depois de anotar imagens suficientes, rode:</p>
      <p><code>python scripts\\train_signature_yolo.py --data datasets\\assinaturas_yolo\\data.yaml --epochs 80 --imgsz 960</code></p>
      <button id="trainBtn" class="secondary">Iniciar treino pelo servidor</button>
      <p class="small">Modelo final esperado: <code>models\\assinatura_yolo.pt</code></p>
    </section>
  </main>

  <script>
    const statusEl = document.getElementById("status");
    const canvas = document.getElementById("annotatorCanvas");
    const ctx = canvas.getContext("2d");
    const selectedNameEl = document.getElementById("selectedName");
    const boxesEl = document.getElementById("boxes");
    let selectedImage = "";
    let imageObj = null;
    let boxes = [];
    let drawing = false;
    let start = null;

    function showStatus(text) {
      statusEl.style.display = "block";
      statusEl.textContent = text;
    }

    function canvasPoint(event) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left) * (canvas.width / rect.width),
        y: (event.clientY - rect.top) * (canvas.height / rect.height),
      };
    }

    function normalizeBox(box) {
      const x = Math.min(box.x, box.x + box.w);
      const y = Math.min(box.y, box.y + box.h);
      return { x, y, w: Math.abs(box.w), h: Math.abs(box.h) };
    }

    function renderBoxes() {
      boxesEl.innerHTML = boxes.map((box, index) => {
        const b = normalizeBox(box);
        return `<span class="tag">assinatura ${index + 1}: ${Math.round(b.w)}x${Math.round(b.h)}</span>`;
      }).join("");
    }

    function drawCanvas(previewBox = null) {
      if (!imageObj) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(imageObj, 0, 0);
      ctx.lineWidth = Math.max(2, canvas.width / 700);
      ctx.strokeStyle = "#dc2626";
      ctx.fillStyle = "rgba(220, 38, 38, .12)";
      [...boxes, ...(previewBox ? [previewBox] : [])].forEach((box) => {
        const b = normalizeBox(box);
        ctx.fillRect(b.x, b.y, b.w, b.h);
        ctx.strokeRect(b.x, b.y, b.w, b.h);
      });
      renderBoxes();
    }

    async function selectImage(name) {
      selectedImage = name;
      boxes = [];
      selectedNameEl.textContent = name;
      imageObj = new Image();
      imageObj.onload = async () => {
        canvas.width = imageObj.naturalWidth;
        canvas.height = imageObj.naturalHeight;
        drawCanvas();
        const response = await fetch(`/api/labels/${encodeURIComponent(name)}`);
        const data = await response.json();
        boxes = (data.boxes || []).map((box) => ({
          x: (box.x_center - box.width / 2) * canvas.width,
          y: (box.y_center - box.height / 2) * canvas.height,
          w: box.width * canvas.width,
          h: box.height * canvas.height,
        }));
        drawCanvas();
      };
      imageObj.src = `/images/${encodeURIComponent(name)}`;
      document.querySelectorAll(".thumb").forEach((el) => {
        el.classList.toggle("active", el.dataset.name === name);
      });
    }

    async function loadImages() {
      const response = await fetch("/api/images");
      const data = await response.json();
      const gallery = document.getElementById("gallery");
      gallery.innerHTML = "";
      data.images.forEach((name) => {
        const div = document.createElement("div");
        div.className = "thumb";
        div.dataset.name = name;
        div.innerHTML = `<img src="/images/${encodeURIComponent(name)}" alt=""><span>${name}</span>`;
        div.addEventListener("click", () => selectImage(name));
        gallery.appendChild(div);
      });
      if (!selectedImage && data.images.length) selectImage(data.images[0]);
    }

    document.getElementById("uploadBtn").addEventListener("click", async () => {
      const input = document.getElementById("files");
      if (!input.files.length) return showStatus("Selecione ao menos um arquivo.");
      const form = new FormData();
      [...input.files].forEach((file) => form.append("files", file));
      showStatus("Enviando e convertendo...");
      const response = await fetch("/api/upload", { method: "POST", body: form });
      const data = await response.json();
      showStatus(data.message);
      selectedImage = "";
      await loadImages();
    });

    canvas.addEventListener("mousedown", (event) => {
      if (!imageObj) return;
      drawing = true;
      start = canvasPoint(event);
    });
    canvas.addEventListener("mousemove", (event) => {
      if (!drawing || !start) return;
      const point = canvasPoint(event);
      drawCanvas({ x: start.x, y: start.y, w: point.x - start.x, h: point.y - start.y });
    });
    canvas.addEventListener("mouseup", (event) => {
      if (!drawing || !start) return;
      const point = canvasPoint(event);
      const box = normalizeBox({ x: start.x, y: start.y, w: point.x - start.x, h: point.y - start.y });
      drawing = false;
      start = null;
      if (box.w >= 5 && box.h >= 5) boxes.push(box);
      drawCanvas();
    });

    document.getElementById("undoBtn").addEventListener("click", () => {
      boxes.pop();
      drawCanvas();
    });
    document.getElementById("clearBtn").addEventListener("click", () => {
      boxes = [];
      drawCanvas();
    });
    document.getElementById("saveLabelBtn").addEventListener("click", async () => {
      if (!selectedImage) return showStatus("Selecione uma imagem.");
      const yoloBoxes = boxes.map((box) => {
        const b = normalizeBox(box);
        return {
          class_id: 0,
          x_center: (b.x + b.w / 2) / canvas.width,
          y_center: (b.y + b.h / 2) / canvas.height,
          width: b.w / canvas.width,
          height: b.h / canvas.height,
        };
      });
      const response = await fetch(`/api/labels/${encodeURIComponent(selectedImage)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ boxes: yoloBoxes }),
      });
      const data = await response.json();
      showStatus(data.message);
    });
    document.getElementById("trainBtn").addEventListener("click", async () => {
      const response = await fetch("/api/train", { method: "POST" });
      const data = await response.json();
      showStatus(data.message);
    });

    loadImages();
  </script>
</body>
</html>
"""


@app.get("/images/<path:filename>")
def image(filename):
    return send_from_directory(IMAGE_DIR, filename)


@app.get("/api/images")
def api_images():
    return jsonify({"images": list_images()})


@app.get("/api/labels/<path:filename>")
def api_get_label(filename):
    path = label_path(filename)
    boxes = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 5:
                boxes.append({
                    "class_id": int(float(parts[0])),
                    "x_center": float(parts[1]),
                    "y_center": float(parts[2]),
                    "width": float(parts[3]),
                    "height": float(parts[4]),
                })
    return jsonify({"boxes": boxes})


@app.post("/api/labels/<path:filename>")
def api_save_label(filename):
    ensure_dirs()
    boxes = request.json.get("boxes", []) if request.is_json else []
    lines = []
    for box in boxes:
        lines.append(
            f"{int(box.get('class_id', 0))} "
            f"{float(box.get('x_center', 0)):.6f} "
            f"{float(box.get('y_center', 0)):.6f} "
            f"{float(box.get('width', 0)):.6f} "
            f"{float(box.get('height', 0)):.6f}"
        )
    label_path(filename).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return jsonify({"message": f"Anotacao salva: {len(lines)} assinatura(s)."})


@app.post("/api/upload")
def api_upload():
    files = request.files.getlist("files")
    created = []
    for item in files:
        ext = Path(item.filename).suffix.lower()
        if ext == ".pdf":
            created.extend(save_pdf_pages(item))
        elif ext in {".jpg", ".jpeg", ".png"}:
            created.extend(save_image(item))
    return jsonify({"message": f"{len(created)} imagem(ns) pronta(s) para anotacao.", "created": created})


@app.post("/api/train")
def api_train():
    try:
        import torch  # noqa: F401
        import ultralytics  # noqa: F401
    except ModuleNotFoundError:
        return jsonify({
            "message": "Ultralytics nao esta instalado. Rode: python -m pip install -r requirements-yolo.txt"
        }), 500
    except OSError as exc:
        return jsonify({
            "message": (
                "PyTorch nao carregou no Windows. Instale/aceite o Microsoft Visual C++ "
                "Redistributable x64 e tente novamente. "
                f"Detalhe: {exc}"
            )
        }), 500

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "train_signature_yolo.py"),
        "--data",
        str(ROOT / "datasets" / "assinaturas_yolo" / "data.yaml"),
        "--epochs",
        "80",
        "--imgsz",
        "960",
    ]
    subprocess.Popen(cmd, cwd=ROOT)
    return jsonify({"message": "Treino iniciado em segundo plano. Aguarde models/assinatura_yolo.pt."})


if __name__ == "__main__":
    ensure_dirs()
    app.run(host="127.0.0.1", port=8010, debug=False)
