import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import torch
from ultralytics import YOLO

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DATA_YAML = "AI/data/dataset/data.yaml"
MODEL_NAME = "yolov10n.pt"
EPOCHS = 100
BATCH = 16
IMG_SIZE = 640
PATIENCE = 20

def main():
    model = YOLO(MODEL_NAME)
    model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        batch=BATCH,
        imgsz=IMG_SIZE,
        device=DEVICE,
        patience=PATIENCE,
        workers=4,
        amp=False,
        project="runs/train",
        name="yolov10n_baseline",
        exist_ok=True,
        pretrained=True,
        optimizer="auto",
        cos_lr=True,
        warmup_epochs=3,
    )

if __name__ == "__main__":
    main()
