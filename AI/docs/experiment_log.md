# Experiment Log

## 실험 요약

| ID | Date | Change | Result | Conclusion |
|----|------|---------|---------|------------|
| Baseline | - | yolov8n, yolo11n 1차 학습 | mAP50-95: 0.8014 ~ 0.8066 | yolo11n 선정 |
| Exp01 | 2025-03-22 | HNM 데이터셋 적용 | mAP50-95: **0.898** | +11.3% 개선, Exp02 불필요 |
| Exp02 | - | 증강 기법별 실험 | - | Exp01 성능 충분으로 취소 |

---

## Baseline: yolov8n vs yolo11n 비교

### 실험 개요

- **목적**: 최적 모델 선정
- **방법**: 동일 데이터셋으로 yolov8n, yolo11n 학습 후 성능 비교
- **데이터셋**: 9,999장 (train 7,999 / val 2,000)

### 하이퍼파라미터

| 항목 | 값 |
|---|---|
| Epoch | 100 (early stopping patience=20) |
| Batch | 64 |
| Image Size | 640 |
| Optimizer | AdamW |
| LR Scheduler | Cosine |

### 결과

| 지표 | yolov8n (epoch 68) | yolo11n (epoch 81) |
|---|---|---|
| Precision | 0.8053 | **0.8121** |
| Recall | 0.8068 | **0.8164** |
| mAP50 | 0.8665 | **0.8719** |
| mAP50-95 | 0.8014 | **0.8066** |

### 결론

- yolo11n이 yolov8n 대비 전 지표에서 소폭 상회
- yolo11n을 최종 모델로 선정

---

## Exp01: Hard Negative Mining

### 실험 개요

- **목적**: HNM 데이터셋으로 재학습하여 분류 정확도 향상 확인
- **방법**: 
  - HNM 데이터셋으로 재학습 (하이퍼파라미터 동일)
  - Baseline vs HNM 데이터셋 성능 비교
- **관련 논문**: Training Region-based Object Detectors with Online Hard Example Mining (Shrivastava et al., CVPR 2016)

### HNM Dataset

| 항목 | 값 |
|---|---|
| Train Images | 843 |
| Val Images | 2000 |
| 클래스별 분포 | Can: 469, Pet bottle: 908, Styrofoam: 909 |
| 구조 | images/train, images/val |

### 하이퍼파라미터

| 항목 | 값 |
|---|---|
| Epoch | 100 |
| Batch | 64 |
| Image Size | 640 |
| Optimizer | AdamW |
| LR Scheduler | Cosine |
| Warmup Epochs | 3 |

### 결과

#### Best Epoch (epoch 83)

| 지표 | Baseline | Exp01 | 개선율 |
|---|---|---|---|
| Precision | 0.8121 | **0.918** | +13.0% |
| Recall | 0.8164 | **0.897** | +9.9% |
| mAP50 | 0.8719 | **0.957** | +9.8% |
| mAP50-95 | 0.8066 | **0.898** | +11.3% |

#### 클래스별 결과

| Class | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Can | 0.905 | 0.903 | 0.951 | 0.878 |
| Pet bottle | 0.918 | 0.911 | 0.961 | 0.897 |
| Styrofoam | 0.927 | 0.880 | 0.958 | 0.919 |
| **All** | **0.917** | **0.898** | **0.957** | **0.898** |

### 분석

1. **전반적 성능 향상**: HNM 적용으로 모든 지표에서 10% 이상 개선
2. **Pet bottle 클래스 개선**: Baseline 대비 가장 큰 폭으로 개선 (0.76 → 0.897)
3. **Styrofoam 안정적**: 가장 높은 성능 유지 (0.919)
4. **Precision 향상**: False Positive 감소

### 결론

- HNM 데이터셋 적용으로 **mAP50-95 11.3% 개선** 달성
- Exp02 (증강 실험)는 Exp01 성능이 기대 이상으로 충분하여 **진행하지 않음**

---

## Exp02: 증강 기법별 실험 (취소)

### 취소 사유

- Exp01 결과가 기대 이상으로 우수 (mAP50-95: 0.898)
- 증강 기법 추가 적용 시 marginal gain이 제한적일 것으로 판단
- 시간 대비 성과 고려하여 Exp02 진행하지 않음

### 원래 계획

| 실험 | 파라미터 | 테스트 값 |
|---|---|---|
| Exp02-1 | shear | 5.0, 10.0, 15.0 |
| Exp02-2 | mixup | 0.1, 0.2, 0.3 |
| Exp02-3 | hsv_h | 0.05, 0.15, 0.25 |
| Exp02-4 | hsv_s | 0.5, 0.7, 1.0 |
| Exp02-5 | hsv_v | 0.3, 0.6 |
| Exp02-6 | translate | 0.0, 0.05, 0.1 |

---

## 최종 모델

| 항목 | 값 |
|---|---|
| 모델 | yolo11n |
| 가중치 | runs/detect/runs/exp01/hnm_training/weights/best.pt |
| mAP50-95 | 0.898 |
| 학습 데이터 | HNM 데이터셋 (843장) + 원본 val set (2000장) |