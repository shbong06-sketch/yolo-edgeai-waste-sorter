# Deployment

## Environment

| Item | Version |
|------|---------|
| OS | Ubuntu 24.04 |
| CPU | Intel Core Ultra 7 155H (16core / 22 thread, 4.8GHz) |
| ROS2 | Jazzy |
| Python | 3.10.20 (Anaconda) |
| ultralytics | 8.4.87 |
| onnx | 1.22.0 |
| onnxruntime | 1.23.2 |
| GPU | NVIDIA RTX 3050 |

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
| INT8 | 8비트 정량화 → FP32 대비 모델 크기 약 75% 감소 | onnxruntime 동적 양자화 적용 (CPU 한계) |

---

## Benchmark

### Inference Latency (오프라인 벤치마크)

#### CPU 환경
- `export_onnx.py` 기반 단일 추론 측정 (50회 평균, 워밍업 5회).
- ROS2 파이프라인 내 실제 처리 시간과 차이가 있을 수 있음.

| Model | Inference (ms) | FPS | Size (MB) |
|-------|---------------|-----|-----------|
| PyTorch (.pt) | 59.47 | 16.8 | 5.21 |
| ONNX FP32 | 27.30 | 36.6 | 10.11 |

- **ONNX Speedup**: 2.18x (PyTorch 대비)
- **Trade-off**: ONNX는 추론 속도 2.2배 향상, 파일 크기 2배 증가

#### GPU 환경

- `export_onnx.py` 기반 단일 추론 측정 (50회 평균, 워밍업 5회).
- GPU: NVIDIA RTX 3050 (CUDAExecutionProvider)

| Model | Inference (ms) | FPS | Size (MB) |
|-------|---------------|-----|-----------|
| PyTorch (.pt) | 8.41 | 118.9 | 5.21 |
| ONNX FP32 (CPU) | 24.58 | 40.7 | 10.11 |
| ONNX FP32 (GPU) | 8.47 | 118.1 | 10.11 |
| ONNX INT8 (CPU) | 99.31 | 10.1 | 2.87 |
| ONNX INT8 (GPU) | 126.12 | 7.9 | 2.87 |

- **ONNX FP32 GPU vs PyTorch**: 0.99x (동등 수준)
- **ONNX FP32 CPU vs PyTorch**: 0.34x (CPU는 3배 느림)
- **INT8 동적 양자화**: GPU/CPU 모두 FP32 대비 현저히 느림 (모델 크기 축소 효과 미미)
- **분석**: RTX 3050에서는 PyTorch와 ONNX GPU 성능이 동등. INT8 동적 양자화는 소형 모델(YOLOv8n)에서 양자화 변환 비용이 치명적으로 보임.

### ROS2 Pipeline Benchmark

실시간 카메라 파이프라인에서 측정 (카메라노드 -> 탐지 노드 각각 실행)
- 측정 방법: `ros2 topic hz`, `ros2 topic bw`로 마지막 5개 샘플 평균
- 카메라노드와 탐지 노드를 별도 프로세스로 실행

#### Topic Statistics

#### CPU 환경

| Topic | Hz(avg) | BW |
|---|---|---|
| /camera/image_raw(best.pt) | 24.20 | 22.10 (MB/s) |
| /detection_results(best.pt) | 19.27 | 697.2 (KB/s) |
| /camera/image_raw(best.onnx) | 7.484 | 5.625 (MB/s) |
| /detection_results(best.onnx) | 20.71 | 1.56 (KB/s) |
> **Note**: best.onnx 사용 시 카메라 토픽 Hz가 24.20 -> 7.484로 급락한 것은 onnxruntime 추론이 CPU 자원을 과점유하여 카메라 노드의 타이머 콜백이 지연된 것으로 추측됨.
> (두 노드가 동일한 CPU 코어를 경쟁)

#### GPU 환경

| Topic | Hz(avg) | BW |
|---|---|---|
| /camera/image_raw(best.pt) | 8.63 | 6.50 (MB/s) |
| /detection_results(best.pt) | 30.00 | 1.08 (KB/s) |
| /camera/image_raw(best.onnx) | 7.13 | 5.87 (MB/s) |
| /detection_results(best.onnx) | 30.01 | 1.08 (KB/s) |
| /camera/image_raw(best_int8.onnx) | 19.43 | 23.39 (MB/s) |
| /detection_results(best_int8.onnx) | 7.84 | 283 (KB/s) |
> **Note**: device를 cuda로 설정 시, best.pt와 best.onnx 두 경우 모두, /detection_results 토픽의 Hz가 설정 값인 30을 달성함.
> 다만, /camera/image_raw 토픽의 경우 설정 값 30에 비해, 상당히 부족한 값을 보임.

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

- INT8 동적 양자화 모델: GPU/CPU 모두 FP32 대비 현저히 느림
  - **원인**: `DynamicQuantizeLinear`, `ConvInteger` 연산의 런타임 오버헤드가 모델 축소 이득 상쇄
  - **해결**: 동적 양자화 대신 정적 양자화(static quantization) + calibration 데이터 적용 검토 필요

---

## Future Work

- 카메라 인식 및 실시간 추론 파이프라인 최적화
- 정적 양자화(static quantization) + calibration 데이터 기반 INT8 최적화 고려
- 배치 추론 및 Dynamic Shape 적용 검토

---

## Optimization log

### OPT01. QoS 설정 변경

#### 변경사항

- `camera/image_raw` 토픽의 QoS를 `qos_profile_sensor_data`로 설정

#### 개선효과

- 카메라 토픽은 개선, 탐지 토픽은 악화됨.
- 카메라 Hz 증가 : 카메라 노드가 더 빠르게 프레임을 캡처하게 됨.
- 탐지 Hz 급락 : QoS 변경이 탐지 노드의 처리 우선 순위를 낮추거나 자원 경쟁을 심화시킨 것으로 보임.

| Topic | Hz(avg) | BW |
|---|---|---|
| /camera/image_raw(best.pt) | 10.454 | 7.64 (MB/s) |
| /detection_results(best.pt) | 12.841 | 1.02 (KB/s) |
| /camera/image_raw(best.onnx) | 13.821 | 7.51 (MB/s) |
| /detection_results(best.onnx) | 8.587 | 0.42 (KB/s) |
| /camera/image_raw(best_int8.onnx) | 28.111 | 26.94 (MB/s) |
| /detection_results(best_int8.onnx) | 6.513 | 0.31 (KB/s) |

### OPT02. detection node 개선 - ONNX 최적화 적용

#### 변경사항

- `inference_engine.py` 추가하여 파일 확장자에 따라 적절한 추론 엔진을 선택하여 사용하도록 개선.

#### 개선효과

1. best.onnx - 유일한 개선 모델
    - 탐지 Hz 37% 향상
    - 카메라 Hz 동일

2. best.pt - 역효과
    - 탐지 Hz -10% 약화
    - 카메라 Hz - 35% 개선
    - 카메라 Hz는 올랐지만, 탐지 Hz 감소. 카메라가 더 빠르게 프레임을 보내주면서 탐지 노드의 부하가 발생한 것으로 추정.

3. best_int.onnx - 여전히 성능 부진
    - 탐지 Hz 미미한 개선.
    - 작은 모델(yolo11n)에서 동적 양자화를 사용한 한계가 보임.
    - 현재 단계에서는 탈락시키고, 향후 과제로 정적 양자화 및 calibration 데이터 적용을 고려해 봐야 할 것으로 보임.

| Topic | Hz(avg) | BW |
|---|---|---|
| /camera/image_raw(best.pt) | 14.121 | 7.40 (MB/s) |
| /detection_results(best.pt) | 11.542 | 1.61 (KB/s) |
| /camera/image_raw(best.onnx) | 13.896 | 7.23 (MB/s) |
| /detection_results(best.onnx) | 11.754 | 2.74 (KB/s) |
| /camera/image_raw(best_int8.onnx) | 28.232 | 27.57 (MB/s) |
| /detection_results(best_int8.onnx) | 7.028 | 0.31 (KB/s) |

### OPT03. detection node 개선2 - 프레임 스킵 + 멀티스레드 콜백

#### 변경 사항

- `detector_node.py` - 프레임 스킵 + 멀티스레드 콜백 적용 + 매 프레임마다 로깅하던 것을 타이머 기반으로 1초 간격 요약해 로깅하도록 변경

| 항목 | Before | After |
|------|--------|-------|
| 콜백 구조 | 동기식, 모든 프레임 처리 | `MutuallyExclusiveCallbackGroup` + 추론 전용 스레드 |
| 프레임 스킵 | 없음 | `_busy` 플래그로 추론 중 새 프레임 자동 스킵 (latest-frame 방식) |
| 로깅 | 매 프레임 `.info()` | 1초 간격 요약 로깅 (수신/처리/스킵 카운트) |
| executor | `rclpy.spin()` | `MultiThreadedExecutor` |

#### 아키텍처

```
[카메라 노드] → image_raw → [image_callback] → 최신 프레임 저장 (즉시 반환)
                                                      ↓
                                              [추론 스레드] → 추론 실행 → 결과 발행
```

- **image_callback**: 프레임 저장만 수행 (빠른 반환), 추론 중이면 스킵
- **추론 스레드**: `_inference_loop()` — 이벤트 기반, 최신 프레임만 처리
- **스레드 안전성**: `_busy` 플래그 + `threading.Lock`으로 경쟁 조건 방지
- **executor**: `MultiThreadedExecutor`로 멀티스레드 콜백 그룹 지원

#### 개선효과

- 기대 대비 성능 악화 : 모든 케이스에서 카메라와 탐지 Hz 감소
- 원인 추정
    1. 스레드 오버헤드 의심(Lock, Event, Thread 생성, 관리 비용 추가)
    2. 카메라 노드 병목

| Topic | Hz(avg) | BW |
|---|---|---|
| /camera/image_raw(best.pt) | 10.037 | 9.21 (MB/s) |
| /detection_results(best.pt) | 9.747 | 4.01 (KB/s) |
| /camera/image_raw(best.onnx) | 11.032 | 11.92 (MB/s) |
| /detection_results(best.onnx) | 11.678 | 0.37 (KB/s) |

### OPT04. 메시지 타입 변경 - 압축 토픽(CompressedImage) 및 detection node 개선

#### 변경사항

- 메시지 타입 변경 - `Image` -> `CompressedImage`
- log 형태 변경 - 객체 탐지 결과 포함하는 형태로
- `detector_node.py` - 레이스 컨디션 수정 + 메모리 관리 + 7개 항목 최적화

| 항목 | Before | After |
|------|--------|-------|
| 상태 전이 순서 | `busy=False → frame=None` (해제 후 초기화로 인해 1번과 2번 사이에 이미지 콜백이 들어오면 프레임 유실 위험) | `frame=None → busy=False` (안전) |
| 메모리 관리 | `np.frombuffer()` (읽기 전용 뷰, 연속적이지 않은 메모리 가능성 존재. cv2.cvtColor() 등 추가 연산 시 내부적 복사 발생) | `np.frombuffer().copy()` (쓰기 가능, C-contiguous) |
| 이중 복사 | bgr8에서 `copy()` + `cvtColor()` | bgr8은 `copy().reshape()`만 (cvtColor 불필요) |
| busy 체크 시점 | 변환 후 체크 | 변환 전 체크 (불필요한 변환 방지. busy 상태일 때 이미지 변환 수행하지 않음 -> CPU 자원 절약) |
| 프레임 전달 | `threading.Event` (1개만 처리. set()과 clear() 사이 들어오는 프레임 유실 위험) | `queue.Queue(maxsize=1)` (최신 프레임 유지, 이전 프레임 자동 폐기 -> 프레임 유실 방지) |
| 시간 API | `time.time()` (시스템 시간 의존) | `self.get_clock().now()` (ROS2 clock, 시간 변경 안정적으로) |
| 메시지 변환 | 반복문 내 `append` | `_det_to_detection()` 헬퍼 메서드 분리 + 리스트 컴프리헨션 사용 |
| imgsz 설정 | 하드코딩 `640` | `declare_parameter('imgsz', 640)` |
| 메시지 타입 | `Image` | `CompressedImage` |

#### 아키텍처

```
[카메라 노드] → image_raw → [image_callback] → busy 체크 → 변환 → Queue 저장
                                                            ↓
                                                    [추론 스레드] → Queue.get() → copy() → 추론 → 결과 발행
```

- **image_callback**: busy 체크 → 변환 → Queue 저장 (빠른 반환)
- **추론 스레드**: `queue.get()`으로 프레임 수신 → `copy()`로 독립성 확보
- **스레드 안전성**: `_busy` 플래그 + `threading.Lock` + `queue.Queue`로 경쟁 조건 방지
- **메모리 안전성**: `.copy()`로 C-contiguous + WRITEABLE 배열 보장

#### 개선효과

1. **레이스 컨디션 방지**: 프레임 초기화 → busy 해제 순서로 새 프레임 유실 방지
2. **메모리 안전성**: `np.frombuffer().copy()`로 읽기 전용 뷰 문제 해결
3. **CPU 효율**: busy 상태일 때 이미지 변환 수행하지 않음 (불필요한 연산 제거)
4. **프레임 유실 방지**: Queue 기반으로 모든 프레임이 순서대로 처리
5. **시스템 시간 독립**: ROS2 clock 사용으로 NTP 동기화 영향 제거
6. **유지보수성**: 헬퍼 메서드 분리로 코드 가독성 향상

| Topic | Hz(avg) | BW |
|---|---|---|
| /camera/image_raw(best.pt) | 30.010 | 799.39 (KB/s) |
| /detection_results(best.pt) | 20.051 | 8.40 (KB/s) |
| /camera/image_raw(best.onnx) | 30.000 | 767.59 (KB/s) |
| /detection_results(best.onnx) | 17.832 | 2.51 (KB/s) |

#### 분석

1. **카메라 Hz 30 도달** (가장 큰 개선)
   - `best.onnx`: 7.13 → 30.000 Hz (4.2배)
   - `best.pt`: 8.63 → 30.010 Hz (3.5배)
   - 압축 메시지(CompressedImage) 전환으로 네트워크 대역폭 부담 감소 → 카메라 노드 타이머 콜백 정상 동작

2. **대역폭 87% 감소**
   - `best.onnx`: 5.87 MB/s → 767.59 KB/s
   - JPEG 압축으로 인한 데이터 크기 감소가 주 요인

3. **탐지 Hz 감소 (trade-off)**
   - `best.onnx`: 30.01 → 17.832 Hz
   - `best.pt`: 30.00 → 20.051 Hz
   - JPEG 디코딩(`cv2.imdecode`) 오버헤드가 탐지 노드에 추가되어 처리량 감소
   - 카메라 Hz가 30으로 증가하면서 탐지 노드에 더 많은 프레임이 도착 → 프레임 스킵 증가

4. **결론**
   - BW 절감과 카메라 Hz 안정화 목표 달성
   - 탐지 Hz 감소는 JPEG 디코딩 오버헤드로 인한 것이며, 향후 디코딩 최적화나 하드웨어 가속 적용 시 개선 가능

### Final Benchmark

| Topic | Before | After |
|------|--------|-------|
| /camera/image_raw(best.onnx) | 7.13 Hz, 5.87 MB/s | 30.000 Hz, 767.59 KB/s |
| /detection_results(best.onnx) | 30.01 Hz, 1.08 KB/s | 17.832 Hz, 2.51 KB/s |