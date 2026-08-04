import csv
from pathlib import Path

import matplotlib.image as mpimg
import pytest

from evaluation_node.core import CSV_FIELDS
from evaluation_node.visualization import FILES, generate_visualizations


@pytest.mark.parametrize('status,with_row,label', [
    ('completed', True, 'COMPLETED'), ('stopped', True, 'PARTIAL'),
    ('stopped', False, 'PARTIAL')])
def test_charts_for_complete_partial_and_empty(tmp_path, status, with_row, label):
    csv_path = tmp_path / 'results.csv'
    with csv_path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        if with_row:
            writer.writerow({'trial_id': 'T001', 'target_class': 'can',
                             'detected_class': 'can', 'detection_received': True,
                             'target_x_mm': 10, 'target_y_mm': 20,
                             'fk_x_mm': 12, 'fk_y_mm': 23,
                             'estimated_total_error_mm': 3.6,
                             'position_pass': True,
                             'failure_reasons': ''})
    state = {'status': status, 'planned_trials': 2, 'discarded_trials': 1}
    manifest = generate_visualizations(csv_path, state, 5, 4)
    assert manifest['run_label'] == label
    assert manifest['recorded_trials'] == int(with_row)
    for filename in FILES:
        image_path = tmp_path / 'charts' / filename
        assert image_path.stat().st_size > 0
        assert mpimg.imread(image_path).shape[:2] == (900, 1600)
    before = (tmp_path / 'charts' / FILES[0]).stat().st_mtime_ns
    assert generate_visualizations(csv_path, state, 5, 4) == manifest
    assert (tmp_path / 'charts' / FILES[0]).stat().st_mtime_ns == before


def test_multiple_failure_reasons_and_missing_fk(tmp_path):
    csv_path = tmp_path / 'results.csv'
    with csv_path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS); writer.writeheader()
        writer.writerow({'trial_id': 'T001', 'target_class': 'can',
                         'failure_reasons': 'a;b'})
    manifest = generate_visualizations(csv_path, {'status': 'stopped'}, 5, 4)
    assert manifest['recorded_trials'] == 1
