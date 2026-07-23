# generate_hnm_dataset.py
# Hard Negative Mining 데이터셋 생성 스크립트
# val 검증 결과(FP/FN)를 기반으로 학습용 데이터셋을 클래스별로 구축

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import csv
import cv2
import torch
import shutil
from pathlib import Path
from ultralytics import YOLO

# 클래스 정의
CLASS_NAMES = ["Can", "Pet bottle", "Styrofoam"]

# TP/FP 판별 기준
IOU_THRESHOLD = 0.5          # IoU 기준: 이 값 이상이면 TP로 판별
CONF_THRESHOLD_DEFAULT = 0.5  # 신뢰도 기준: 이 값 이상만 예측으로 간주

# 경로 설정
DATASET_IMAGES = Path("AI/data/dataset/images/val")   # 원본 val 이미지
DATASET_LABELS = Path("AI/data/dataset/labels/val")    # 원본 val 라벨
OUTPUT_DIR = Path("AI/data/hnm_dataset")               # 출력 데이터셋
MODEL_PATH = Path("runs/detect/runs/train_full/yolo11n/weights/best.pt")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate Hard Negative Mining dataset from val errors")
    parser.add_argument("--model", type=str, default=MODEL_PATH,
                        help="학습된 모델 경로 (pt 파일)")
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD_DEFAULT,
                        help="신뢰도 임계값")
    parser.add_argument("--iou", type=float, default=IOU_THRESHOLD,
                        help="TP 판별용 IoU 임계값")
    return parser.parse_args()


def load_ground_truth(label_path):
    # YOLO TXT 라벨 파일에서 ground truth bbox를 로드
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


def xyxy_to_xywh(x1, y1, x2, y2, img_w, img_h):
    # xyxy 포맷을 YOLO 포맷(x_center, y_center, w, h)으로 변환 (정규화 포함)
    x_center = ((x1 + x2) / 2) / img_w
    y_center = ((y1 + y2) / 2) / img_h
    w = (x2 - x1) / img_w
    h = (y2 - y1) / img_h
    return x_center, y_center, w, h


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
    - TP: 모델이 옳게 탐지 (IoU >= iou_thresh)
    - FP: 모델이 잘못 탐지 (오탐지)
    - FN: 모델이 놓친 실제 객체 (미탐지)
    """
    matched_gt = set()
    tp_list = []
    fp_list = []

    # 신뢰도가 높은 예측부터 매칭 (Greedy 방식)
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

        # IoU 기준을 충족하면 TP, 아니면 FP
        if best_iou >= iou_thresh and best_gt_idx >= 0:
            matched_gt.add(best_gt_idx)
            tp_list.append(pred)
        else:
            fp_list.append(pred)

    # 매칭되지 않은 GT는 FN (미탐지)
    fn_list = [gt for idx, gt in enumerate(gt_boxes) if idx not in matched_gt]

    return tp_list, fp_list, fn_list


def main():
    args = parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print(f"Loading model: {args.model}")

    # 모델 로드
    model = YOLO(args.model)

    # 출력 디렉토리 생성 (클래스별 / FP, FN 구분)
    for cls_name in CLASS_NAMES:
        for error_type in ["FP", "FN"]:
            (OUTPUT_DIR / "images" / cls_name / error_type).mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / "labels" / cls_name / error_type).mkdir(parents=True, exist_ok=True)

    # val 이미지 파일 목록 수집
    image_files = sorted(DATASET_IMAGES.glob("*.jpg")) + sorted(DATASET_IMAGES.glob("*.png"))
    print(f"Total val images: {len(image_files)}")

    # 클래스별 통계
    stats = {cls: {"FP": 0, "FN": 0} for cls in CLASS_NAMES}
    total_counter = 0

    # 각 이미지에 대해 추론 후 FP/FN 판별
    for img_path in image_files:
        total_counter += 1
        stem = img_path.stem
        label_path = DATASET_LABELS / f"{stem}.txt"

        # Ground truth 로드
        gt_boxes = load_ground_truth(label_path)

        # 이미지 로드
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        img_h, img_w = img.shape[:2]

        # GT bbox를 xyxy 포맷으로 변환
        for gt in gt_boxes:
            gt["xyxy"] = xywh_to_xyxy(gt["x_center"], gt["y_center"], gt["w"], gt["h"], img_w, img_h)

        # YOLO 추론 실행
        results = model.predict(source=img, conf=args.conf, iou=args.iou, imgsz=640, device=device, verbose=False)

        # 예측 결과를 pred_boxes로 변환
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

        # TP, FP, FN 판별
        tp_list, fp_list, fn_list = match_predictions_to_gt(pred_boxes, gt_boxes, args.iou)

        # FP(오탐지) 이미지/라벨 저장
        # - FP: 원본 GT 라벨 + 모델이 틀리게 예측한 bbox를 라벨로 저장
        if fp_list:
            # FP 이미지의 클래스는 첫 번째 FP 예측 기준으로 결정
            cls_name = CLASS_NAMES[fp_list[0]["class_id"]]
            img_out = OUTPUT_DIR / "images" / cls_name / "FP" / f"{stem}.jpg"
            lbl_out = OUTPUT_DIR / "labels" / cls_name / "FP" / f"{stem}.txt"
            cv2.imwrite(str(img_out), img)

            with open(lbl_out, "w") as f:
                # 1) 원본 GT 라벨 저장
                for gt in gt_boxes:
                    f.write(f"{gt['class_id']} {gt['x_center']:.6f} {gt['y_center']:.6f} {gt['w']:.6f} {gt['h']:.6f}\n")
                # 2) 모델이 틀리게 예측한 bbox 저장
                for det in fp_list:
                    x1, y1, x2, y2 = det["xyxy"]
                    xc, yc, w, h = xyxy_to_xywh(x1, y1, x2, y2, img_w, img_h)
                    f.write(f"{det['class_id']} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
            stats[cls_name]["FP"] += 1

        # FN(미탐지) 이미지/라벨 저장
        # - FN: 원본 ground truth bbox를 라벨로 저장 (모델이 놓친 객체)
        for gt in fn_list:
            cls_name = CLASS_NAMES[gt["class_id"]]

            img_out = OUTPUT_DIR / "images" / cls_name / "FN" / f"{stem}.jpg"
            lbl_out = OUTPUT_DIR / "labels" / cls_name / "FN" / f"{stem}.txt"
            cv2.imwrite(str(img_out), img)
            with open(lbl_out, "w") as f:
                f.write(f"{gt['class_id']} {gt['x_center']:.6f} {gt['y_center']:.6f} {gt['w']:.6f} {gt['h']:.6f}\n")
            stats[cls_name]["FN"] += 1

        # 진행 상황 출력 (200장마다)
        if total_counter % 200 == 0:
            print(f"  processed {total_counter}/{len(image_files)}")

    # data.yaml 생성
    data_yaml = f"""path: AI/data/hnm_dataset
train: images
nc: 3
names:
  0: Can
  1: Pet bottle
  2: Styrofoam
"""
    with open(OUTPUT_DIR / "data.yaml", "w") as f:
        f.write(data_yaml)

    # 최종 통계 출력
    print("\n=== HNM Dataset Summary ===")
    print(f"{'Class':<15} {'FP':<8} {'FN':<8} {'Total':<8}")
    print("-" * 40)
    total_fp = 0
    total_fn = 0
    for cls_name in CLASS_NAMES:
        fp = stats[cls_name]["FP"]
        fn = stats[cls_name]["FN"]
        total_fp += fp
        total_fn += fn
        print(f"{cls_name:<15} {fp:<8} {fn:<8} {fp+fn:<8}")
    print("-" * 40)
    print(f"{'Total':<15} {total_fp:<8} {total_fn:<8} {total_fp+total_fn:<8}")
    print(f"\nOutput: {OUTPUT_DIR}")
    print(f"data.yaml: {OUTPUT_DIR / 'data.yaml'}")


if __name__ == "__main__":
    main()
