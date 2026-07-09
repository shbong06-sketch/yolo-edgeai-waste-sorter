import shutil, random, csv
from pathlib import Path
from collections import Counter

SRC = Path("AI/data/full_dataset")
DST = Path("AI/data/dataset")
TARGET = {"train": 2400, "val": 600}
SEED = 42
CLASS_NAMES = ["Can", "Pet bottle", "Styrofoam"]
NUM_CLASSES = len(CLASS_NAMES)
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def sample_stratified(split):
    label_dir = SRC / "labels" / split
    label_files = list(label_dir.glob("*.txt"))
    random.shuffle(label_files)

    selected = {}
    class_count = Counter()
    target_per_class = TARGET[split]

    for label_path in label_files:
        stem = label_path.stem
        if stem in selected:
            continue

        with open(label_path) as f:
            classes = set()
            for line in f:
                line = line.strip()
                if line:
                    cid = int(line.split()[0])
                    if cid < NUM_CLASSES:
                        classes.add(cid)

        needed = [c for c in classes if class_count[c] < target_per_class]
        if needed:
            selected[stem] = classes
            for c in classes:
                class_count[c] += 1

        if all(class_count[c] >= target_per_class for c in range(NUM_CLASSES)):
            break

    for cid in range(NUM_CLASSES):
        print(f"  {CLASS_NAMES[cid]}: {class_count[cid]}/{target_per_class} 장")
    print(f"  total unique images: {len(selected)}")

    return selected


def copy_files(stems_dict, split):
    img_dir = SRC / "images" / split
    lbl_dir = SRC / "labels" / split
    img_out = DST / "images" / split
    lbl_out = DST / "labels" / split
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    metadata = []
    counter = 0

    for stem, classes in stems_dict.items():
        counter += 1
        new_name = f"dataset_{counter:06d}"

        # 이미지 복사 (이름 변경)
        src_img = None
        for ext in IMG_EXTS:
            candidate = img_dir / f"{stem}{ext}"
            if candidate.exists():
                src_img = candidate
                break
        if src_img is None:
            continue

        dst_img = img_out / f"{new_name}{src_img.suffix}"
        shutil.copy2(src_img, dst_img)

        # 라벨 복사 (이름 변경)
        src_lbl = lbl_dir / f"{stem}.txt"
        dst_lbl = lbl_out / f"{new_name}.txt"
        if src_lbl.exists():
            shutil.copy2(src_lbl, dst_lbl)

        # 메타데이터 기록
        metadata.append({
            "new_file": dst_img.name,
            "original_file": src_img.name,
            "classes": ",".join(str(c) for c in sorted(classes)),
            "class_names": ",".join(CLASS_NAMES[c] for c in sorted(classes)),
            "split": split,
            "source": "영상추출",
        })

    # CSV 저장
    csv_path = DST / "dataset_metadata.csv"
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["new_file", "original_file", "classes", "class_names", "split", "source"])
        if write_header:
            writer.writeheader()
        writer.writerows(metadata)


def main():
    random.seed(SEED)

    for split in ["train", "val"]:
        print(f"\n=== {split} (클래스당 {TARGET[split]}장) ===")
        stems_dict = sample_stratified(split)
        copy_files(stems_dict, split)
        print(f"  → {len(stems_dict)} 개 파일 복사 완료")

    src_yaml = SRC / "data.yaml"
    if src_yaml.exists():
        shutil.copy2(src_yaml, DST / "data.yaml")
    print("\n데이터셋 구축 완료!")
    print("메타데이터: dataset_metadata.csv")


if __name__ == "__main__":
    main()
