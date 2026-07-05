import os
import json
import shutil
import random
import yaml
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def load_config(path="configs/preprocess.yaml"):
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)     # YAML → dict 변환

    cfg['paths']['raw_data'] = Path(cfg['paths']['raw_data'])   # str → Path
    cfg['paths']['output'] = Path(cfg['paths']['output'])

    if cfg['parallel']['max_workers'] == 'auto':    # auto → cpu_count()
        cfg['parallel']['max_workers'] = os.cpu_count() or 4

    return cfg


cfg = load_config()


def get_label_dir(class_dir):
    """labels 폴더 확인, 없으면 상세 에러 메시지 출력"""
    label_dir = class_dir / 'labels'
    if label_dir.is_dir():
        return label_dir
    actual_dirs = [d.name for d in class_dir.iterdir() if d.is_dir()]
    raise FileNotFoundError(
        f"'{class_dir / 'labels'}' 폴더가 없습니다.\n"
        f"해당 클래스 디렉토리에 있는 폴더: {actual_dirs}\n"
        f"폴더명에 오타가 없는지 확인하세요."
    )


def collect_data():
    """클래스별로 (이미지경로, JSON경로, 클래스ID) 수집 후 dict 반환"""
    per_class = {name: [] for name in cfg['classes']}
    for class_name in cfg['classes']:
        class_dir = cfg['paths']['raw_data'] / class_name
        if not class_dir.is_dir():
            continue
        class_id = cfg['classes'].index(class_name)
        img_dir = class_dir / 'images'
        label_dir = get_label_dir(class_dir)
        for img_path in img_dir.iterdir():
            if img_path.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
                continue
            json_path = label_dir / (img_path.stem + '.json')
            if json_path.is_file():
                per_class[class_name].append((str(img_path), str(json_path), class_id))
    return per_class


def split_data(per_class):
    """클래스별로 셔플 후 train/val 분할 (Stratified Split)"""
    random.seed(cfg['split']['seed'])
    train_data = []
    val_data = []
    for items in per_class.values():
        random.shuffle(items)
        split_idx = int(len(items) * cfg['split']['train_ratio'])
        train_data.extend(items[:split_idx])
        val_data.extend(items[split_idx:])
    return train_data, val_data


def yolo_bbox_from_ann(ann, img_w, img_h, class_id):
    """
    JSON annotation 한 건을 YOLO 포맷 문자열로 변환
    - BOX: POINTS = [[x, y, w, h]]
    - POLYGON: POINTS = [[x1,y1], [x2,y2], ...] -> 외접 사각형 변환
    """
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
    x_center = (x + w / 2) / img_w
    y_center = (y + h / 2) / img_h
    w_yolo = w / img_w
    h_yolo = h / img_h
    return f"{class_id} {x_center:.6f} {y_center:.6f} {w_yolo:.6f} {h_yolo:.6f}"


def process_one(item):
    """
    단일 이미지 처리 (병렬 실행 단위)
    - 이미지 이동(원본 이미지 보존 안됨.)
    - JSON -> YOLO TXT 변환
    """
    img_path, json_path, class_id, split_type = item
    file_name = os.path.basename(img_path)
    base_name = os.path.splitext(file_name)[0]

    with Image.open(img_path) as img:
        img_w, img_h = img.size

    target_img = str(cfg['paths']['output'] / 'images' / split_type / file_name)
    shutil.move(img_path, target_img)

    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    yolo_lines = [
        yolo_bbox_from_ann(ann, img_w, img_h, class_id)
        for ann in json_data['ANNOTATION_INFO']
    ]

    target_txt = str(cfg['paths']['output'] / 'labels' / split_type / (base_name + '.txt'))
    with open(target_txt, 'w') as f:
        f.write('\n'.join(yolo_lines) + '\n')

    return file_name


if __name__ == '__main__':
    for split in ['train', 'val']:
        (cfg['paths']['output'] / 'images' / split).mkdir(parents=True, exist_ok=True)
        (cfg['paths']['output'] / 'labels' / split).mkdir(parents=True, exist_ok=True)

    all_data = collect_data()
    train_data, val_data = split_data(all_data)

    for split_type, data in [('train', train_data), ('val', val_data)]:
        items = [(*item, split_type) for item in data]
        with ThreadPoolExecutor(max_workers=cfg['parallel']['max_workers']) as executor:
            futures = [executor.submit(process_one, item) for item in items]
            for _ in as_completed(futures):
                pass

    print("데이터셋 구축 완료!")
