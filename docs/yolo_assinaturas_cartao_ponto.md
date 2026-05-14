# YOLO para Assinaturas no Cartao Ponto

## 1. Instalar dependencias opcionais

```powershell
pip install -r requirements-yolo.txt
```

## 2. Converter PDFs em imagens para o CVAT

Use uma pasta com PDFs de cartao ponto:

```powershell
python scripts/export_cartao_ponto_pages.py --input "C:\caminho\cartoes_ponto" --output datasets/assinaturas_cvat/images
```

As imagens geradas ficam prontas para upload no CVAT.

## 3. Anotar no CVAT

Crie um projeto com uma label:

```text
assinatura
```

Marque com retangulo apenas a assinatura/rubrica real. Nao marque o texto impresso "Assinatura" se o campo estiver vazio.

Exporte em formato YOLO 1.1.

## 4. Preparar a pasta exportada

Depois de exportar do CVAT, organize assim:

```text
datasets/assinaturas_yolo/
  data.yaml
  images/
    train/
    val/
    test/
  labels/
    train/
    val/
    test/
```

O `data.yaml` ja existe no projeto e define a classe `assinatura`.

## 5. Treinar

```powershell
python scripts/train_signature_yolo.py --data datasets/assinaturas_yolo/data.yaml --epochs 80 --imgsz 960
```

Ao final, o script copia o melhor modelo para:

```text
models/assinatura_yolo.pt
```

## 6. Usar no sistema

Quando `models/assinatura_yolo.pt` existir, o validador de Cartao Ponto usa YOLO automaticamente. Se o modelo nao existir, ele continua usando a regra atual por OpenCV.

Tambem da para apontar outro arquivo:

```powershell
$env:YOLO_SIGNATURE_MODEL="C:\modelos\best.pt"
npm run dev
```
