환경 설정 (conda, requirements.txt)
학습 실행 방법 (train.py)
추론 실행 방법 (detect_realtime.py + argparse 옵션)
모델 가중치 파일 위치 및 형식
ROS2 연동을 위한 인터페이스 (출력 데이터 구조: class_name, confidence, bbox)

# Deployment

## Environment

Jetson Orin Nano

JetPack

CUDA

cuDNN

TensorRT

Python

---

## Model Export

.pt

↓

ONNX

↓

TensorRT

---

## Optimization

FP16

INT8

Batch

Dynamic Shape

---

## Benchmark

| Model | FPS | Latency |

---

## Deployment Procedure

1.

2.

3.

---

## Known Issues

...

---

## Future Work