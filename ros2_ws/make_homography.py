#!/usr/bin/env python3
import cv2
import numpy as np
import os

def main():
    # 2번 카메라 열기
    cap = cv2.VideoCapture(2)
    
    if not cap.isOpened():
        print(" 에러: 2번 카메라를 열 수 없습니다. 인덱스를 확인하세요.")
        return

    print("====================================================")
    print(" SO-ARM 101 맞춤형 호모그래피 캘리브레이션 스크립트")
    print("====================================================")
    print(" [방법] 화면에서 기준점 4개를 신중하게 클릭하세요.")
    print(" 점을 찍을 때마다 터미널창에 해당 점의 '로봇 기준 실제 X, Y(mm)'를 입력합니다.")
    print(" 완료되면 지정된 경로에 .npy 장부가 저장됩니다.")
    print("====================================================")

    image_points = []
    
    # 마우스 클릭 콜백 함수
    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(image_points) < 4:
                image_points.append([x, y])
                print(f" [{len(image_points)}번 점 지정] 픽셀 좌표: (u={x}, v={y})")
                # 클릭한 자리에 시각적으로 빨간 점 표시
                cv2.circle(img_display, (x, y), 5, (0, 0, 250), -1)
                cv2.putText(img_display, f"P{len(image_points)}", (x + 10, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 250), 1)
                cv2.imshow("Calibration Window", img_display)

    # 최초 프레임 캡처 후 창 띄우기
    ret, frame = cap.read()
    if not ret:
        print(" 카메라 프레임을 읽어올 수 없습니다.")
        return
        
    img_display = frame.copy()
    cv2.namedWindow("Calibration Window")
    cv2.setMouseCallback("Calibration Window", mouse_callback)

    # 4개의 점을 다 찍을 때까지 화면 유지
    while len(image_points) < 4:
        cv2.imshow("Calibration Window", img_display)
        # q를 누르면 중단
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("⏹ 캘리브레이션이 사용자에 의해 중단되었습니다.")
            cap.release()
            cv2.destroyAllWindows()
            return

    print("\n 4개의 픽셀 점 채집 완료! 이제 실물 로봇 기준 거리(mm)를 입력하세요.")
    cv2.destroyAllWindows()
    cap.release()

    # 실제 로봇 물리 좌표 수집
    robot_points = []
    for i in range(4):
        print(f"\n--- [P{i+1}번 점] 픽셀 위치: {image_points[i]} ---")
        print(" 로봇 기저(바닥 회전축 정중앙) 기준 mm 단위로 입력하세요.")
        rx = float(input(f"▶ 로봇 기준 실제 X 거리 입력 (mm): "))
        ry = float(input(f"▶ 로봇 기준 실제 Y 거리 입력 (mm): "))
        robot_points.append([rx, ry])

    # 수학 연산을 위해 numpy 배열로 변환
    pts_src = np.array(image_points, dtype=float)
    pts_dst = np.array(robot_points, dtype=float)

    # 호모그래피 행렬 계산 (OpenCV 마법 엔진)
    H, status = cv2.findHomography(pts_src, pts_dst)

    # 결과 저장 경로 지정 (성현님 프로젝트 AI 폴더 경로)
    save_dir = "/home/gt/yolo-edgeai-waste-sorter/ros2_ws"
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, "homography_matrix.npy")

    # 파일 저장
    np.save(save_path, H)
    print("\n====================================================")
    print(f" 호모그래피 행렬 생성 성공 및 파일 저장 완료!")
    print(f" 저장 경로: {save_path}")
    print("====================================================")
    print(H)

if __name__ == "__main__":
    main()