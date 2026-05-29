import argparse
import random
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_IMAGES = ROOT / "datasets" / "assinaturas_cvat" / "images"
SOURCE_LABELS = ROOT / "datasets" / "assinaturas_yolo" / "labels"
DATASET_DIR = ROOT / "datasets" / "assinaturas_yolo"
CLASS_FILE = DATASET_DIR / "classes.txt"
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
DEFAULT_CLASSES = [
    "assinatura",
    "rubrica",
    "campo_assinatura",
    "campo_assinatura_vazio",
    "carimbo",
    "assinatura_digital_visual",
]


def get_classes():
    CLASS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CLASS_FILE.exists():
        CLASS_FILE.write_text("\n".join(DEFAULT_CLASSES) + "\n", encoding="utf-8")
    classes = [ln.strip() for ln in CLASS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return classes or DEFAULT_CLASSES


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
    # Ultralytics caches label/image mapping in these files. If stale, it can
    # reference files from an old split and crash with FileNotFoundError.
    for cache_file in [DATASET_DIR / "labels" / "train.cache", DATASET_DIR / "labels" / "val.cache"]:
        if cache_file.exists():
            cache_file.unlink()


def copy_pair(image_path, split):
    image_dest = DATASET_DIR / "images" / split / image_path.name
    label_src = SOURCE_LABELS / f"{image_path.stem}.txt"
    label_dest = DATASET_DIR / "labels" / split / label_src.name
    shutil.copy2(image_path, image_dest)
    shutil.copy2(label_src, label_dest)


def validar_label(path, num_classes):
    erros = []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            erros.append(f"{path.name}:{ln} formato invalido")
            continue
        try:
            cls = int(float(parts[0]))
            xc, yc, w, h = [float(x) for x in parts[1:]]
        except Exception:
            erros.append(f"{path.name}:{ln} valores nao numericos")
            continue

        if cls < 0 or cls >= num_classes:
            erros.append(f"{path.name}:{ln} class_id invalido ({cls})")
        for vname, v in [("x_center", xc), ("y_center", yc), ("width", w), ("height", h)]:
            if v < 0 or v > 1:
                erros.append(f"{path.name}:{ln} {vname} fora de 0..1 ({v})")

    return erros


def write_data_yaml(classes):
    data_yaml = DATASET_DIR / "data.yaml"
    normalized_path = str(DATASET_DIR).replace("\\", "/")
    names_lines = [f"  {idx}: {name}" for idx, name in enumerate(classes)]
    data_yaml.write_text(
        "\n".join([
            f"path: {normalized_path}",
            "train: images/train",
            "val: images/val",
            "",
            "names:",
            *names_lines,
            "",
        ]),
        encoding="utf-8",
    )
    return data_yaml


def main():
    parser = argparse.ArgumentParser(description="Prepara dataset YOLO train/val para assinaturas.")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--only-images", nargs="*", default=[])
    args = parser.parse_args()

    classes = get_classes()
    images_all = [p for p in sorted(SOURCE_IMAGES.iterdir()) if p.suffix.lower() in IMAGE_EXTS]
    if args.only_images:
        filtro = {Path(x).name for x in args.only_images}
        images_all = [p for p in images_all if p.name in filtro]
    labels_all = list(sorted(SOURCE_LABELS.glob("*.txt")))

    imagens_sem_label = [img.name for img in images_all if not has_label(img)]
    labels_sem_imagem = [lb.name for lb in labels_all if not (SOURCE_IMAGES / f"{lb.stem}.jpg").exists() and not (SOURCE_IMAGES / f"{lb.stem}.jpeg").exists() and not (SOURCE_IMAGES / f"{lb.stem}.png").exists()]

    erros_labels = []
    for lb in labels_all:
        erros_labels.extend(validar_label(lb, len(classes)))

    images = [img for img in images_all if has_label(img)]
    if not images:
        raise SystemExit("Nenhuma imagem anotada encontrada. Salve anotacoes primeiro no servidor YOLO.")

    random.Random(args.seed).shuffle(images)

    if len(images) == 1:
        train_images = images
        val_images = images
    else:
        val_count = max(1, int(round(len(images) * args.val_ratio)))
        val_images = images[:val_count]
        train_images = images[val_count:] or val_images

    clear_split_dirs()
    for image in train_images:
        copy_pair(image, "train")
    for image in val_images:
        copy_pair(image, "val")

    data_yaml = write_data_yaml(classes)

    print("=== RESUMO DATASET YOLO ===")
    print(f"Classes ({len(classes)}): {classes}")
    print(f"Imagens totais: {len(images_all)}")
    print(f"Imagens com label: {len(images)}")
    print(f"Imagens sem label: {len(imagens_sem_label)}")
    print(f"Labels sem imagem: {len(labels_sem_imagem)}")
    print(f"Erros de label: {len(erros_labels)}")

    if imagens_sem_label:
        print("- imagens sem label:", imagens_sem_label[:20])
    if labels_sem_imagem:
        print("- labels sem imagem:", labels_sem_imagem[:20])
    if erros_labels:
        print("- primeiros erros de label:")
        for err in erros_labels[:30]:
            print("  ", err)

    print(f"Dataset preparado: {DATASET_DIR}")
    print(f"Train: {len(train_images)} imagem(ns)")
    print(f"Val: {len(val_images)} imagem(ns)")
    print(f"YAML: {data_yaml}")


if __name__ == "__main__":
    main()

