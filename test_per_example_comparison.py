#!/usr/bin/env python3
"""Test per-example comparison directly"""

from pathlib import Path
import sys
import csv
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.result_evaluator import ResultEvaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_log_csv(path):
    """Load per-example results from CSV"""
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

# Paths
baseline_path = Path('papers/codebases/TextAttack/baseline/log.csv')
reproduced_path = Path('papers/codebases/TextAttack/log.csv')
output_dir = Path('outputs/visualizations/textAttack')
output_dir.mkdir(parents=True, exist_ok=True)

logger.info(f"Loading baseline from: {baseline_path}")
logger.info(f"Loading reproduced from: {reproduced_path}")

baseline_log = load_log_csv(baseline_path)
reproduced_log = load_log_csv(reproduced_path)

logger.info(f"Baseline: {len(baseline_log)} examples")
logger.info(f"Reproduced: {len(reproduced_log)} examples")

# Compare
evaluator = ResultEvaluator()
diffs = evaluator.compare_per_example_results(baseline_log, reproduced_log)

logger.info(f"Found {len(diffs)} mismatches")

# Always generate the full comparison HTML (even with 0 diffs)
diff_html = evaluator.generate_per_example_diff_table(diffs)
baseline_table = evaluator.generate_per_example_table(baseline_log, "Baseline Results")
reproduced_table = evaluator.generate_per_example_table(reproduced_log, "Reproduced Results")

# Combine
combined_html = f"""
<html>
<head>
    <title>Per-Example Comparison</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h2 {{ color: #333; border-bottom: 2px solid #007bff; padding-bottom: 5px; }}
        table {{ margin: 20px 0; max-width: 100%; overflow-x: auto; }}
        .section {{ margin: 30px 0; }}
    </style>
</head>
<body>
    <h1>Per-Example Attack Results Comparison</h1>
    
    <div class="section">
        <h2>Differences Found: {len(diffs)}</h2>
        {diff_html}
    </div>
    
    <div class="section">
        {baseline_table}
    </div>
    
    <div class="section">
        {reproduced_table}
    </div>
</body>
</html>
"""

# Save
html_path = output_dir / 'per_example_diffs.html'
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(combined_html)

if diffs:
    csv_path = output_dir / 'per_example_diffs.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=diffs[0].keys())
        writer.writeheader()
        writer.writerows(diffs)
    
    logger.info(f"✓ Saved to {html_path} and {csv_path}")
    print(f"\n✅ SUCCESS: Found and saved {len(diffs)} per-example mismatches!")
else:
    logger.info(f"✓ Saved full comparison to {html_path}")
    print(f"\n✅ SUCCESS: No mismatches found. Full per-example tables saved!")
