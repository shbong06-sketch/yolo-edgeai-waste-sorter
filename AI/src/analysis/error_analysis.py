import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import csv
import cv2
import torch
import numpy as np
from pathlib import Path
from ultralytics import YOLO
from collections import defaultdict

CLASS_NAMES = ["Can", "Pet bottle", "Styrofoam"]
IOU_THRESHOLD = 0.5
CONF_THRESHOLD_DEFAULT = 0.5

DATASET_IMAGES = Path("AI/data/dataset/images/val")
DATASET_LABELS = Path("AI/data/dataset/labels/val")
OUTPUT_DIR = Path("AI/docs/images/error_analysis")


def parse_args():
    parser = argparse.ArgumentParser(description="YOLO Error Analysis on Validation Set")
    parser.add_argument("--model", type=str, default="runs/detect/runs/train_full/yolo11n/weights/best.pt",
                        help="trained model path (pt file)")
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD_DEFAULT,
                        help="confidence threshold")
    parser.add_argument("--iou", type=float, default=IOU_THRESHOLD,
                        help="IoU threshold for TP matching")
    parser.add_argument("--max-samples", type=int, default=10,
                        help="max number of sample images to save per error type")
    return parser.parse_args()


def load_ground_truth(label_path):
    # YOLO TXT 라벨 파일에서 ground truth를 수집
    boxes = []
    if not label_path.exists():
        return boxes
    with open(label_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                cls_id = int(parts[0])
                x_center = float(parts[1])
                y_center = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])
                boxes.append({
                    "class_id": cls_id,
                    "x_center": x_center,
                    "y_center": y_center,
                    "w": w,
                    "h": h,
                })
    return boxes


def xywh_to_xyxy(x_center, y_center, w, h, img_w, img_h):
    # YOLO 포맷(x_center, y_center, w, h)을 xyxy 포맷으로 변환
    x1 = int((x_center - w / 2) * img_w)
    y1 = int((y_center - h / 2) * img_h)
    x2 = int((x_center + w / 2) * img_w)
    y2 = int((y_center + h / 2) * img_h)
    return x1, y1, x2, y2


def compute_iou(box_a, box_b):
    # 두 바운딩 박스 간 IoU를 계산 (xyxy 포맷)
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def match_predictions_to_gt(pred_boxes, gt_boxes, iou_thresh):
    """
    예측 박스와 ground truth 박스를 매칭하여 TP, FP, FN을 판별
    - pred_boxes: [{"class_id", "confidence", "xyxy": (x1,y1,x2,y2)}, ...]
    - gt_boxes: [{"class_id", "xyxy": (x1,y1,x2,y2)}, ...]
    """
    matched_gt = set()
    tp_list = []
    fp_list = []

    sorted_preds = sorted(pred_boxes, key=lambda x: x["confidence"], reverse=True)

    for pred in sorted_preds:
        best_iou = 0.0
        best_gt_idx = -1
        for idx, gt in enumerate(gt_boxes):
            if idx in matched_gt:
                continue
            if pred["class_id"] != gt["class_id"]:
                continue
            iou = compute_iou(pred["xyxy"], gt["xyxy"])
            if iou > best_iou:
                best_iou = iou
                best_gt_idx = idx

        if best_iou >= iou_thresh and best_gt_idx >= 0:
            matched_gt.add(best_gt_idx)
            tp_list.append(pred)
        else:
            fp_list.append(pred)

    fn_list = [gt for idx, gt in enumerate(gt_boxes) if idx not in matched_gt]

    return tp_list, fp_list, fn_list


def create_montage(image_list, output_path, cols=5, cell_size=(320, 320), border=2):
    """
    이미지 리스트를 격자 형태로 만들어 하나의 큰 이미지로 생성
    - image_list: 저장된 이미지 경로 리스트
    - output_path: 출력 파일 경로
    - cols: 열 개수
    - cell_size: 각 셀 크기 (width, height)
    - border: 이미지 간 간격 (px)
    """
    if not image_list:
        return

    cell_w, cell_h = cell_size
    rows = (len(image_list) + cols - 1) // cols
    total_w = cols * cell_w + (cols + 1) * border
    total_h = rows * cell_h + (rows + 1) * border
    canvas = np.ones((total_h, total_w, 3), dtype=np.uint8) * 40

    for idx, img_path in enumerate(image_list):
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        img = cv2.resize(img, (cell_w, cell_h))
        r = idx // cols
        c = idx % cols
        y = border + r * (cell_h + border)
        x = border + c * (cell_w + border)
        canvas[y:y + cell_h, x:x + cell_w] = img

    cv2.imwrite(str(output_path), canvas)


def draw_boxes(img, detections, color, label_prefix=""):
    # 이미지에 바운딩 박스를 그리기
    for det in detections:
        x1, y1, x2, y2 = det["xyxy"]
        cls_id = det["class_id"]
        conf = det.get("confidence", 0.0)

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"{label_prefix}{CLASS_NAMES[cls_id]} {conf:.2f}" if conf > 0 else f"{label_prefix}{CLASS_NAMES[cls_id]}"
        cv2.putText(img, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return img


def main():
    args = parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print(f"Loading model: {args.model}")

    model = YOLO(args.model)

    image_files = sorted(DATASET_IMAGES.glob("*.jpg")) + sorted(DATASET_IMAGES.glob("*.png"))
    print(f"Total val images: {len(image_files)}")

    all_errors = []
    stats = {
        "total_images": 0,
        "total_gt": 0,
        "total_pred": 0,
        "total_tp": 0,
        "total_fp": 0,
        "total_fn": 0,
        "per_class": {name: {"tp": 0, "fp": 0, "fn": 0} for name in CLASS_NAMES},
        "conf_tp": [],
        "conf_fp": [],
    }

    (OUTPUT_DIR / "fp_samples").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "fn_samples").mkdir(parents=True, exist_ok=True)

    fp_samples = []
    fn_samples = []

    for img_path in image_files:
        stats["total_images"] += 1
        stem = img_path.stem
        label_path = DATASET_LABELS / f"{stem}.txt"

        gt_boxes = load_ground_truth(label_path)
        for gt in gt_boxes:
            gt["xyxy"] = (0, 0, 0, 0)

        img = cv2.imread(str(img_path))
        if img is None:
            continue
        img_h, img_w = img.shape[:2]

        for gt in gt_boxes:
            gt["xyxy"] = xywh_to_xyxy(gt["x_center"], gt["y_center"], gt["w"], gt["h"], img_w, img_h)

        results = model.predict(source=img, conf=args.conf, iou=args.iou, imgsz=640, device=device, verbose=False)

        pred_boxes = []
        r = results[0]
        if r.boxes is not None:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                pred_boxes.append({
                    "class_id": cls_id,
                    "confidence": conf,
                    "xyxy": (x1, y1, x2, y2),
                })

        tp_list, fp_list, fn_list = match_predictions_to_gt(pred_boxes, gt_boxes, args.iou)

        stats["total_gt"] += len(gt_boxes)
        stats["total_pred"] += len(pred_boxes)
        stats["total_tp"] += len(tp_list)
        stats["total_fp"] += len(fp_list)
        stats["total_fn"] += len(fn_list)

        for det in tp_list:
            cname = CLASS_NAMES[det["class_id"]]
            stats["per_class"][cname]["tp"] += 1
            stats["conf_tp"].append(det["confidence"])
        for det in fp_list:
            cname = CLASS_NAMES[det["class_id"]]
            stats["per_class"][cname]["fp"] += 1
            stats["conf_fp"].append(det["confidence"])
        for gt in fn_list:
            cname = CLASS_NAMES[gt["class_id"]]
            stats["per_class"][cname]["fn"] += 1

        if fp_list and len(fp_samples) < args.max_samples:
            img_copy = img.copy()
            draw_boxes(img_copy, fp_list, (0, 0, 255), label_prefix="FP: ")
            draw_boxes(img_copy, tp_list, (0, 255, 0), label_prefix="TP: ")
            fp_path = OUTPUT_DIR / "fp_samples" / f"{stem}_fp.jpg"
            cv2.imwrite(str(fp_path), img_copy)
            fp_samples.append({
                "image": stem,
                "fp_count": len(fp_list),
                "fp_classes": ",".join(CLASS_NAMES[d["class_id"]] for d in fp_list),
                "fn_count": len(fn_list),
            })

        if fn_list and len(fn_samples) < args.max_samples:
            img_copy = img.copy()
            draw_boxes(img_copy, fn_list, (255, 0, 0), label_prefix="FN: ")
            draw_boxes(img_copy, tp_list, (0, 255, 0), label_prefix="TP: ")
            fn_path = OUTPUT_DIR / "fn_samples" / f"{stem}_fn.jpg"
            cv2.imwrite(str(fn_path), img_copy)
            fn_samples.append({
                "image": stem,
                "fn_count": len(fn_list),
                "fn_classes": ",".join(CLASS_NAMES[g["class_id"]] for g in fn_list),
                "fp_count": len(fp_list),
            })

        if stats["total_images"] % 200 == 0:
            print(f"  processed {stats['total_images']}/{len(image_files)}")

    csv_path = OUTPUT_DIR / "error_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "error_type", "count", "classes"])
        for s in fp_samples:
            writer.writerow([s["image"], "FP", s["fp_count"], s["fp_classes"]])
        for s in fn_samples:
            writer.writerow([s["image"], "FN", s["fn_count"], s["fn_classes"]])

    print("\n=== Error Analysis Summary ===")
    print(f"Total images: {stats['total_images']}")
    print(f"Total GT: {stats['total_gt']}")
    print(f"Total Predictions: {stats['total_pred']}")
    print(f"TP: {stats['total_tp']}")
    print(f"FP: {stats['total_fp']}")
    print(f"FN: {stats['total_fn']}")
    print()
    print(f"{'Class':<15} {'TP':<8} {'FP':<8} {'FN':<8}")
    print("-" * 40)
    for cname in CLASS_NAMES:
        c = stats["per_class"][cname]
        print(f"{cname:<15} {c['tp']:<8} {c['fp']:<8} {c['fn']:<8}")
    print()
    if stats["conf_tp"]:
        print(f"Avg confidence (TP): {sum(stats['conf_tp'])/len(stats['conf_tp']):.4f}")
    if stats["conf_fp"]:
        print(f"Avg confidence (FP): {sum(stats['conf_fp'])/len(stats['conf_fp']):.4f}")
    print(f"\nFP samples saved: {len(fp_samples)} images -> {OUTPUT_DIR / 'fp_samples/'}")
    print(f"FN samples saved: {len(fn_samples)} images -> {OUTPUT_DIR / 'fn_samples/'}")
    print(f"CSV saved: {csv_path}")

    fp_image_paths = sorted((OUTPUT_DIR / "fp_samples").glob("*.jpg"))
    fn_image_paths = sorted((OUTPUT_DIR / "fn_samples").glob("*.jpg"))

    if fp_image_paths:
        fp_montage_path = OUTPUT_DIR / "fp_montage.jpg"
        create_montage(fp_image_paths, fp_montage_path, cols=5, cell_size=(320, 320))
        print(f"FP montage saved: {fp_montage_path}")

    if fn_image_paths:
        fn_montage_path = OUTPUT_DIR / "fn_montage.jpg"
        create_montage(fn_image_paths, fn_montage_path, cols=5, cell_size=(320, 320))
        print(f"FN montage saved: {fn_montage_path}")


if __name__ == "__main__":
    main()
