import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import csv
from pathlib import Path

DATASET_LABELS = Path("AI/data/dataset/labels/val")
DATASET_IMAGES = Path("AI/data/dataset/images/val")

PET_BOTTLE_CLASS_ID = 1


def parse_args():
    parser = argparse.ArgumentParser(description="Count overlapping Pet bottle bounding boxes in val set")
    parser.add_argument("--iou", type=float, default=0.3,
                        help="IoU threshold to consider boxes as overlapping")
    return parser.parse_args()


def load_boxes(label_path):
    boxes = []
    if not label_path.exists():
        return boxes
    with open(label_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                cls_id = int(parts[0])
                if cls_id == PET_BOTTLE_CLASS_ID:
                    x_center = float(parts[1])
                    y_center = float(parts[2])
                    w = float(parts[3])
                    h = float(parts[4])
                    x1 = x_center - w / 2
                    y1 = y_center - h / 2
                    x2 = x_center + w / 2
                    y2 = y_center + h / 2
                    boxes.append((x1, y1, x2, y2))
    return boxes


def compute_iou(box_a, box_b):
    # gt와 pred의 IoU 계산
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def main():
    args = parse_args()

    label_files = sorted(DATASET_LABELS.glob("*.txt"))
    total_images = len(label_files)

    overlap_images = []
    total_pet_bottles = 0
    total_overlap_pairs = 0

    for label_path in label_files:
        stem = label_path.stem
        boxes = load_boxes(label_path)
        num_boxes = len(boxes)
        total_pet_bottles += num_boxes

        if num_boxes < 2:
            continue

        max_iou = 0.0
        overlap_count = 0
        for i in range(num_boxes):
            for j in range(i + 1, num_boxes):
                iou = compute_iou(boxes[i], boxes[j])
                if iou > max_iou:
                    max_iou = iou
                if iou >= args.iou:
                    overlap_count += 1

        if overlap_count > 0:
            total_overlap_pairs += overlap_count
            overlap_images.append({
                "image": stem,
                "pet_bottle_count": num_boxes,
                "overlap_pairs": overlap_count,
                "max_iou": round(max_iou, 4),
            })

    print(f"=== Pet Bottle Overlap Analysis (IoU >= {args.iou}) ===")
    print(f"Total val images: {total_images}")
    print(f"Total Pet bottle instances: {total_pet_bottles}")
    print(f"Images with overlapping Pet bottles: {len(overlap_images)}")
    print(f"Overlapping ratio: {len(overlap_images) / total_images * 100:.2f}%")
    print(f"Total overlapping pairs: {total_overlap_pairs}")

    if overlap_images:
        csv_path = DATASET_LABELS.parent.parent / "pet_bottle_overlap.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["image", "pet_bottle_count", "overlap_pairs", "max_iou"])
            writer.writeheader()
            writer.writerows(overlap_images)
        print(f"\nCSV saved: {csv_path}")

        print(f"\nTop 10 images with most overlaps:")
        sorted_images = sorted(overlap_images, key=lambda x: x["overlap_pairs"], reverse=True)[:10]
        for img in sorted_images:
            print(f"  {img['image']}: {img['pet_bottle_count']} bottles, {img['overlap_pairs']} pairs, max_iou={img['max_iou']}")


if __name__ == "__main__":
    main()
