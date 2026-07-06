import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import torch
from ultralytics import YOLO
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DATA_YAML = "AI/data/sample_dataset/data.yaml"
EPOCHS = 50
BATCH = 16
IMG_SIZE = 640
PATIENCE = 15
PROJECT = "runs/train"

MODELS = ["yolov8n.pt", "yolov10n.pt", "yolo11n.pt"]

METRICS = {
    "metrics/mAP50(B)": "mAP50",
    "metrics/mAP50-95(B)": "mAP50-95",
    "metrics/precision(B)": "Precision",
    "metrics/recall(B)": "Recall",
    "train/box_loss": "Box Loss",
}


def train_models():
    results = {}
    for model_name in MODELS:
        name = model_name.replace(".pt", "")
        print(f"\n=== Training {name} ===")
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
        results[name] = model.val()
        print(f"{name} mAP50-95: {results[name].box.map:.4f}")
        print(f"{name} mAP50: {results[name].box.map50:.4f}")

    print("\n=== Model Comparison ===")
    print(f"{'Model':<15} {'mAP50-95':<10} {'mAP50':<10}")
    print("-" * 35)
    for name, r in results.items():
        print(f"{name:<15} {r.box.map:<10.4f} {r.box.map50:<10.4f}")

    return results


def plot_comparison():
    # 각 모델의 results.csv 읽기
    run_dirs = [Path(PROJECT) / m.replace(".pt", "") for m in MODELS]
    dfs = {}
    for d in run_dirs:
        csv_path = d / "results.csv"
        if csv_path.exists():
            dfs[d.name] = pd.read_csv(csv_path)

    if not dfs:
        print("results.csv not found. Skip plotting.")
        return

    n_metrics = len(METRICS)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes = axes.flatten()

    # 메트릭별 비교 그래프
    for idx, (col, label) in enumerate(METRICS.items()):
        ax = axes[idx]
        for name, df in dfs.items():
            if col in df.columns:
                ax.plot(df["epoch"], df[col], label=name)
        ax.set_title(label)
        ax.set_xlabel("Epoch")
        ax.legend()
        ax.grid(True)

    for i in range(n_metrics, len(axes)):
        axes[i].axis("off")

    plt.tight_layout()
    out_path = Path(PROJECT) / "comparison.png"
    plt.savefig(out_path, dpi=150)
    print(f"\nComparison chart saved: {out_path}")
    plt.show()


def main():
    train_models()
    plot_comparison()


if __name__ == "__main__":
    main()
