import cv2
import numpy as np

# 수집할 매칭 데이터 리스트
pixel_points = []
robot_points = []

def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"\n[클릭 완료] 픽셀 좌표 (u, v): [{x}, {y}]")
        
        # 실제 로봇 물리 좌표 입력 받기
        try:
            real_x = float(input(" -> 이 지점의 실제 로봇 X 좌표 (mm 단위, 예: -150): "))
            real_y = float(input(" -> 이 지점의 실제 로봇 Y 좌표 (mm 단위, 예: 250): "))
            
            pixel_points.append([x, y])
            robot_points.append([real_x, real_y])
            print(f"현재 기록된 점 개수: {len(pixel_points)} / 최소 4개 필요")
            
            # 화면에 클릭한 지점 표시
            cv2.circle(img_copy, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(img_copy, f"P{len(pixel_points)}", (x + 10, y), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        except ValueError:
            print("❌ 올바른 숫자를 입력해주세요. 다시 클릭하세요.")

# 1. 카메라 영상 주입 (640x480 제약 사양 반영)
cap = cv2.VideoCapture(2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

ret, frame = cap.read()
if not ret:
    print("카메라를 열 수 없습니다. 이미지를 대체하여 테스트하거나 포트를 확인하세요.")
    exit()

img_copy = frame.copy()
cv2.namedWindow("Calibration Window")
cv2.setMouseCallback("Calibration Window", mouse_callback)

print("=== 호모그래피 캘리브레이션 시작 ===")
print("1. 카메라 화면에서 기준점을 좌상, 우상, 우하, 좌하 순으로 넓게 4개 이상 클릭하세요.")
print("2. 점을 찍을 때마다 터미널 창에 실측한 물리 거리(mm)를 입력하세요.")
print("3. 데이터 입력이 끝나면 화면 창에서 'q'를 눌러 행렬을 계산합니다.")

while True:
    cv2.imshow("Calibration Window", img_copy)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# 2. 호모그래피 행렬 계산 및 저장
if len(pixel_points) >= 4:
    pts_src = np.array(pixel_points, dtype=np.float32)
    pts_dst = np.array(robot_points, dtype=np.float32)
    
    # 3x3 변환 행렬 H 도출
    H, status = cv2.findHomography(pts_src, pts_dst)
    
    print("\n==============================================")
    print("🎯 캘리브레이션 완료! 생성된 3x3 호모그래피 행렬 (H):")
    print(H)
    print("==============================================")
    
    # 제어 노드가 다이렉트로 로드할 수 있게 numpy 파일로 깔끔하게 저장
    np.save("homography_matrix.npy", H)
    print("-> 'homography_matrix.npy' 파일로 저장이 완료되었습니다.")
else:
    print("❌ 최소 4개 이상의 지점을 매칭해야 행렬을 구할 수 있습니다.")