import csv

from evaluation_node.core import EvaluationRun


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


def config():
    return {'control_mode': 'keyboard', 'start_key': 's', 'end_key': 'e',
            'quit_key': 'q', 'visualization_dpi': 150,
            'target_classes': ['can'],
            'positions': {'P1': {'x_mm': 100, 'y_mm': 20}},
            'position_tolerance_mm': 5,
            'detection_timeout_sec': 2, 'operation_timeout_sec': 4,
            'cooldown_sec': 0}


def test_start_duplicate_and_empty_end(tmp_path):
    run = EvaluationRun(config(), tmp_path)
    assert run.end_trial()[0] is False
    assert run.start_trial()[0] is True
    assert run.start_trial()[0] is False
    assert len(list(csv.DictReader(run.csv_path.open()))) == 0


def test_preflight_does_not_require_unused_homography(tmp_path):
    data = config()
    data.update(configuration_confirmed=True, thresholds_locked=True,
                evaluation_phase='final')
    run = EvaluationRun(data, tmp_path)
    failures = run.preflight(
        {'/detection_results': True, '/follower/joint_states': True},
        valid_joints=True, gripper_open=True)
    assert failures == []


def test_success_does_not_auto_complete(tmp_path):
    run = EvaluationRun(config(), tmp_path)
    run.start_trial()
    run.record_detection('can')
    run.record_fk((103, 24, 20))
    success, row = run.end_trial('keyboard')
    assert success and row['operation_complete']
    assert row['operation_complete_source'] == 'keyboard_e'
    assert row['position_pass'] is True
    assert row['failure_reasons'] == ''
    assert run.status == 'running'


def test_s_and_e_define_unlimited_trial_count(tmp_path):
    run = EvaluationRun(config(), tmp_path)
    for number in range(3):
        assert run.start_trial()[0]
        assert run.active['trial_id'] == f'T{number + 1:03d}'
        assert run.end_trial()[0]
    assert run.started == 3
    assert len(run.rows) == 3
    assert run.state()['planned_trials'] is None


def test_missing_detection_pose_and_timeout_waits_for_end(tmp_path):
    clock = Clock()
    run = EvaluationRun(config(), tmp_path, clock)
    run.start_trial()
    clock.value = 5
    run.watchdog()
    assert run.active is not None and not run.rows
    _, row = run.end_trial('keyboard')
    reasons = row['failure_reasons'].split(';')
    assert {'detection_timeout', 'operation_timeout',
            'manual_end_before_detection', 'manual_end_before_pose'} <= set(reasons)


def test_class_mismatch_and_tolerance(tmp_path):
    run = EvaluationRun(config(), tmp_path)
    run.start_trial(); run.record_detection('plastic'); run.record_fk((200, 20, 0))
    _, row = run.end_trial()
    assert 'class_mismatch' in row['failure_reasons']
    assert 'position_tolerance_exceeded' in row['failure_reasons']


def test_quit_discards_active_without_csv_row(tmp_path):
    run = EvaluationRun(config(), tmp_path)
    run.start_trial()
    assert run.stop_run('keyboard_quit', True)
    assert not run.rows
    assert run.discarded == [{'trial_id': 'T001', 'reason': 'keyboard_quit'}]


def test_abort_records_failure_and_continues(tmp_path):
    run = EvaluationRun(config(), tmp_path)
    run.start_trial()
    success, row = run.abort_trial()
    assert success and 'operator_aborted' in row['failure_reasons']
    assert run.status == 'running'
