"""
YOLO 모델 ONNX 변환 및 INT8 양자화 스크립트

실행:
    python AI/src/training/export_onnx.py

출력:
    - 원본 ONNX 모델 (.onnx)  ← .pt와 같은 디렉토리에 생성
    - INT8 양자화 모델 (_int8.onnx)
    - 벤치마크 결과 (추론 속도, 파일 크기 비교)
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import time
import onnxruntime as ort
import numpy as np
from pathlib import Path
from onnxruntime.quantization import quantize_dynamic, QuantType

# Config
MODEL_PATH = "runs/detect/runs/exp01/hnm_training/weights/best.pt"  # 변환할 .pt 모델 경로
IMG_SIZE = 640       # 입력 이미지 크기 (정사각형)
BENCHMARK_RUNS = 50  # 벤치마크 반복 횟수


def export_onnx(model_path: str, imgsz: int = 640) -> str:
    # YOLO .pt 모델을 ONNX 포맷으로 변환
    # .pt와 같은 디렉토리에 .onnx 파일을 저장

    # Args:
    # - model_path: 학습된 .pt 모델 경로
    # - imgsz: 추론 시 입력 이미지 크기

    # Returns:
    # - 변환된 .onnx 파일 경로
    
    from ultralytics import YOLO

    model = YOLO(model_path)

    # ultralytics export: .pt와 같은 디렉토리에 .onnx 저장 (exporter.py:907)
    model.export(
        format="onnx",
        imgsz=imgsz,
        simplify=True,   # onnxslim으로 불필요한 노드 제거
        opset=17,        # 최신 ONNX 연산자 지원
    )

    # 저장 경로: .pt 파일과 동일한 디렉토리, 확장자만 .onnx
    onnx_path = Path(model_path).with_suffix(".onnx")

    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX export failed: {onnx_path} not found")

    print(f"ONNX export complete: {onnx_path}")
    return str(onnx_path)


def quantize_onnx(onnx_path: str) -> str:
    # ONNX 모델에 동적 INT8 양자화 적용
    # - 동적 양자화: 추론 시 activations을 실시간으로 양자화 (학습 데이터 불필요)
    # - INT8 가중치: 모델 크기 약 75% 감소, CPU 추론 속도 향상

    # Args:
    # - onnx_path: 원본 ONNX 모델 경로

    # Returns:
    # - 양자화된 _int8.onnx 파일 경로
    
    onnx_path = Path(onnx_path)
    # best.onnx → best_int8.onnx
    quant_path = onnx_path.with_name(onnx_path.stem + "_int8" + onnx_path.suffix)

    quantize_dynamic(
        model_input=str(onnx_path),
        model_output=str(quant_path),
        weight_type=QuantType.QInt8,
    )

    print(f"Quantized model saved: {quant_path}")
    return str(quant_path)


def benchmark_pt(model_path: str, imgsz: int = 640, runs: int = 50) -> dict:
    # PyTorch .pt 모델의 추론 성능 측정 (ultralytics YOLO 사용)

    # Args:
    # - model_path: .pt 모델 경로
    # - imgsz: 입력 이미지 크기
    # - runs: 추론 반복 횟수

    # Returns:
    # - {"avg_ms": 평균 추론 시간(ms), "size_mb": 모델 파일 크기(MB)}
    
    from ultralytics import YOLO

    model = YOLO(model_path)
    # 더미 입력 이미지 생성 (ultralytics는 numpy 배열을 받음)
    dummy = np.random.randint(0, 255, (imgsz, imgsz, 3), dtype=np.uint8)

    # 워밍업
    for _ in range(5):
        model.predict(source=dummy, verbose=False)

    # 벤치마크 측정
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        model.predict(source=dummy, verbose=False)
        times.append(time.perf_counter() - start)

    avg_ms = np.mean(times) * 1000
    size_mb = Path(model_path).stat().st_size / (1024 * 1024)
    return {"avg_ms": round(avg_ms, 2), "size_mb": round(size_mb, 2)}


def benchmark_onnx(onnx_path: str, imgsz: int = 640, runs: int = 50) -> dict:
    # ONNX 모델의 추론 성능 측정

    # Args:
    # - onnx_path: 벤치마크할 ONNX 모델 경로
    # - imgsz: 더미 입력 이미지 크기
    # - runs: 추론 반복 횟수

    # Returns:
    # - {"avg_ms": 평균 추론 시간(ms), "size_mb": 모델 파일 크기(MB)}

    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    dummy = np.random.randn(1, 3, imgsz, imgsz).astype(np.float32)

    # 워밍업
    for _ in range(5):
        session.run(None, {input_name: dummy})

    # 벤치마크 측정
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        session.run(None, {input_name: dummy})
        times.append(time.perf_counter() - start)

    avg_ms = np.mean(times) * 1000
    size_mb = Path(onnx_path).stat().st_size / (1024 * 1024)
    return {"avg_ms": round(avg_ms, 2), "size_mb": round(size_mb, 2)}


def compare(pt_path: str, original_onnx: str, quant_onnx: str, imgsz: int = 640):
    # .pt / .onnx / 양자화 모델 성능 비교

    # Args:
    # - pt_path: 원본 .pt 모델 경로
    # - original_onnx: FP32 ONNX 모델 경로
    # - quant_onnx: INT8 양자화 ONNX 경로
    # - imgsz: 벤치마크 입력 이미지 크기
    
    pt = benchmark_pt(pt_path, imgsz)
    onnx = benchmark_onnx(original_onnx, imgsz)

    # 양자화 모델 로드 시도
    quant = None
    try:
        quant = benchmark_onnx(quant_onnx, imgsz)
    except Exception as e:
        print(f"\n[SKIP] Quantized model benchmark failed: {e}")
        print(f"  → onnxruntime CPU may not support INT8 ConvInteger.\n")

    # 결과 출력
    print("\n========== Benchmark ==========")
    if quant:
        print(f"{'':20s} {'PyTorch (.pt)':>14s} {'ONNX':>14s} {'INT8 Quant':>14s}")
        print(f"{'Inference (ms)':20s} {pt['avg_ms']:>14.2f} {onnx['avg_ms']:>14.2f} {quant['avg_ms']:>14.2f}")
        print(f"{'Size (MB)':20s} {pt['size_mb']:>14.2f} {onnx['size_mb']:>14.2f} {quant['size_mb']:>14.2f}")
    else:
        print(f"{'':20s} {'PyTorch (.pt)':>14s} {'ONNX':>14s}")
        print(f"{'Inference (ms)':20s} {pt['avg_ms']:>14.2f} {onnx['avg_ms']:>14.2f}")
        print(f"{'Size (MB)':20s} {pt['size_mb']:>14.2f} {onnx['size_mb']:>14.2f}")

    # .pt vs ONNX 속도 비교
    speedup = pt["avg_ms"] / onnx["avg_ms"] if onnx["avg_ms"] > 0 else 0
    print(f"{'ONNX Speedup':20s} {speedup:>13.2f}x")
    print("================================\n")


def main():
    model_path = MODEL_PATH

    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        return

    print(f"Model: {model_path}")
    print(f"Image size: {IMG_SIZE}\n")

    # Step 1: .pt → .onnx 변환
    print("=== Step 1: ONNX Export ===")
    onnx_path = export_onnx(model_path, IMG_SIZE)

    # Step 2: FP32 → INT8 동적 양자화
    print("\n=== Step 2: INT8 Dynamic Quantization ===")
    quant_path = quantize_onnx(onnx_path)

    # Step 3: .pt vs .onnx vs 양자화 모델 벤치마크 비교
    print("\n=== Step 3: Benchmark ===")
    compare(model_path, onnx_path, quant_path, IMG_SIZE)

    print("Done.")


if __name__ == "__main__":
    main()
