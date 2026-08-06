import shutil, random
from pathlib import Path
from collections import defaultdict, Counter

SRC = Path("AI/data/dataset")
DST = Path("AI/data/sample_dataset")
TARGET = {"train": 80, "val": 20}
SEED = 42
CLASS_NAMES = ["Can", "Pet bottle", "Styrofoam"]
NUM_CLASSES = len(CLASS_NAMES)
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def sample_stratified(split):
    label_dir = SRC / "labels" / split
    label_files = list(label_dir.glob("*.txt"))
    random.shuffle(label_files)

    selected = set()
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

        # 선택된 이미지가 특정 클래스를 충족하는지 확인
        # 아직 target에 못 미친 클래스가 있으면 포함
        needed = [c for c in classes if class_count[c] < target_per_class]
        if needed:
            selected.add(stem)
            for c in classes:
                class_count[c] += 1

        # 모든 클래스가 target에 도달하면 중단
        if all(class_count[c] >= target_per_class for c in range(NUM_CLASSES)):
            break

    # 결과 로깅
    for cid in range(NUM_CLASSES):
        actual = class_count[cid]
        print(f"  {CLASS_NAMES[cid]}: {actual}/{target_per_class} 장")
    print(f"  total unique images: {len(selected)}")

    return selected


def copy_files(stems, split):
    img_dir = SRC / "images" / split
    lbl_dir = SRC / "labels" / split
    img_out = DST / "images" / split
    lbl_out = DST / "labels" / split
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    for stem in stems:
        for ext in IMG_EXTS:
            src = img_dir / f"{stem}{ext}"
            if src.exists():
                shutil.copy2(src, img_out / src.name)
                break
        src = lbl_dir / f"{stem}.txt"
        if src.exists():
            shutil.copy2(src, lbl_out / src.name)


def main():
    random.seed(SEED)

    for split in ["train", "val"]:
        print(f"\n=== {split} (클래스당 {TARGET[split]}장) ===")
        stems = sample_stratified(split)
        copy_files(stems, split)
        print(f"  → {len(stems)} 개 파일 복사 완료")

    src_yaml = SRC / "data.yaml"
    if src_yaml.exists():
        shutil.copy2(src_yaml, DST / "data.yaml")
    print("\n샘플 데이터셋 생성 완료!")


if __name__ == "__main__":
    main()
