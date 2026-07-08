# Week 1 — AI 파트 진행 상황

> **기간**: 2026.07.03 ~ 2026.07.08  
> **목표**: 베이스라인 데이터셋 구축 + YOLO 모델 학습 + 실시간 비전 파이프라인 완성

---

## 1. 데이터셋 구축

| 항목 | 내용 |
|---|---|
| 출처 | AIHub (재활용품 분류 및 선별 데이터) |
| 클래스 | 3종 — Can, Pet bottle, Styrofoam |
| 전체 장수 | 9,999장 |
| 분할 비율 | train 8 : val 2 |
| 경로 | `AI/data/dataset/` |
| 구조 | `AI/data/dataset/data.yaml` |
| 링크 | ([Google Drive](https://drive.google.com/file/d/1YwxGctreCivOjuJ5DvqFp6z17AK1IuOL/view?usp=drive_link))

```yaml
# data.yaml
path: AI/data/dataset
train: images/train
val: images/val
nc: 3
names:
  0: Can
  1: Pet bottle
  2: Styrofoam
```

---

## 2. YOLO 모델 1차 학습

### 학습 설정

| 항목 | 값 |
|---|---|
| 모델 | yolov8n.pt, yolo11n.pt |
| 에폭 | 100 (early stopping patience=20) |
| 배치 크기 | 64 |
| 이미지 크기 | 640 |
| 옵티마이저 | AdamW |
| LR 스케줄러 | Cosine (cos_lr=True) |
| 데이터 증강 | YOLO default(Mosaic, RandAugment, Erasing 등) |
| GPU | Colab L4 |

### 학습 결과

| 모델 | 가중치 크기 | 가중치 경로 |
|---|---|---|
| yolov8n | 6.0 MB | `runs/detect/runs/train_full/yolov8n/weights/best.pt` |
| yolo11n | 5.2 MB | `runs/detect/runs/train_full/yolo11n/weights/best.pt` |

### 산출물
- `train.py` - YOLO 모델 학습 코드
- `results.png`, `BoxPR_curve.png`, `confusion_matrix.png` 등 성능 그래프
- `args.yaml` — 학습 하이퍼파라미터 기록

---

## 3. 실시간 비전 파이프라인

### 구조
```
입력(웹캠/파일) → YOLO 추론 → 바운딩박스 → 출력
```

### 파일
- `AI/src/inference/detect_realtime.py`

### 기능
| 기능 | 설명 |
|---|---|
| 입력 | 웹캠(기본) 또는 동영상 파일 |
| 추론 | YOLO 기반 객체 탐지(3 클래스 분류 및 탐지) |
| 출력 | 바운딩 박스 시각화 (실시간 화면) |
| 설정 | argparse → `--model`, `--source`, `--conf`, `--iou`, `--imgsz` |

### 실행 방법
```bash
python AI/src/inference/detect_realtime.py --model runs/detect/runs/train_full/yolov8n/weights/best.pt
```

### 출력 데이터 구조

| 필드 | 타입 | 예시 |
|---|---|---|
| class_name | str | `"Can"` |
| confidence | float | `0.92` |
| bbox (xyxy) | (int, int, int, int) | `(100, 50, 200, 150)` |


---

## 4. 다음 주차 계획 (Week 2)

- [ ] 데이터 증강 기법 추가 적용 후 모델 재학습
- [ ] 모델 성능 평가 (mAP, IoU 측정)
- [ ] ONNX/TensorRT 등 경량화 변환
- [ ] ROS 팀과 출력 인터페이스 확정
