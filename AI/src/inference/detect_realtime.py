# detect_realtime.py
# YOLO 모델을 사용한 실시간 객체 탐지 (웹캠 또는 비디오 파일)

import argparse
import cv2
import torch
from ultralytics import YOLO
from pathlib import Path

# 탐지할 객체 클래스 이름 (모델 학습 시 사용한 클래스 순서와 일치해야 함)
CLASS_NAMES = ["Can", "Pet bottle", "Styrofoam"]

# 실행 시작 시점의 설정을 터미널에서 변경할 수 있도록 argparse 사용.
def parse_args():
    # 명령행 인자 파싱 함수
    parser = argparse.ArgumentParser(description="YOLO real-time detection")
    # --model: 학습된 YOLO 가중치 파일 경로
    parser.add_argument("--model", type=str, default="runs/detect/runs/train_full/yolo11n/weights/best.pt",
                        help="model path (pt file)")
    # --source: 비디오 입력 소스 (0=웹캠, 또는 동영상 파일 경로)
    parser.add_argument("--source", type=str, default="0",
                        help="video source: 0(webcam) or video file path")
    # --conf: 탐지 신뢰도 임계값 (이 값 이상만 출력)
    parser.add_argument("--conf", type=float, default=0.5,
                        help="confidence threshold")
    # --iou: NMS(Non-Maximum Suppression) IoU 임계값
    parser.add_argument("--iou", type=float, default=0.45,
                        help="NMS IoU threshold")
    # --imgsz: 모델 입력 이미지 크기 (정사각형)
    parser.add_argument("--imgsz", type=int, default=640,
                        help="input image size")
    return parser.parse_args()


def main():
    # 1. 인자 읽기 및 디바이스 설정
    args = parse_args()

    # CUDA(GPU) 사용 가능하면 GPU, 아니면 CPU 사용
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print(f"Loading model: {args.model}")

    # 2. YOLO 모델 로드
    model = YOLO(args.model)

    # 3. 비디오 캡처 객체 생성
    #    --source가 숫자 문자열이면 웹캠 인덱스, 아니면 파일 경로로 간주(카메라 영상/동영상 모두 처리 가능)
    cap = cv2.VideoCapture(int(args.source) if args.source.isdigit() else args.source)
    if not cap.isOpened():
        print("Failed to open video source")
        return

    print("Press 'q' to quit")

    # 4. 프레임 루프 - 한 프레임씩 읽어서 객체 탐지 수행
    while True:
        # 한 프레임 읽기
        ret, frame = cap.read()
        if not ret:
            print("웹캠에서 프레임을 읽을 수 없습니다. 스트림을 종료합니다.")
            break

        # YOLO 추론 실행 (바운딩 박스, 클래스, 신뢰도 반환)
        results = model.predict(source=frame, conf=args.conf, iou=args.iou, imgsz=args.imgsz, device=device, verbose=False)

        # 탐지 결과를 프레임 위에 시각화
        r = results[0]
        boxes = r.boxes

        if boxes is not None:
            for box in boxes:
                # 바운딩 박스 좌표 (좌상단, 우하단)
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                # 클래스 ID 및 신뢰도
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                label = f"{CLASS_NAMES[cls_id]} {conf:.2f}"

                # 바운딩 박스 그리기
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                # 클래스명 + 신뢰도 텍스트 표시
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # 콘솔에 탐지 결과 출력
                print(f"[{CLASS_NAMES[cls_id]}] conf={conf:.2f} "
                      f"xyxy=({x1},{y1},{x2},{y2})")

        # 결과 프레임 화면에 출력
        cv2.imshow("YOLO Detection", frame)

        # 'q' 키 입력 시 종료
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # 5. 리소스 정리
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
