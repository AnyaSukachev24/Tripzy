# Results Organization

This document describes the folder structure for organizing test and evaluation results.

## Folder Structure

```
Tripzy/
├── evaluation-results/          # Automated evaluation runs
│   └── eval_YYYYMMDD_HHMMSS.json
├── test-results/                # Manual test runs
│   └── test_YYYYMMDD_HHMMSS.json
└── ui-tries-results/            # UI testing sessions
    └── ui_YYYYMMDD_HHMMSS.json
```

## Folder Purposes

### `evaluation-results/`
**Purpose**: Automated golden dataset evaluation runs  
**Created by**: `python tests/evaluations/run_golden_dataset_eval.py`  
**File format**: JSON with scores, pass/fail status, and detailed evaluation results  
**Naming**: `eval_YYYYMMDD_HHMMSS.json` (e.g., `eval_20260213_113000.json`)

**Example Usage**:
```bash
# Run evaluation (auto-saves with timestamp)
python tests/evaluations/run_golden_dataset_eval.py

# Run evaluation with custom output
python tests/evaluations/run_golden_dataset_eval.py --output custom_name.json
```

### `test-results/`
**Purpose**: Manual test runs and experiments  
**Created by**: Manual test scripts  
**File format**: JSON or text logs from test executions  
**Naming**: `test_YYYYMMDD_HHMMSS.json`

### `ui-tries-results/`
**Purpose**: UI testing sessions and browser interaction recordings  
**Created by**: Browser testing scripts or manual UI tests  
**File format**: JSON, screenshots, or video recordings  
**Naming**: `ui_YYYYMMDD_HHMMSS.json`

## Comparing Results Over Time

### View Specific Evaluation
```bash
python tests/evaluations/run_golden_dataset_eval.py --analyze evaluation-results/eval_20260213_113000.json
```

### Compare Two Runs
```python
import json

# Load two evaluation results
with open('evaluation-results/eval_20260213_100000.json') as f:
    baseline = json.load(f)
    
with open('evaluation-results/eval_20260213_120000.json') as f:
    current = json.load(f)

# Compare scores
print(f"Baseline: {baseline['average_score']:.2f}")
print(f"Current: {current['average_score']:.2f}")
print(f"Improvement: {(current['average_score'] - baseline['average_score']):.2f}")
```

## Best Practices

1. **Don't delete old results** - Keep them for historical tracking
2. **Tag important baselines** - Rename key evaluation runs (e.g., `eval_baseline_v1.json`)
3. **Document experiments** - Add a `notes.md` file describing significant changes
4. **Track in git** - Add important baseline files to git, exclude routine runs

## Git Ignore

The `.gitignore` file excludes routine results but allows you to manually add important baselines:

```gitignore
# Exclude routine evaluation results
evaluation-results/*
test-results/*
ui-tries-results/*

# But allow baseline files
!evaluation-results/baseline_*.json
!test-results/baseline_*.json
```

## Viewing Trends

Create a simple script to track scores over time:

```python
# scripts/track_scores.py
import json
import glob
from pathlib import Path

results_files = sorted(glob.glob('evaluation-results/eval_*.json'))

for file in results_files[-10:]:  # Last 10 runs
    with open(file) as f:
        data = json.load(f)
    timestamp = data['timestamp']
    score = data['average_score']
    pass_rate = data['pass_rate'] * 100
    print(f"{timestamp}: Score={score:.2f}, Pass Rate={pass_rate:.1f}%")
```
