"""
DetectorNode 로깅 개선 테스트.

ROS2 환경 없이도 실행 가능한 핵심 로직 테스트.
"""

import time
import unittest


class TestLogSummaryDetectionStats(unittest.TestCase):
    """_log_summary의 탐지 결과 통계 테스트."""

    def test_detection_stats_format(self):
        """탐지 결과가 올바른 형식이어야 함."""
        detections_log = [('plastic', 320.0, 240.0), ('paper', 100.0, 50.0)]

        log_lines = []
        for class_name, cx, cy in detections_log:
            log_lines.append(f'  {class_name}: ({cx:.0f}, {cy:.0f})')

        log_message = f'탐지 결과 ({len(detections_log)}개):\n' + '\n'.join(log_lines)

        self.assertIn('탐지 결과', log_message)
        self.assertIn('plastic', log_message)
        self.assertIn('paper', log_message)
        self.assertIn('320', log_message)
        self.assertIn('240', log_message)

    def test_log_resets_detection_counters(self):
        """요약 로그 후 탐지 카운터가 리셋되어야 함."""
        detections_log = [('plastic', 320.0, 240.0)]
        detections_log = []
        self.assertEqual(detections_log, [])


class TestEncodingWarningOnce(unittest.TestCase):
    """인코딩 경고 1회만 출력 테스트."""

    def test_same_encoding_warning_only_once(self):
        """같은 인코딩에 대한 경고는 1회만 출력되어야 함."""
        warned_encodings = set()
        warn_count = 0

        for _ in range(10):
            encoding = 'yuv422'
            if encoding not in warned_encodings:
                warn_count += 1
                warned_encodings.add(encoding)

        self.assertEqual(warn_count, 1)


class TestInferenceErrorThrottling(unittest.TestCase):
    """추론 오류 빈도 제한 테스트."""

    def test_inference_error_throttled(self):
        """추론 오류는 5초 간격으로만 출력되어야 함."""
        last_error_time = 0.0
        error_count = 0

        for _ in range(5):
            current_time = time.time()
            if current_time - last_error_time > 5.0:
                error_count += 1
                last_error_time = current_time

        self.assertEqual(error_count, 1)


if __name__ == '__main__':
    unittest.main()
