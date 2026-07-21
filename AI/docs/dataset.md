# Dataset

> **최종 업데이트**: 2026.07.08  
> **용도**: YOLO 객체 탐지 모델 학습용 커스텀 데이터셋

---

## 1. Overview

| 항목 | 내용 |
|---|---|
| 데이터셋 명 | `yolo_waste_dataset_v3.0` |
| 출처 | AIHub (재활용품 분류 및 선별 데이터) |
| 클래스 | 3종 — Can, Pet bottle, Styrofoam |
| 전체 장수 | 9,999장 |
| 분할 비율 | train 8 : val 2 (80:20) |
| 라벨 포맷 | YOLO format (`class_id x_center y_center width height`) |
| 최종 경로 | `AI/data/dataset/` |
| 설정 파일 | `AI/data/dataset/data.yaml` |
| 메타데이터 | `AI/data/dataset/dataset_metadata.csv` |

### 1.1 데이터 출처

| 구분 | 수량 | 설명 |
|---|---|---|
| AIHub 선별영상 추출 | 9,000장 | 재활용품 분류 및 선별 영상에서 프레임 추출 |
| 개별 재활용품 이미지 | 999장 | 직접 촬영 |
| **합계** | **9,999장** | |

> AIHub 링크: [재활용품 분류 및 선별 데이터](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=data&dataSetSn=71362)

### 1.2 클래스 정보

| Class ID | 클래스명 | 설명 |
|---|---|---|
| 0 | Can | 금속 캔 |
| 1 | Pet bottle | 페트병 |
| 2 | Styrofoam | 스티로폼 |

---

## 2. Dataset Statistics

### 2.1 전체 분포

| Class | Train | Val | Total |
|---|---|---|---|
| Can | 2,667 | 666 | 3,333 |
| Pet bottle | 2,666 | 667 | 3,333 |
| Styrofoam | 2,666 | 667 | 3,333 |
| **Total** | **7,999** | **2,000** | **9,999** |

### 2.2 이미지 사양

| 항목 | 값 |
|---|---|
| 해상도 | 640×640 (YOLO 입력 기준) |
| 포맷 | JPG, JPEG, PNG |
| 최대 파일 크기 | 1.0 MB (이상 시 리사이즈) |

---


## 3. 전처리 파이프라인

### 3.1 전체 흐름

```
raw_data (AIHub 원본)
    │
    ▼ [preprocess_fast.py]
full_dataset (JSON → YOLO TXT 변환 + 8:2 분할)
    │
    ▼ [build_dataset.py]
dataset (클래스별 균형 샘플링 + 메타데이터 생성)
    │
    ▼ [fix_jpeg.py]
dataset (이미지 리사이즈 및 압축)
    │
    ▼ [sample_dataset.py]  (선택)
sample_dataset (소규모 테스트용)
```

### 3.2 스크립트별 역할

| 스크립트 | 경로 | 역할 |
|---|---|---|
| `preprocess.py` | `AI/src/preprocessing/preprocess.py` | JSON 어노테이션을 YOLO TXT 포맷으로 변환(확인용 코드), train/val 8:2 분할 |
| `preprocess_fast.py` | `AI/src/preprocessing/preprocess_fast.py` | `preprocess.py`의 병렬 처리 버전 (YAML 설정 파일 기반) |
| `build_dataset.py` | `AI/src/preprocessing/build_dataset.py` | 전체 데이터에서 클래스별 균형 샘플링 후 최종 데이터셋 구축 |
| `sample_dataset.py` | `AI/src/preprocessing/sample_dataset.py` | 소규모 샘플 데이터셋 생성 (빠른 모델 비교 테스트용) |
| `fix_jpeg.py` | `AI/src/preprocessing/fix_jpeg.py` | 이미지 리사이즈 (640px) 및 JPEG 품질 압축 (85) |

---

## 4. Annotation

### 4.1 라벨 변환 규칙

원본 JSON 어노테이션(`ANNOTATION_INFO`)에서 YOLO TXT 포맷으로 변환합니다.

| 원본 형 변환 | 변환 방법 |
|---|---|
| `SHAPE_TYPE: BOX` | `POINTS = [[x, y, w, h]]` → 직접 정규화 |
| `SHAPE_TYPE: POLYGON` | 외접 사각형(Bounding Box)으로 변환 후 정규화 |

### 4.2 라벨 형태

```
YOLO 포맷: class_id x_center y_center width height
(모든 값은 이미지 크기 대비 0~1로 정규화)
```

---

## 5. 설정 파일

### 5.1 `data.yaml` (학습용)

```yaml
path: AI/data/dataset
train: images/train
val: images/val
nc: 3
names:
  0: Can
  1: Pet bottle
  2: Styrofoam
```

### 5.2 `preprocess.yaml` (전처리 설정)

```yaml
paths:
  raw_data: AI/data/raw_data
  output: AI/data/full_dataset

classes:
  - Can
  - Pet bottle
  - Styrofoam

split:
  train_ratio: 0.8
  seed: 42

parallel:
  max_workers: auto    # auto → os.cpu_count()
```

---

## 6. 메타데이터

`build_dataset.py` 실행 시 생성되는 `dataset_metadata.csv`에 이미지별 정보가 기록됩니다.

| 필드 | 설명 | 예시 |
|---|---|---|
| `new_file` | 리네이밍된 파일명 | `dataset_000001.jpg` |
| `original_file` | 원본 파일명 | `video_001_frame_042.jpg` |
| `classes` | 클래스 ID (쉼표 구분) | `0,1` |
| `class_names` | 클래스명 (쉼표 구분) | `Can,Pet bottle` |
| `split` | 데이터 분할 | `train` / `val` |
| `source` | 데이터 출처 | `영상추출` |

---

## 7. 다운로드

| 항목 | 내용 |
|---|---|
| 파일명 | `yolo_waste_dataset_v1.0.zip` |
| 링크 | [Google Drive](https://drive.google.com/file/d/1G4qchajo2-Tmv9D_KOxuKr_NzRUwT2DO/view?usp=sharing) |
| 압축 해제 경로 | `AI/data/dataset/` |

---

## 8. Dataset Issues

| 항목 | 내용 |
|---|---|
| bbox 누락 | 일부 이미지에서 JSON 어노테이션 파일은 존재하나 `ANNOTATION_INFO` 내 bbox 좌표가 누락된 케이스 존재 |
| 겹침 | 이미지 내 여러 객체가 겹쳐 있어 정확한 bbox 경계 구분이 어려운 샘플 다수 → 탐지 난이도 상승 |
| 클래스 간 형태 다양성 | Pet bottle의 색상(투명/파랑/초록), 형태(구부러짐/찌그러짐), 라벨 유무 등 intra-class variation이 큼 |
| 배경 편향 | 학습 데이터의 배경이 단조로움(대부분 어두운 컨베이어 벨트 이미지) |

---

## 9. Dataset Version

| 버전 | 변경 내용 |
|---|---|
| v1.0 | raw 데이터 전체 이미지 대상 랜덤 샘플링 (클래스 비율 미고려) |
| v2.0 | 클래스별 비율 동일하게 수정 (균형 샘플링 적용) |
| v3.0 | 메타데이터 CSV 파일 인코딩을 UTF-8로 수정하여 깨짐 문제 해결, 이미지 사이즈 통일(640*640) |

---