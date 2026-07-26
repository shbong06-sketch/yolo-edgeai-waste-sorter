"""
추론 엔진 모듈.

파일 확장자에 따라 적절한 추론 엔진을 선택하여 사용:
- .pt  -> YoloEngine  (ultralytics YOLO 사용)
- .onnx -> OnnxEngine (onnxruntime 직접 사용)

공통 인터페이스:
    engine = EngineFactory.create(model_path, device, imgsz)
    results = engine.predict(frame, conf, iou)
    # results: list of dict
    #   [{'class_name': str, 'confidence': float,
    #     'bbox': [x1, y1, x2, y2]}, ...]
"""

import os
import sys

import numpy as np


def _find_cuda_libs():
    """
    onnxruntime-gpu의 CUDA 라이브러리를 pip 패키지에서 찾아 ctypes로 로드.

    LD_LIBRARY_PATH에 nvidia 패키지 경로가 포함되어 있지 않은 환경에서
    onnxruntime이 CUDAExecutionProvider를 로드할 수 있도록 보장한다.

    onnxruntime-gpu는 pip으로 설치된 nvidia-cu13, nvidia-cudnn 패키지에
    libcudart.so.13 등 CUDA 라이브러리를 포함하지만, 동적 링커는
    LD_LIBRARY_PATH를 통해 이를 찾으므로, Python 프로세스 시작 시
    ctypes로 미리 로드하여 해결한다.
    """
    import ctypes
    import sysconfig

    # nvidia CUDA 라이브러리가 포함된 site-packages 디렉토리를 여러 경로에서 탐색
    # 가상환경(.venv, conda) 또는 시스템 전체 설치 모두 호환
    candidates = []

    # 1. sysconfig로 시스템/환경별 site-packages 경로
    #    (venv, conda, 시스템 설치 모두 커버)
    #    - venv: <venv>/lib/pythonX.Y/site-packages
    #    - conda: <conda_env>/lib/pythonX.Y/site-packages
    #    - 시스템 설치: /usr/lib/python3/dist-packages 또는
    #      /usr/local/lib/pythonX.Y/dist-packages
    for key in ('purelib', 'platlib'):
        sp = sysconfig.get_path(key)
        if sp and sp not in candidates:
            candidates.append(sp)

    # 2. sys.prefix 기준 site-packages (venv, conda에서
    #    prefix가 환경 루트를 가리킴)
    prefix_sp = os.path.join(
        sys.prefix, 'lib',
        f'python{sys.version_info.major}.{sys.version_info.minor}',
        'site-packages',
    )
    if prefix_sp not in candidates:
        candidates.append(prefix_sp)

    # 3. 현재 파일(__file__) 기준으로 상위 디렉토리를 순회하며 탐색
    #    colcon 빌드 시 install/ 디렉토리에 패키지가 설치되는 경우 대비
    base = os.path.dirname(os.path.abspath(__file__))
    for depth in range(10):
        candidate = os.path.join(
            base, *['..'] * depth, 'lib',
            f'python{sys.version_info.major}.{sys.version_info.minor}',
            'site-packages',
        )
        candidate = os.path.normpath(candidate)
        if candidate not in candidates:
            candidates.append(candidate)

    # nvidia/cu13/lib 디렉토리가 존재하는 첫 번째 site-packages를 사용
    site_packages = None
    for sp in candidates:
        nvidia_lib = os.path.join(sp, 'nvidia', 'cu13', 'lib')
        if os.path.isdir(sp) and os.path.isdir(nvidia_lib):
            site_packages = sp
            break

    if site_packages is None:
        return

    cuda_dirs = [
        os.path.join(site_packages, 'nvidia', 'cu13', 'lib'),
        os.path.join(site_packages, 'nvidia', 'cudnn', 'lib'),
    ]
    cuda_libs = [
        'libcudart.so.13', 'libcublas.so.13', 'libcublasLt.so.13',
        'libcurand.so.10', 'libcufft.so.12', 'libnvrtc.so.13',
        'libcudnn.so.9', 'libcudnn_ops.so.9', 'libcudnn_cnn.so.9',
        'libcudnn_adv.so.9', 'libcudnn_graph.so.9',
        'libcudnn_heuristic.so.9',
        'libcudnn_engines_precompiled.so.9',
        'libcudnn_engines_runtime_compiled.so.9',
    ]
    ld_paths = []
    for d in cuda_dirs:
        if not os.path.isdir(d):
            continue
        ld_paths.append(d)
        for lib in cuda_libs:
            p = os.path.join(d, lib)
            if os.path.isfile(p):
                ctypes.CDLL(p)

    if ld_paths:
        os.environ['LD_LIBRARY_PATH'] = (
            ':'.join(ld_paths)
            + ':'
            + os.environ.get('LD_LIBRARY_PATH', '')
        )


class YoloEngine:
    """
    ultralytics YOLO를 사용하는 추론 엔진 (.pt 모델 전용).

    .pt 파일 추론에 사용한다.
    """

    def __init__(self, model_path: str, device: str = 'cuda', imgsz: int = 640):
        """Initialize YoloEngine."""
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.device = device
        self.imgsz = imgsz

    def predict(
        self, frame: np.ndarray, conf: float = 0.5, iou: float = 0.45
    ) -> list:
        """
        YOLO 추론 실행.

        Args:
            frame: BGR 이미지 (numpy array, HWC)
            conf: 신뢰도 임계값
            iou: NMS IoU 임계값

        Returns
        -------
        [{'class_name': str, 'confidence': float,
          'bbox': [x1, y1, x2, y2]}, ...]

        """
        results = self.model.predict(
            source=frame, conf=conf, iou=iou,
            device=self.device, verbose=False,
        )
        detections = []
        if not results or len(results) == 0:
            return detections

        result = results[0]
        if result.boxes is None or len(result.boxes) == 0:
            return detections

        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0])
            conf_val = float(box.conf[0])
            class_name = result.names[cls_id]
            detections.append({
                'class_name': class_name,
                'confidence': conf_val,
                'bbox': [x1, y1, x2, y2],
            })
        return detections


class OnnxEngine:
    """
    onnxruntime을 직접 사용하는 추론 엔진 (.onnx 모델 전용).

    ultralytics를 거치지 않고 onnxruntime InferenceSession을 직접 구성하여:
    - IO Binding으로 GPU 메모리 복사 최소화
    - CUDAExecutionProvider / TensorRTExecutionProvider 전환 가능
    - ultralytics, torch 의존성 불필요

    전처리/후처리(리사이즈, 정규화, NMS)를 직접 수행한다.
    """

    def __init__(self, model_path: str, device: str = 'cuda', imgsz: int = 640):
        """Initialize OnnxEngine."""
        self.imgsz = imgsz
        self.model_path = model_path

        # CUDA 라이브러리 프리로드 (onnxruntime import 전에 실행되어야 함)
        # LD_LIBRARY_PATH에 nvidia 패키지 경로가 없으면 onnxruntime이
        # CUDAExecutionProvider를 로드할 수 없으므로, ctypes로 미리 로드
        _find_cuda_libs()

        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError(
                'onnxruntime이 설치되지 않았습니다. '
                'pip install onnxruntime-gpu 또는 '
                'pip install onnxruntime 으로 설치하세요.'
            ) from None

        # 프로바이더 설정: GPU 사용 가능 시 CUDA, 불가 시 CPU 폴백
        if device == 'cuda':
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        else:
            providers = ['CPUExecutionProvider']

        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

        # 실제 사용된 프로바이더 확인
        actual_provider = self.session.get_providers()[0]
        self._logger_info(
            f'ONNX 모델 로드: {model_path} (provider={actual_provider})'
        )

        # 모델 출력 shapes 확인 (NMS 후처리에 사용)
        self.output_names = [o.name for o in self.session.get_outputs()]

    def _logger_info(self, msg: str):
        """ROS2 노드 외부 호출 시 대비 (현재는 no-op)."""
        pass

    def predict(
        self, frame: np.ndarray, conf: float = 0.5, iou: float = 0.45
    ) -> list:
        """
        ONNX 모델 추론 실행.

        파이프라인:
        1. 전처리: BGR -> RGB, 리사이즈, 정규화, CHW 변환, 배치 차원 추가
        2. 추론: onnxruntime 세션 실행
        3. 후처리: 출력 파싱, NMS 적용, 좌표 스케일링

        Args:
            frame: BGR 이미지 (numpy array, HWC, uint8)
            conf: 신뢰도 임계값
            iou: NMS IoU 임계값

        Returns
        -------
        [{'class_name': str, 'confidence': float,
          'bbox': [x1, y1, x2, y2]}, ...]

        """
        # 1. 전처리
        input_tensor = self._preprocess(frame)

        # 2. 추론
        outputs = self.session.run(None, {self.input_name: input_tensor})

        # 3. 후처리 (NMS 포함)
        detections = self._postprocess(outputs, frame.shape, conf, iou)
        return detections

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        이미지 전처리.

        ultralytics YOLO의 preprocessing과 동일한 방식:
        - BGR -> RGB 변환
        - 리사이즈 (letterbox, padding 포함)
        - 0~255 -> 0.0~1.0 정규화
        - HWC -> CHW 변환
        - 배치 차원 추가 (NCHW)
        """
        # BGR -> RGB
        img = frame[:, :, ::-1].copy()

        # 리사이즈 (letterbox: 검정 패딩 포함)
        img, ratio, (dw, dh) = self._letterbox(
            img, (self.imgsz, self.imgsz)
        )

        # 정규화 및 CHW 변환
        img = img.astype(np.float32) / 255.0
        img = img.transpose(2, 0, 1)  # HWC -> CHW
        img = np.expand_dims(img, 0)   # 배치 차원 추가

        # 스케일링 정보를 후처리에 전달하기 위해 인스턴스 변수로 저장
        self._ratio = ratio
        self._dw = dw
        self._dh = dh

        return img

    def _letterbox(
        self, img: np.ndarray, new_shape: tuple
    ) -> tuple:
        """
        Letterbox 리사이즈 (검정 패딩으로 정사각형 유지).

        ultralytics의 letterbox와 동일한 로직.
        원본 이미지의 비율을 유지하면서 new_shape 크기로 리사이즈.

        Returns
        -------
        (resized_img, ratio, (pad_w, pad_h))

        """
        h, w = img.shape[:2]
        r = min(new_shape[0] / h, new_shape[1] / w)
        new_unpad = (int(round(w * r)), int(round(h * r)))
        dw = (new_shape[1] - new_unpad[0]) / 2
        dh = (new_shape[0] - new_unpad[1]) / 2

        if (w, h) != new_unpad:
            img = cv2_resize(img, new_unpad, interpolation=2)  # INTER_LINEAR

        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2_copyMakeBorder(
            img, top, bottom, left, right,
            borderType=0, value=(114, 114, 114),
        )
        return img, r, (dw, dh)

    def _postprocess(
        self, outputs: list, orig_shape: tuple,
        conf_thresh: float, iou_thresh: float,
    ) -> list:
        """
        모델 출력 후처리.

        YOLOv11 출력 형식: [1, 84, 8400] (transposed)
        - 84 = 4 (bbox xyxy) + 80 (class scores, COCO 기준)
        - 프로젝트 클래스 수에 맞게 조정 필요
          (현재 3클래스이지만 모델 출력에 따라 달라짐)

        NMS(Non-Maximum Suppression)를 적용하여
        중복 바운딩박스 제거.
        """
        # 출력 포맷: [1, 4+num_classes, num_detections]
        pred = outputs[0]
        if pred.ndim == 3:
            pred = pred[0]  # 배치 차원 제거 -> [4+C, N]

        pred = pred.T  # -> [N, 4+C]

        # bbox: xywh -> xyxy 변환
        cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2

        # 클래스 신뢰도
        class_scores = pred[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = np.max(class_scores, axis=1)

        # 신뢰도 필터
        mask = confidences >= conf_thresh
        x1, y1, x2, y2 = x1[mask], y1[mask], x2[mask], y2[mask]
        class_ids = class_ids[mask]
        confidences = confidences[mask]

        if len(confidences) == 0:
            return []

        # NMS 적용
        boxes_np = np.column_stack([x1, y1, x2, y2]).astype(np.float32)
        indices = cv2_dnnNMSBoxes(
            boxes_np, confidences.tolist(), conf_thresh, iou_thresh
        )

        # 결과 생성 (원본 좌표로 스케일링)
        orig_h, orig_w = orig_shape[:2]
        detections = []
        for i in indices:
            i = int(i)
            bx1, by1, bx2, by2 = x1[i], y1[i], x2[i], y2[i]

            # letterbox 패딩 및 리사이즈 되돌리기
            bx1 = (bx1 - self._dw) / self._ratio
            by1 = (by1 - self._dh) / self._ratio
            bx2 = (bx2 - self._dw) / self._ratio
            by2 = (by2 - self._dh) / self._ratio

            # 원본 이미지 범위로 클리핑
            bx1 = max(0, min(bx1, orig_w))
            by1 = max(0, min(by1, orig_h))
            bx2 = max(0, min(bx2, orig_w))
            by2 = max(0, min(by2, orig_h))

            detections.append({
                'class_name': str(class_ids[i]),
                'confidence': float(confidences[i]),
                'bbox': [
                    float(bx1), float(by1),
                    float(bx2), float(by2),
                ],
            })
        return detections


# OpenCV 함수를 캐시하여 매번 import해야 하는 일을 방지
_cv2 = None


def _get_cv2():
    """Lazy Loading으로 불필요한 import 방지."""
    global _cv2
    if _cv2 is None:
        import cv2
        _cv2 = cv2
    return _cv2


def cv2_resize(img, dsize, interpolation):
    """Wrap OpenCV resize."""
    return _get_cv2().resize(img, dsize, interpolation=interpolation)


def cv2_copyMakeBorder(src, top, bottom, left, right, borderType, value):
    """Wrap OpenCV copyMakeBorder."""
    return _get_cv2().copyMakeBorder(
        src, top, bottom, left, right,
        borderType=borderType, value=value,
    )


def cv2_dnnNMSBoxes(bboxes, scores, score_threshold, nms_threshold):
    """Wrap OpenCV DNN NMSBoxes."""
    return _get_cv2().dnn.NMSBoxes(
        bboxes, scores, score_threshold, nms_threshold
    )


class EngineFactory:
    """
    파일 확장자에 따라 적절한 추론 엔진을 생성하는 팩토리.

    사용 예:
        engine = EngineFactory.create('best.pt', device='cuda')
        engine = EngineFactory.create('best.onnx', device='cuda')
    """

    @staticmethod
    def create(model_path: str, device: str = 'cuda', imgsz: int = 640):
        """
        추론 엔진 생성.

        Args:
            model_path: 모델 파일 경로 (.pt 또는 .onnx)
            device: 추론 디바이스 ('cuda' 또는 'cpu')
            imgsz: 입력 이미지 크기

        Returns
        -------
        YoloEngine 또는 OnnxEngine 인스턴스

        """
        ext = os.path.splitext(model_path)[1].lower()
        if ext == '.pt':
            return YoloEngine(model_path, device, imgsz)
        elif ext == '.onnx':
            return OnnxEngine(model_path, device, imgsz)
        else:
            raise ValueError(
                f'지원하지 않는 모델 형식: {ext} '
                f'(.pt 또는 .onnx 파일을 사용하세요)'
            )
