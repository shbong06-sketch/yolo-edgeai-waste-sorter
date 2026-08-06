import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import torch
from ultralytics import YOLO

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DATA_YAML = "AI/data/dataset/data.yaml"
EPOCHS = 100
BATCH = 64
IMG_SIZE = 640
PATIENCE = 20
PROJECT = "runs/train_full"

MODELS = ["yolov8n.pt", "yolo11n.pt"]


def main():
    for model_name in MODELS:
        name = model_name.replace(".pt", "")
        print(f"\n=== Training {name} on full dataset ===")
        model = YOLO(model_name)
        model.train(
            data=DATA_YAML,
            epochs=EPOCHS,
            batch=BATCH,
            imgsz=IMG_SIZE,
            device=DEVICE,
            patience=PATIENCE,
            workers=4,
            amp=False,
            project=PROJECT,
            name=name,
            exist_ok=True,
            pretrained=True,
            optimizer="AdamW",
            cos_lr=True,
            warmup_epochs=3,
        )
        metrics = model.val()
        print(f"{name} - mAP50-95: {metrics.box.map:.4f}, mAP50: {metrics.box.map50:.4f}")

    print("\n=== Full dataset training complete ===")


if __name__ == "__main__":
    main()
