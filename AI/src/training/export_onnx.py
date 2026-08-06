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

import ctypes
import sys
import sysconfig

# onnxruntime-gpu CUDA 라이브러리를 미리 로드
# CUDAExecutionProvider에 필요한 모든 라이브러리를 pip 패키지에서 찾아 로드
# 가상환경(.venv, conda) 또는 시스템 전체 설치 모두 호환
_cuda_libs = [
    "libcudart.so.13", "libcublas.so.13", "libcublasLt.so.13",
    "libcurand.so.10", "libcufft.so.12", "libnvrtc.so.13",
    "libcudnn.so.9", "libcudnn_ops.so.9", "libcudnn_cnn.so.9",
    "libcudnn_adv.so.9", "libcudnn_graph.so.9", "libcudnn_heuristic.so.9",
    "libcudnn_engines_precompiled.so.9", "libcudnn_engines_runtime_compiled.so.9",
]

# nvidia 패키지가 설치된 site-packages를 여러 경로에서 탐색
_candidates = []
for _key in ("purelib", "platlib"):
    _sp = sysconfig.get_path(_key)
    if _sp and _sp not in _candidates:
        _candidates.append(_sp)
_prefix_sp = os.path.join(
    sys.prefix, "lib",
    f"python{sys.version_info.major}.{sys.version_info.minor}",
    "site-packages",
)
if _prefix_sp not in _candidates:
    _candidates.append(_prefix_sp)
_base = os.path.dirname(os.path.abspath(__file__))
for _depth in range(10):
    _c = os.path.normpath(os.path.join(_base, *[".."] * _depth, "lib",
        f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))
    if _c not in _candidates:
        _candidates.append(_c)

_site_packages = None
for _sp in _candidates:
    if os.path.isdir(_sp) and os.path.isdir(os.path.join(_sp, "nvidia", "cu13", "lib")):
        _site_packages = _sp
        break

if _site_packages:
    _cuda_dirs = [
        os.path.join(_site_packages, "nvidia", "cu13", "lib"),
        os.path.join(_site_packages, "nvidia", "cudnn", "lib"),
    ]
    _ld_paths = []
    for _d in _cuda_dirs:
        if os.path.isdir(_d):
            _ld_paths.append(_d)
            for _lib in _cuda_libs:
                _p = os.path.join(_d, _lib)
                if os.path.isfile(_p):
                    ctypes.CDLL(_p)
    if _ld_paths:
        os.environ["LD_LIBRARY_PATH"] = ":".join(_ld_paths) + ":" + os.environ.get("LD_LIBRARY_PATH", "")

import time
import onnxruntime as ort
import numpy as np
from pathlib import Path
from onnxruntime.quantization import quantize_dynamic, QuantType


def detect_gpu() -> bool:
    # onnxruntime에서 CUDAExecutionProvider 사용 가능 여부 확인

    # Returns:
    # - True: GPU 사용 가능, False: CPU만 사용 가능
    
    available = ort.get_available_providers()
    has_gpu = "CUDAExecutionProvider" in available
    print(f"Available providers: {available}")
    print(f"GPU (CUDA): {'available' if has_gpu else 'not available'}")
    return has_gpu


# Config
MODEL_PATH = "ros2_ws/best.pt"  # 변환할 .pt 모델 경로
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


def benchmark_onnx(
    onnx_path: str,
    imgsz: int = 640,
    runs: int = 50,
    providers: list = None,
) -> dict:
    # ONNX 모델의 추론 성능 측정

    # Args:
    # - onnx_path: 벤치마크할 ONNX 모델 경로
    # - imgsz: 더미 입력 이미지 크기
    # - runs: 추론 반복 횟수
    # - providers: onnxruntime 실행 프로바이더 목록 (기본값: CPU)

    # Returns:
    # - {"avg_ms": 평균 추론 시간(ms), "size_mb": 모델 파일 크기(MB), "provider": 실제 사용된 프로바이더}
    
    if providers is None:
        providers = ["CPUExecutionProvider"]

    session = ort.InferenceSession(onnx_path, providers=providers)
    actual_provider = session.get_providers()[0]
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
    return {
        "avg_ms": round(avg_ms, 2),
        "size_mb": round(size_mb, 2),
        "provider": actual_provider,
    }


def compare(pt_path: str, original_onnx: str, quant_onnx: str, imgsz: int = 640, has_gpu: bool = False):
    # .pt / .onnx / 양자화 모델 성능 비교

    # Args:
    # - pt_path: 원본 .pt 모델 경로
    # - original_onnx: FP32 ONNX 모델 경로
    # - quant_onnx: INT8 양자화 ONNX 경로
    # - imgsz: 벤치마크 입력 이미지 크기
    # - has_gpu: GPU 사용 가능 여부

    cpu_providers = ["CPUExecutionProvider"]
    gpu_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    # PyTorch 벤치마크
    pt = benchmark_pt(pt_path, imgsz)

    # ONNX FP32 벤치마크 (CPU)
    onnx_cpu = benchmark_onnx(original_onnx, imgsz, providers=cpu_providers)

    # ONNX FP32 벤치마크 (GPU)
    onnx_gpu = None
    if has_gpu:
        try:
            onnx_gpu = benchmark_onnx(original_onnx, imgsz, providers=gpu_providers)
        except Exception as e:
            print(f"\n[SKIP] ONNX GPU benchmark failed: {e}")

    # INT8 양자화 모델 벤치마크 (CPU)
    quant_cpu = None
    try:
        quant_cpu = benchmark_onnx(quant_onnx, imgsz, providers=cpu_providers)
    except Exception as e:
        print(f"\n[SKIP] INT8 CPU benchmark failed: {e}")

    # INT8 양자화 모델 벤치마크 (GPU)
    quant_gpu = None
    if has_gpu:
        try:
            quant_gpu = benchmark_onnx(quant_onnx, imgsz, providers=gpu_providers)
        except Exception as e:
            print(f"\n[SKIP] INT8 GPU benchmark failed: {e}")

    # 결과 출력
    print("\n========== Benchmark ==========")
    if has_gpu:
        print(f"{'':20s} {'PyTorch':>12s} {'ONNX CPU':>12s} {'ONNX GPU':>12s} {'INT8 CPU':>12s} {'INT8 GPU':>12s}")
        print(f"{'Inference (ms)':20s}", end="")
        print(f" {pt['avg_ms']:>12.2f}", end="")
        print(f" {onnx_cpu['avg_ms']:>12.2f}", end="")
        print(f" {onnx_gpu['avg_ms'] if onnx_gpu else 0:>12.2f}", end="")
        print(f" {quant_cpu['avg_ms'] if quant_cpu else 0:>12.2f}", end="")
        print(f" {quant_gpu['avg_ms'] if quant_gpu else 0:>12.2f}")
        print(f"{'Size (MB)':20s}", end="")
        print(f" {pt['size_mb']:>12.2f}", end="")
        print(f" {onnx_cpu['size_mb']:>12.2f}", end="")
        print(f" {onnx_gpu['size_mb'] if onnx_gpu else 0:>12.2f}", end="")
        print(f" {quant_cpu['size_mb'] if quant_cpu else 0:>12.2f}", end="")
        print(f" {quant_gpu['size_mb'] if quant_gpu else 0:>12.2f}")
        print()
        # CPU speedup
        speedup_cpu = pt["avg_ms"] / onnx_cpu["avg_ms"] if onnx_cpu["avg_ms"] > 0 else 0
        print(f"{'ONNX Speedup (CPU)':20s} {speedup_cpu:>11.2f}x")
        # GPU speedup
        if onnx_gpu and onnx_gpu["avg_ms"] > 0:
            speedup_gpu = pt["avg_ms"] / onnx_gpu["avg_ms"]
            print(f"{'ONNX Speedup (GPU)':20s} {speedup_gpu:>11.2f}x")
        # INT8 vs FP32
        if quant_cpu and onnx_cpu["avg_ms"] > 0:
            int8_speedup_cpu = onnx_cpu["avg_ms"] / quant_cpu["avg_ms"]
            print(f"{'INT8 vs FP32 (CPU)':20s} {int8_speedup_cpu:>11.2f}x")
        if quant_gpu and onnx_gpu and onnx_gpu["avg_ms"] > 0:
            int8_speedup_gpu = onnx_gpu["avg_ms"] / quant_gpu["avg_ms"]
            print(f"{'INT8 vs FP32 (GPU)':20s} {int8_speedup_gpu:>11.2f}x")
    else:
        print(f"{'':20s} {'PyTorch (.pt)':>14s} {'ONNX':>14s} {'INT8 Quant':>14s}")
        print(f"{'Inference (ms)':20s} {pt['avg_ms']:>14.2f} {onnx_cpu['avg_ms']:>14.2f} {quant_cpu['avg_ms'] if quant_cpu else 0:>14.2f}")
        print(f"{'Size (MB)':20s} {pt['size_mb']:>14.2f} {onnx_cpu['size_mb']:>14.2f} {quant_cpu['size_mb'] if quant_cpu else 0:>14.2f}")
        speedup = pt["avg_ms"] / onnx_cpu["avg_ms"] if onnx_cpu["avg_ms"] > 0 else 0
        print(f"{'ONNX Speedup':20s} {speedup:>13.2f}x")

    print("================================\n")


def main():
    model_path = MODEL_PATH

    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        return

    print(f"Model: {model_path}")
    print(f"Image size: {IMG_SIZE}\n")

    # GPU 감지
    print("=== Environment ===")
    has_gpu = detect_gpu()
    print()

    # Step 1: .pt → .onnx 변환
    print("=== Step 1: ONNX Export ===")
    onnx_path = export_onnx(model_path, IMG_SIZE)

    # Step 2: FP32 → INT8 동적 양자화
    print("\n=== Step 2: INT8 Dynamic Quantization ===")
    quant_path = quantize_onnx(onnx_path)

    # Step 3: .pt vs .onnx vs 양자화 모델 벤치마크 비교
    print("\n=== Step 3: Benchmark ===")
    compare(model_path, onnx_path, quant_path, IMG_SIZE, has_gpu=has_gpu)

    print("Done.")


if __name__ == "__main__":
    main()
