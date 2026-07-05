import os
import json
import shutil
import random
from PIL import Image


# 1. 경로 설정 >> config에 넣기
RAW_DATA_DIR = r"data\raw_data"
OUTPUT_DIR = r"data\dataset"
TRAIN_RATIO = 0.8  # Train 80%, Val 20%

# 2. 클래스 정의 (원래 폴더명들을 리스트로 적어주세요. 인덱스가 클래스 번호가 됩니다)
CLASSES = ['Can', 'Pet bottle', 'Styrofoam'] 
class_map = {name: idx for idx, name in enumerate(CLASSES)}

# 3. 출력 폴더 생성
for split in ['train', 'val']:
    os.makedirs(os.path.join(OUTPUT_DIR, 'images', split), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, 'labels', split), exist_ok=True)

# 4. 데이터 수집
all_data = [] # (이미지 경로, JSON 경로, 클래스 ID) 튜플들을 담을 리스트

for class_name in CLASSES:
    class_dir = os.path.join(RAW_DATA_DIR, class_name)
    if not os.path.exists(class_dir):
        continue
        
    class_id = class_map[class_name]
    
    img_dir = os.path.join(class_dir, 'images')
    # Pet bottle는 'lables' 폴더명 오타 처리
    label_dir = os.path.join(class_dir, 'labels')
    if not os.path.exists(label_dir):
        label_dir = os.path.join(class_dir, 'lables')

    # 폴더 내 파일 확인 (이미지명과 json명이 같다고 가정)
    files = os.listdir(img_dir)
    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    for img_name in images:
        base_name = os.path.splitext(img_name)[0]
        json_name = base_name + '.json'
        json_path = os.path.join(label_dir, json_name)
        
        if os.path.exists(json_path):
            all_data.append((os.path.join(img_dir, img_name), json_path, class_id))

# 5. 데이터 셔플 및 분할
random.seed(42) # 결과 재현을 위한 시드 고정
random.shuffle(all_data)
split_idx = int(len(all_data) * TRAIN_RATIO)
train_data = all_data[:split_idx]
val_data = all_data[split_idx:]

# 6. 변환 및 복사 함수
def process_and_copy(data_list, split_type):
    for img_path, json_path, class_id in data_list:
        file_name = os.path.basename(img_path)
        base_name = os.path.splitext(file_name)[0]
        
        # 이미지 크기 구하기 (정규화용)
        with Image.open(img_path) as img:
            img_w, img_h = img.size
            
        # 이미지 복사
        target_img_path = os.path.join(OUTPUT_DIR, 'images', split_type, file_name)
        shutil.copy(img_path, target_img_path)
        
        # JSON 읽어서 YOLO TXT로 변환
        target_txt_path = os.path.join(OUTPUT_DIR, 'labels', split_type, base_name + '.txt')
        
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            
        yolo_lines = []
        for ann in json_data['ANNOTATION_INFO']:
            shape_type = ann.get('SHAPE_TYPE', 'BOX')
            pts = ann['POINTS']
            
            if shape_type == 'POLYGON':
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                x = min(xs)
                y = min(ys)
                w = max(xs) - x
                h = max(ys) - y
            else:
                x, y, w, h = pts[0]
            
            x_center = (x + (w / 2)) / img_w
            y_center = (y + (h / 2)) / img_h
            w_yolo = w / img_w
            h_yolo = h / img_h
            yolo_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w_yolo:.6f} {h_yolo:.6f}")
        
        # TXT 파일 저장
        with open(target_txt_path, 'w') as f_out:
            f_out.write('\n'.join(yolo_lines) + '\n')

# 실행
process_and_copy(train_data, 'train')
process_and_copy(val_data, 'val')
print("데이터셋 구축 완료!")