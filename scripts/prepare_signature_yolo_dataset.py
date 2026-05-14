import argparse
import random
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_IMAGES = ROOT / "datasets" / "assinaturas_cvat" / "images"
SOURCE_LABELS = ROOT / "datasets" / "assinaturas_yolo" / "labels"
DATASET_DIR = ROOT / "datasets" / "assinaturas_yolo"
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def has_label(image_path):
    return (SOURCE_LABELS / f"{image_path.stem}.txt").exists()


def clear_split_dirs():
    for folder in [
        DATASET_DIR / "images" / "train",
        DATASET_DIR / "images" / "val",
        DATASET_DIR / "labels" / "train",
        DATASET_DIR / "labels" / "val",
    ]:
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)


def copy_pair(image_path, split):
    image_dest = DATASET_DIR / "images" / split / image_path.name
    label_src = SOURCE_LABELS / f"{image_path.stem}.txt"
    label_dest = DATASET_DIR / "labels" / split / label_src.name
    shutil.copy2(image_path, image_dest)
    shutil.copy2(label_src, label_dest)


def write_data_yaml():
    data_yaml = DATASET_DIR / "data.yaml"
    normalized_path = str(DATASET_DIR).replace("\\", "/")
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {normalized_path}",
                "train: images/train",
                "val: images/val",
                "",
                "names:",
                "  0: assinatura",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return data_yaml


def main():
    parser = argparse.ArgumentParser(description="Prepara dataset YOLO train/val para assinaturas.")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    images = [
        path
        for path in sorted(SOURCE_IMAGES.iterdir())
        if path.suffix.lower() in IMAGE_EXTS and has_label(path)
    ]

    if not images:
        raise SystemExit(
            "Nenhuma imagem anotada encontrada. Salve anotacoes primeiro no servidor YOLO."
        )

    random.Random(args.seed).shuffle(images)

    if len(images) == 1:
        train_images = images
        val_images = images
    else:
        val_count = max(1, int(round(len(images) * args.val_ratio)))
        val_images = images[:val_count]
        train_images = images[val_count:]
        if not train_images:
            train_images = val_images

    clear_split_dirs()
    for image in train_images:
        copy_pair(image, "train")
    for image in val_images:
        copy_pair(image, "val")

    data_yaml = write_data_yaml()

    print(f"Dataset preparado: {DATASET_DIR}")
    print(f"Train: {len(train_images)} imagem(ns)")
    print(f"Val: {len(val_images)} imagem(ns)")
    print(f"YAML: {data_yaml}")


if __name__ == "__main__":
    main()
