import argparse
import os
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Treina YOLO para detectar assinaturas.")
    parser.add_argument("--data", default="datasets/assinaturas_yolo/data.yaml")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--name", default="assinatura_yolo")
    parser.add_argument("--deploy", default="models/assinatura_yolo.pt")
    parser.add_argument("--skip-prepare", action="store_true")
    parser.add_argument("--only-images", nargs="*", default=[])
    args = parser.parse_args()

    if not args.skip_prepare:
        subprocess.run(
            [sys.executable, "scripts/prepare_signature_yolo_dataset.py", *( ["--only-images", *args.only_images] if args.only_images else [] )],
            check=True,
        )

    try:
        from ultralytics import YOLO
    except ModuleNotFoundError:
        raise SystemExit(
            "Ultralytics nao esta instalado. Rode: python -m pip install -r requirements-yolo.txt"
        )
    except OSError as exc:
        raise SystemExit(
            "PyTorch nao conseguiu carregar as DLLs no Windows.\n"
            "Instale/aceite o Microsoft Visual C++ Redistributable x64 e tente novamente:\n"
            "winget install --id Microsoft.VCRedist.2015+.x64 --source winget\n"
            f"Detalhe original: {exc}"
        )

    model = YOLO(args.model)
    result = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project="runs/detect",
        name=args.name,
    )

    best = os.path.join(result.save_dir, "weights", "best.pt")
    if os.path.exists(best):
        os.makedirs(os.path.dirname(args.deploy), exist_ok=True)
        shutil.copy2(best, args.deploy)
        print(f"Modelo copiado para {os.path.abspath(args.deploy)}")
    else:
        print(f"Treino finalizado, mas best.pt nao foi encontrado em {best}")


if __name__ == "__main__":
    main()

