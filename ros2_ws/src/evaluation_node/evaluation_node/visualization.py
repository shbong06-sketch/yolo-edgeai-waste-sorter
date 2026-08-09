"""화면 없이 원자적으로 평가 그래프를 생성한다."""

import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


FILES = ('overall_summary.png', 'class_performance.png',
         'trial_position_error.png', 'target_vs_fk.png',
         'failure_reasons.png')


def _number(row, key):
    try:
        value = float(row.get(key, ''))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _truth(value):
    return str(value).lower() in ('1', 'true', 'yes')


def _font():
    names = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in ('NanumGothic', 'Noto Sans CJK KR'):
        if candidate in names:
            plt.rcParams['font.family'] = candidate
            return candidate, []
    return 'DejaVu Sans', ['한국어 글꼴을 찾을 수 없어 영어 라벨을 사용했다.']


def _save(fig, path, dpi):
    width, height = 1600 / dpi, 900 / dpi
    fig.set_size_inches(width, height)
    temporary = path.with_name(path.stem + '.tmp.png')
    fig.savefig(temporary, dpi=dpi, bbox_inches=None)
    plt.close(fig)
    os.replace(temporary, path)


def generate_visualizations(csv_path, run_state, tolerance_mm,
                            warning_mm, dpi=150, enabled=True):
    """필수 그래프 5개를 한 번 생성하고 manifest를 반환한다."""
    charts = Path(csv_path).parent / 'charts'
    manifest_path = charts / 'visualization_manifest.json'
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding='utf-8'))
    charts.mkdir(parents=True, exist_ok=True)
    if not enabled:
        return {'status': 'disabled', 'files': []}
    _, warnings = _font()
    with Path(csv_path).open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    completed = run_state.get('status') == 'completed'
    badge = 'COMPLETED' if completed else 'PARTIAL'
    errors = [_number(row, 'estimated_total_error_mm') for row in rows]
    valid_errors = [value for value in errors if value is not None]
    detections = sum(_truth(row.get('detection_received')) for row in rows)
    correct = sum(row.get('detected_class', '').strip().lower() ==
                  row.get('target_class', '').strip().lower() and
                  bool(row.get('detected_class')) for row in rows)
    passes = sum(_truth(row.get('position_pass')) for row in rows)
    denominator = len(rows)
    rate = lambda count: 100.0 * count / denominator if denominator else 0.0

    fig, ax = plt.subplots()
    ax.axis('off')
    # 동적 평가에서는 계획 회차가 없으므로 실제 s/e로 저장된 수만 표시한다.
    planned = run_state.get('planned_trials')
    recorded_label = (f'Recorded trials: {denominator}' if planned is None else
                      f'Recorded / planned: {denominator} / {planned}')
    metrics = [recorded_label,
               f'Discarded: {run_state.get("discarded_trials", 0)}',
               f'Detection rate: {rate(detections):.1f}%',
               f'Class accuracy: {rate(correct):.1f}%',
               f'Position pass rate: {rate(passes):.1f}%',
               'Mean FK error: ' + (f'{np.mean(valid_errors):.2f} mm' if valid_errors else 'N/A'),
               'P95 FK error: ' + (f'{np.percentile(valid_errors, 95):.2f} mm' if valid_errors else 'N/A'),
               f'Run status: {badge}']
    ax.text(.5, .9, 'SO-ARM 101 Evaluation', ha='center', fontsize=28, weight='bold')
    ax.text(.5, .78, '\n'.join(metrics), ha='center', va='top', fontsize=20, linespacing=1.5)
    _save(fig, charts / FILES[0], dpi)

    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get('target_class', 'unknown')].append(row)
    labels = list(grouped) or ['No data']
    x = np.arange(len(labels))
    detection_rates, accuracy_rates, mean_errors, counts = [], [], [], []
    for label in labels:
        group = grouped.get(label, [])
        count = len(group)
        values = [_number(row, 'estimated_total_error_mm') for row in group]
        values = [value for value in values if value is not None]
        counts.append(len(values))
        detection_rates.append(100 * sum(_truth(row.get('detection_received')) for row in group) / count if count else 0)
        accuracy_rates.append(100 * sum(row.get('detected_class', '').strip().lower() == label.strip().lower() for row in group) / count if count else 0)
        mean_errors.append(float(np.mean(values)) if values else 0)
    fig, ax = plt.subplots()
    width = .25
    ax.bar(x - width, detection_rates, width, label='Detection %')
    ax.bar(x, accuracy_rates, width, label='Class accuracy %')
    ax.bar(x + width, mean_errors, width, label='Mean FK error (mm)')
    ax.set_xticks(x, [f'{label}\n(n={count})' for label, count in zip(labels, counts)])
    ax.set_title(f'Class performance — {badge}'); ax.legend(); ax.grid(axis='y', alpha=.2)
    _save(fig, charts / FILES[1], dpi)

    fig, ax = plt.subplots()
    valid_x = [i + 1 for i, value in enumerate(errors) if value is not None]
    ax.plot(valid_x, valid_errors, 'o-', label='FK error')
    missing = [i + 1 for i, value in enumerate(errors) if value is None]
    if missing:
        ax.scatter(missing, [0] * len(missing), marker='x', color='gray', label='FK missing')
    ax.axhline(tolerance_mm, color='red', linestyle='--', label='Tolerance')
    ax.axhline(warning_mm, color='orange', linestyle=':', label='Warning')
    ax.set_title(f'Trial position error — {badge}'); ax.set_xlabel('Recorded trial'); ax.set_ylabel('Error (mm)'); ax.legend(); ax.grid(alpha=.2)
    _save(fig, charts / FILES[2], dpi)

    fig, ax = plt.subplots()
    excluded = 0
    for row in rows:
        tx, ty, fx, fy = (_number(row, key) for key in ('target_x_mm', 'target_y_mm', 'fk_x_mm', 'fk_y_mm'))
        if None in (tx, ty, fx, fy):
            excluded += 1; continue
        ax.plot([tx, fx], [ty, fy], color='gray', alpha=.5)
        ax.scatter(tx, ty, color='blue'); ax.scatter(fx, fy, color='red')
    ax.set_aspect('equal', adjustable='datalim'); ax.grid(alpha=.2)
    ax.set_title(f'Target vs FK — {badge} (FK missing excluded: {excluded})')
    ax.set_xlabel('X (mm)'); ax.set_ylabel('Y (mm)')
    _save(fig, charts / FILES[3], dpi)

    reasons = Counter(reason for row in rows for reason in row.get('failure_reasons', '').split(';') if reason)
    fig, ax = plt.subplots()
    if reasons:
        ax.barh(list(reasons), list(reasons.values())); ax.set_xlabel('Occurrences')
    else:
        ax.axis('off'); ax.text(.5, .5, 'No failures', ha='center', va='center', fontsize=28)
    ax.set_title(f'Failure reasons — {badge}')
    _save(fig, charts / FILES[4], dpi)

    manifest = {'status': 'complete', 'run_label': badge,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'recorded_trials': denominator, 'files': list(FILES),
                'warnings': warnings, 'image_size': [1600, 900], 'dpi': dpi}
    temporary = manifest_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    os.replace(temporary, manifest_path)
    return manifest
