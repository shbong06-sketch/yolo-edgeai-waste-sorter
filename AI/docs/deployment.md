# Deployment

## Environment

| Item | Version |
|------|---------|
| OS | Windows 11 (64bit), Ubuntu 24.04 |
| Python | 3.10.20 (Anaconda) |
| ultralytics | 8.4.87 |
| onnx | 1.22.0 |
| onnxruntime | 1.23.2 |

---

## Model Export

```
best.pt (PyTorch)
    ↓  ultralytics export (opset 17, simplify)
best.onnx (ONNX FP32)
    ↓  onnxruntime quantize_dynamic (INT8)
best_int8.onnx (ONNX INT8)
```

- `.pt` → `.onnx`: `AI/src/training/export_onnx.py`

---

## Optimization

| Technique | Description | Status |
|-----------|-------------|--------|
| INT8 | 8비트 정량화 → 모델 크기 약 75% 감소 | onnxruntime 동적 양자화 적용 (CPU 한계) |

---

## Benchmark

CPU 환경 기준 (Intel/AMD)

| Model | Inference (ms) | FPS | Size (MB) |
|-------|---------------|-----|-----------|
| PyTorch (.pt) | 59.47 | 16.8 | 5.21 |
| ONNX FP32 | 27.30 | 36.6 | 10.11 |

- **ONNX Speedup**: 2.18x (PyTorch 대비)
- **Trade-off**: ONNX는 추론 속도 2.2배 향상, 파일 크기 2배 증가

> INT8 양자화 모델은 `onnxruntime` CPU에서 `ConvInteger` 미지원으로 벤치마크 불가.

---

## Deployment Procedure

1. **모델 학습**
   ```bash
   python AI/src/training/train.py
   ```
   - 학습 결과: `runs/detect/runs/exp01/hnm_training/weights/best.pt`

2. **ONNX 변환**
   ```bash
   python AI/src/training/export_onnx.py
   ```
   - 출력: `best.onnx`, `best_int8.onnx`

---

## Known Issues

- INT8 양자화 모델: `onnxruntime` CPU에서 `ConvInteger(10)` 미지원
- **해결**: 배포 환경에 GPU가 있는 경우 `onnxruntime-gpu` 설치 후 INT8 모델 사용 가능

### GPU 환경에서 INT8 모델 사용

```bash
pip install onnxruntime-gpu
```

```python
import onnxruntime as ort

# GPU 환경에서 INT8 모델 로드
session = ort.InferenceSession(
    "best_int8.onnx",
    providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
)
```

---

## Future Work

- `onnxruntime-gpu` 설치 후 INT8 양자화 모델 벤치마크 추가
- 배치 추론 및 Dynamic Shape 적용 검토
- 실시간 추론 파이프라인 최적화
