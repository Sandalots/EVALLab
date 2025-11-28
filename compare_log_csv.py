import csv
import sys
from typing import List, Dict

def load_log_csv(path: str) -> List[Dict]:
    """Load a TextAttack log.csv file into a list of dicts."""
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def compare_examples(baseline: List[Dict], reproduced: List[Dict]) -> List[Dict]:
    """Compare per-example results between two runs."""
    diffs = []
    for i, (base, repro) in enumerate(zip(baseline, reproduced)):
        diff = {'index': i}
        for key in ['original_text', 'perturbed_text', 'original_output', 'perturbed_output', 'result_type']:
            if base.get(key) != repro.get(key):
                diff[key + '_baseline'] = base.get(key)
                diff[key + '_reproduced'] = repro.get(key)
        if len(diff) > 1:
            diffs.append(diff)
    return diffs

def main(baseline_path, reproduced_path):
    baseline = load_log_csv(baseline_path)
    reproduced = load_log_csv(reproduced_path)
    if len(baseline) != len(reproduced):
        print(f"Warning: Different number of examples: baseline={len(baseline)}, reproduced={len(reproduced)}")
    diffs = compare_examples(baseline, reproduced)
    if not diffs:
        print("All per-example results match.")
    else:
        print(f"Found {len(diffs)} differing examples:")
        for d in diffs:
            print(f"\nExample {d['index']}:")
            for k, v in d.items():
                if k != 'index':
                    print(f"  {k}: {v}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_log_csv.py <baseline_log.csv> <reproduced_log.csv>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
