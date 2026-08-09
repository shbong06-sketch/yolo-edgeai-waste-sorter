"""ROS 없이 테스트 가능한 평가 회차 상태와 결과 파일 저장 로직."""

import csv
import json
import math
import os
from pathlib import Path
import statistics
import time


CSV_FIELDS = (
    'trial_id', 'target_class', 'sample_id', 'position_id',
    'target_x_mm', 'target_y_mm', 'detected_class', 'detection_received',
    'grasp_pose_captured', 'fk_x_mm', 'fk_y_mm', 'fk_z_mm',
    'estimated_total_error_mm', 'position_pass', 'operation_complete',
    'operation_complete_source', 'trial_completion_mode', 'failure_reasons')

POSITIVE_CONFIG_KEYS = (
    'visualization_dpi', 'position_tolerance_mm',
    'detection_timeout_sec', 'operation_timeout_sec')
NON_NEGATIVE_CONFIG_KEYS = ('position_warning_mm', 'cooldown_sec')


def _validated_float(config, key):
    try:
        value = float(config.get(key, 0))
    except (TypeError, ValueError):
        raise ValueError(f'{key} must be numeric') from None
    if not math.isfinite(value):
        raise ValueError(f'{key} must be finite')
    if key in POSITIVE_CONFIG_KEYS and value <= 0:
        raise ValueError(f'{key} must be positive')
    if key in NON_NEGATIVE_CONFIG_KEYS and value < 0:
        raise ValueError(f'{key} must be non-negative')
    return value


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2),
                         encoding='utf-8')
    os.replace(temporary, path)


class EvaluationRun:
    """수동 평가 회차 생명주기. 콜백은 관찰값과 실패 사유만 추가한다."""

    def __init__(self, config, run_dir, clock=time.monotonic):
        self.config = config
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.run_dir / 'results.csv'
        self.state_path = self.run_dir / 'run_state.json'
        self.summary_path = self.run_dir / 'summary.json'
        self.clock = clock
        # 회차 수를 미리 고정하지 않고, 설정된 평가 대상을 순환해서 안내한다.
        self.templates = self._make_templates(config)
        self.active = None
        self.rows = []
        self.started = 0
        self.discarded = []
        self.status = 'running'
        self.reason = ''
        self.cooldown_until = 0.0
        self.finalized = False
        self.visualization = {'status': 'not_started', 'generated_at': None,
                              'files': [], 'warnings': [], 'error': None}
        self._write_csv()
        self._write_summary()
        self.write_state()

    @staticmethod
    def validate_config(config):
        if config.get('control_mode') != 'keyboard':
            raise ValueError('control_mode must be keyboard')
        keys = [config.get(name) for name in ('start_key', 'end_key', 'quit_key')]
        if any(not isinstance(key, str) or len(key) != 1 for key in keys):
            raise ValueError('control keys must be one character')
        if len(set(key.lower() for key in keys)) != 3:
            raise ValueError('control keys must be distinct')
        values = {key: _validated_float(config, key)
                  for key in POSITIVE_CONFIG_KEYS + NON_NEGATIVE_CONFIG_KEYS}
        tolerance_mm = values['position_tolerance_mm']
        warning_mm = values['position_warning_mm']
        if warning_mm > tolerance_mm:
            raise ValueError('position_warning_mm must not exceed position_tolerance_mm')
        targets = config.get('target_classes')
        if not isinstance(targets, list) or not targets or any(not str(item).strip() for item in targets):
            raise ValueError('target_classes must contain at least one non-empty class')
        positions = config.get('positions')
        if not isinstance(positions, dict) or not positions:
            raise ValueError('positions must contain at least one target position')
        for position_id, point in positions.items():
            if not str(position_id).strip():
                raise ValueError('position IDs must be non-empty')
            try:
                x_mm = float(point['x_mm'])
                y_mm = float(point['y_mm'])
            except (TypeError, KeyError, ValueError):
                raise ValueError(f'position {position_id} must define numeric x_mm and y_mm') from None
            if not (math.isfinite(x_mm) and math.isfinite(y_mm)):
                raise ValueError(f'position {position_id} coordinates must be finite')

    @staticmethod
    def _make_templates(config):
        templates = []
        positions = config.get('positions', {})
        for target in config.get('target_classes', []):
            for position_id, point in positions.items():
                templates.append({
                    'target_class': target,
                    'position_id': str(position_id),
                    'target_x_mm': float(point['x_mm']),
                    'target_y_mm': float(point['y_mm'])})
        return templates

    def next_template(self):
        """평가 횟수를 제한하지 않고 다음 클래스/위치 안내를 반환한다."""
        if not self.templates:
            return None
        return self.templates[self.started % len(self.templates)]

    def preflight(self, publishers=None, valid_joints=False, gripper_open=False):
        failures = []
        if not self.config.get('configuration_confirmed', False):
            failures.append('configuration_not_confirmed')
        if self.config.get('evaluation_phase') == 'final' and not self.config.get('thresholds_locked', False):
            failures.append('thresholds_not_locked')
        publishers = publishers or {}
        for topic in ('/detection_results', '/follower/joint_states'):
            if not publishers.get(topic, False):
                failures.append(f'publisher_missing:{topic}')
        if not valid_joints:
            failures.append('valid_joint_state_missing')
        if not gripper_open:
            failures.append('gripper_not_open')
        return failures

    def start_trial(self, source='service', preflight_failures=()):
        if self.status != 'running' or self.active is not None:
            return False, 'trial already active or run is not running'
        if preflight_failures:
            return False, ';'.join(preflight_failures)
        if self.clock() < self.cooldown_until:
            return False, 'cooldown_active'
        template = self.next_template()
        if template is None:
            return False, 'no target templates configured'
        data = dict(template)
        # 같은 대상이 여러 번 돌아와도 실제 시작 순서로 sample ID를 만든다.
        data['sample_id'] = f"{data['target_class']}-{self.started + 1:03d}"
        data.update(trial_id=f'T{self.started + 1:03d}', source=source,
                    started_at=self.clock(), detected_class='',
                    detection_received=False, grasp_pose_captured=False,
                    outcome_recorded=False, fk=None, failures=[])
        self.active = data
        self.started += 1
        self.write_state()
        return True, data['trial_id']

    def add_failure(self, reason):
        if self.active is not None and reason and reason not in self.active['failures']:
            self.active['failures'].append(reason)

    def record_detection(self, class_id):
        if self.active is None:
            return
        self.active['detection_received'] = True
        self.active['detected_class'] = str(class_id)
        if str(class_id).strip().lower() != self.active['target_class'].strip().lower():
            self.add_failure('class_mismatch')

    def record_fk(self, xyz):
        if self.active is not None:
            self.active['fk'] = tuple(float(value) for value in xyz)
            self.active['grasp_pose_captured'] = True

    def record_outcome(self):
        if self.active is not None:
            self.active['outcome_recorded'] = True

    def watchdog(self):
        if self.active is None:
            return
        elapsed = self.clock() - self.active['started_at']
        if not self.active['detection_received'] and elapsed >= float(self.config.get('detection_timeout_sec', 5)):
            self.add_failure('detection_timeout')
        if elapsed >= float(self.config.get('operation_timeout_sec', 30)):
            self.add_failure('operation_timeout')

    def end_trial(self, source='service'):
        if self.active is None:
            return False, 'no active trial'
        trial = self.active
        if not trial['detection_received']:
            self.add_failure('manual_end_before_detection')
        if not trial['grasp_pose_captured'] or trial['fk'] is None:
            self.add_failure('manual_end_before_pose')
            self.add_failure('position_not_measured')
        error = None
        position_pass = False
        if trial['fk'] is not None:
            error = math.hypot(trial['fk'][0] - trial['target_x_mm'],
                               trial['fk'][1] - trial['target_y_mm'])
            position_pass = error <= float(self.config['position_tolerance_mm'])
            if not position_pass:
                self.add_failure('position_tolerance_exceeded')
        complete = (trial['detection_received'] and
                    trial['grasp_pose_captured'] and trial['fk'] is not None)
        prefix = 'keyboard_e' if source == 'keyboard' else source
        row = {key: '' for key in CSV_FIELDS}
        row.update({key: trial.get(key, '') for key in row})
        row.update(
            fk_x_mm='' if trial['fk'] is None else trial['fk'][0],
            fk_y_mm='' if trial['fk'] is None else trial['fk'][1],
            fk_z_mm='' if trial['fk'] is None else trial['fk'][2],
            estimated_total_error_mm='' if error is None else error,
            position_pass=position_pass, operation_complete=complete,
            operation_complete_source=prefix,
            trial_completion_mode=prefix,
            failure_reasons=';'.join(trial['failures']))
        self.rows.append(row)
        self.active = None
        self.cooldown_until = self.clock() + float(self.config.get('cooldown_sec', 0))
        self._write_csv()
        self._write_summary()
        self.write_state()
        return True, row

    def abort_trial(self, reason='operator_aborted'):
        if self.active is None:
            return False, 'no active trial'
        self.add_failure(reason)
        return self.end_trial('abort_service')

    def stop_run(self, reason, discard_active=True):
        if self.status != 'running':
            return False
        if discard_active and self.active is not None:
            self.discarded.append({'trial_id': self.active['trial_id'],
                                   'reason': reason})
            self.active = None
        self.status, self.reason = 'stopped', reason
        self.write_state()
        return True

    def _write_summary(self):
        measured = [float(row['estimated_total_error_mm']) for row in self.rows
                    if row['estimated_total_error_mm'] != '']
        detected = sum(bool(row['detection_received']) for row in self.rows)
        correct = sum(bool(row['detected_class']) and
                      row['detected_class'].strip().lower() ==
                      row['target_class'].strip().lower() for row in self.rows)
        passed = sum(bool(row['position_pass']) for row in self.rows)
        total = len(self.rows)
        by_class = {}
        for target in sorted({row['target_class'] for row in self.rows}):
            group = [row for row in self.rows if row['target_class'] == target]
            valid = [float(row['estimated_total_error_mm']) for row in group
                     if row['estimated_total_error_mm'] != '']
            by_class[target] = {
                'trials': len(group),
                'detection_rate': sum(bool(row['detection_received']) for row in group) / len(group),
                'class_accuracy': sum(bool(row['detected_class']) and row['detected_class'].strip().lower() == target.strip().lower() for row in group) / len(group),
                'mean_fk_error_mm': sum(valid) / len(valid) if valid else None,
                'valid_fk_measurements': len(valid),
            }
        atomic_json(self.summary_path, {
            'status': self.status,
            'recorded_trials': total,
            'detection_success_rate': detected / total if total else None,
            'class_accuracy': correct / total if total else None,
            'position_pass_rate': passed / total if total else None,
            'mean_fk_error_mm': sum(measured) / len(measured) if measured else None,
            'valid_fk_measurements': len(measured),
            'repeatability_error_stddev_mm': statistics.pstdev(measured) if len(measured) > 1 else None,
            'class_performance': by_class,
        })

    def _write_csv(self):
        temporary = self.csv_path.with_suffix('.csv.tmp')
        with temporary.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)
        os.replace(temporary, self.csv_path)

    def state(self):
        return {'status': self.status, 'reason': self.reason,
                'planned_trials': None, 'started_trials': self.started,
                'recorded_trials': len(self.rows),
                'discarded_trials': len(self.discarded),
                'discarded_trial_ids': self.discarded,
                'active_trial_id': self.active['trial_id'] if self.active else None,
                'keyboard': {'available': bool(self.config.get('keyboard_available', False)),
                             'start_key': self.config['start_key'],
                             'end_key': self.config['end_key'],
                             'quit_key': self.config['quit_key']},
                'visualization': self.visualization}

    def write_state(self):
        atomic_json(self.state_path, self.state())
