"""
YOLO 모델 ONNX 변환 및 INT8 양자화 스크립트

사용법:
    python export_onnx.py --model runs/detect/runs/train_full/yolo11n/weights/best.pt
    python export_onnx.py --model best.pt --imgsz 320 --no-benchmark

출력:
    - 원본 ONNX 모델 (.onnx)
    - INT8 양자화 모델 (_int8.onnx)
    - 벤치마크 결과 (추론 속도, 파일 크기 비교)
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # OpenMP 중복 라이브러리 로드 오류 방지

import argparse
import shutil
import onnxruntime as ort
import numpy as np
from pathlib import Path
from onnxruntime.quantization import quantize_dynamic, QuantType


def export_onnx(model_path: str, imgsz: int = 640) -> str:
    """
    YOLO .pt 모델을 ONNX 포맷으로 변환

    Args:
        model_path: 학습된 .pt 모델 경로
        imgsz: 추론 시 입력 이미지 크기 (정사각형)

    Returns:
        변환된 .onnx 파일 경로
    """
    from ultralytics import YOLO

    # ultralytics 라이브러리로 YOLO 모델 로드
    model = YOLO(model_path)
    # 출력 파일명: best.pt -> best.onnx
    onnx_path = Path(model_path).with_suffix(".onnx")

    # ONNX로 내보내기 (opset 17: 최신 연산자 지원, simplify: 불필요한 노드 제거)
    model.export(
        format="onnx",
        imgsz=imgsz,
        simplify=True,
        opset=17,
    )

    # ultralytics가 기본적으로 weights/ 디렉토리에 ONNX를 저장하므로
    # 저장 위치를 탐색하여 실제 경로를 찾아냄
    exported = Path(model_path).parent.parent / "onnx" / onnx_path.name
    if not exported.exists():
        # 재귀적으로 같은 이름의 .onnx 파일 검색
        candidates = list(Path(model_path).parent.parent.rglob("*.onnx"))
        candidates = [c for c in candidates if c.name == onnx_path.name]
        if candidates:
            exported = candidates[0]
        else:
            raise FileNotFoundError(f"Exported ONNX not found near {model_path}")

    print(f"ONNX export complete: {exported}")
    return str(exported)


def quantize_onnx(onnx_path: str) -> str:
    """
    ONNX 모델에 동적 INT8 양자화 적용
    - 동적 양자화: 추론 시 activations을 실시간으로 양자화 (학습 데이터 불필요)
    - INT8 가중치: 모델 크기 약 75% 감소, 추론 속도 향상

    Args:
        onnx_path: 원본 ONNX 모델 경로

    Returns:
        양자화된 _int8.onnx 파일 경로
    """
    onnx_path = Path(onnx_path)
    # 출력 파일명: best.onnx -> best_int8.onnx
    quant_path = onnx_path.with_name(onnx_path.stem + "_int8" + onnx_path.suffix)

    # 동적 양자화 실행 (가중치를 FP32 -> INT8로 변환)
    quantize_dynamic(
        model_input=str(onnx_path),
        model_output=str(quant_path),
        weight_type=QuantType.QInt8,  # 8비트 정수 양자화
    )

    print(f"Quantized model saved: {quant_path}")
    return str(quant_path)


def benchmark(onnx_path: str, runs: int = 50) -> dict:
    """
    ONNX 모델의 추론 성능 측정
    - 워밍업 5회 후, runs회 반복 측정하여 평균 추론 시간 계산
    - CPU 환경에서 측정 (GPU 사용 시 providers 변경 필요)

    Args:
        onnx_path: 벤치마크할 ONNX 모델 경로
        runs: 추론 반복 횟수

    Returns:
        {"avg_ms": 평균 추론 시간(ms), "size_mb": 모델 파일 크기(MB)}
    """
    # ONNX Runtime 세션 생성 (CPU 추론)
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    # 모델의 입력 텐서 이름 획득 (예: "images")
    input_name = session.get_inputs()[0].name
    # 더미 입력 생성: 배치=1, 채널=3(RGB), 640x640 이미지
    dummy = np.random.randn(1, 3, 640, 640).astype(np.float32)

    import time

    # 워밍업: 첫 실행은 캐시 미스 등으로 시간이 오래 걸리므로 제외
    for _ in range(5):
        session.run(None, {input_name: dummy})

    # 실제 벤치마크 측정
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        session.run(None, {input_name: dummy})
        times.append(time.perf_counter() - start)

    # 평균 추론 시간 (초 -> 밀리초 변환)
    avg_ms = np.mean(times) * 1000
    # 모델 파일 크기 (바이트 -> 메가바이트 변환)
    size_mb = Path(onnx_path).stat().st_size / (1024 * 1024)
    return {"avg_ms": round(avg_ms, 2), "size_mb": round(size_mb, 2)}


def compare(original_onnx: str, quant_onnx: str):
    """
    원본 ONNX와 양자화된 ONNX의 성능 비교

    Args:
        original_onnx: FP32 원본 ONNX 경로
        quant_onnx: INT8 양자화 ONNX 경로
    """
    orig = benchmark(original_onnx)
    quant = benchmark(quant_onnx)

    # 결과 테이블 출력
    print("\n========== Benchmark ==========")
    print(f"{'':20s} {'Original':>12s} {'INT8 Quant':>12s}")
    print(f"{'Inference (ms)':20s} {orig['avg_ms']:>12.2f} {quant['avg_ms']:>12.2f}")
    print(f"{'Size (MB)':20s} {orig['size_mb']:>12.2f} {quant['size_mb']:>12.2f}")

    # 속도 향상 비율 계산
    speedup = orig["avg_ms"] / quant["avg_ms"] if quant["avg_ms"] > 0 else 0
    # 압축률 계산
    compress = (1 - quant["size_mb"] / orig["size_mb"]) * 100 if orig["size_mb"] > 0 else 0
    print(f"{'Speedup':20s} {speedup:>11.2f}x")
    print(f"{'Compression':20s} {compress:>11.1f}%")
    print("================================\n")


def validate_class_names(onnx_path: str):
    """
    ONNX 모델 메타데이터에서 클래스 이름 확인
    학습 시 설정한 클래스 순서가 올바르게 저장되었는지 검증용

    Args:
        onnx_path: 확인할 ONNX 모델 경로
    """
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    meta = session.get_modelmeta().custom_metadata_map
    names = meta.get("names", "")
    print(f"Model classes: {names}")


def parse_args():
    """
    명령줄 인자 파싱

    인자:
        --model:    변환할 .pt 모델 경로 (기본값: yolo11n best.pt)
        --imgsz:    ONNX 변환 시 입력 이미지 크기 (기본값: 640)
        --no-benchmark: 벤치마크 실행하지 않음
    """
    parser = argparse.ArgumentParser(description="Export YOLO .pt to ONNX + INT8 quantization")
    parser.add_argument("--model", type=str,
                        default="runs/detect/runs/train_full/yolo11n/weights/best.pt",
                        help="path to .pt model")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="export image size")
    parser.add_argument("--no-benchmark", action="store_true",
                        help="skip benchmark comparison")
    return parser.parse_args()


def main():
    args = parse_args()
    model_path = args.model

    # 모델 파일 존재 여부 확인
    if not os.path.exists(model_path):
        print(f"Model not found: {model_path}")
        return

    print(f"Model: {model_path}")
    print(f"Image size: {args.imgsz}\n")

    # Step 1: .pt -> .onnx 변환
    print("=== Step 1: ONNX Export ===")
    onnx_path = export_onnx(model_path, args.imgsz)

    # Step 2: FP32 -> INT8 동적 양자화
    print("\n=== Step 2: INT8 Dynamic Quantization ===")
    quant_path = quantize_onnx(onnx_path)

    # Step 3: 원본 vs 양자화 모델 벤치마크 비교
    if not args.no_benchmark:
        print("\n=== Step 3: Benchmark ===")
        compare(onnx_path, quant_path)

    print("Done.")


if __name__ == "__main__":
    main()
