import cv2
from pathlib import Path

MAX_SIZE = 640
MAX_FILE_MB = 1.0

# 데이터 용량 축소 및 사이즈 조정
for split in ["train", "val"]:
    img_dir = Path(f"AI/data/dataset/images/{split}")
    for p in sorted(img_dir.glob("*.jpg")):
        file_mb = p.stat().st_size / (1024 * 1024)
        img = cv2.imread(str(p))
        if img is None:
            print(f"FAILED {split}/{p.name}")
            continue

        h, w = img.shape[:2]
        if max(w, h) > MAX_SIZE or file_mb > MAX_FILE_MB:
            scale = MAX_SIZE / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            print(f"Resized {split}/{p.name} ({w}x{h}, {file_mb:.1f}MB -> {new_w}x{new_h})")

        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 85])

