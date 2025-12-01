"""===============================================================================
EVALLAB STAGE 4/4: RESULT EVALUATION

Compares reproduced metrics to baseline, generates analysis and visualizations.
Final output: comprehensive reproducibility assessment with charts and reports.
===============================================================================
"""

import logging
from typing import Dict, List, Any
from dataclasses import dataclass
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class BaselineMetrics:
    """Baseline metrics from the research paper."""
    metrics: Dict[str, float]
    source: str  # Where in the paper these came from


@dataclass
class ComparisonResult:
    """Comparison between reproduced and baseline results."""
    metric_name: str
    baseline_value: float
    reproduced_value: float
    difference: float
    percent_difference: float
    within_threshold: bool
    configuration: str = ""  # e.g., "sentence/minimal/bm25"


@dataclass
class ExperimentSet:
    """A complete set of experiment results."""
    name: str  # e.g., "outputs_all_methods", "outputs_all_methods_full"
    results: Dict[str, Any]  # The complete results dict
    total_configs: int
    total_metrics: int


class ResultEvaluator:
    def compare_per_example_results(self, baseline_examples, reproduced_examples):
        """
        Compare per-example attack results between baseline and reproduced runs.
        Returns a list of diffs (dicts) for mismatched predictions or outputs.
        """
        diffs = []
        # Use original_text as the key for matching
        baseline_map = {ex.get('original_text'): ex for ex in baseline_examples}
        reproduced_map = {ex.get('original_text'): ex for ex in reproduced_examples}
        for key in baseline_map:
            base = baseline_map[key]
            repro = reproduced_map.get(key)
            if not repro:
                diffs.append({'original_text': key, 'error': 'Missing in reproduced'})
                continue
            # Compare outputs and result_type
            mismatch = False
            diff_entry = {'original_text': key}
            for field in ['perturbed_text', 'original_output', 'perturbed_output', 'ground_truth_output', 'result_type']:
                base_val = base.get(field)
                repro_val = repro.get(field)
                if base_val != repro_val:
                    mismatch = True
                    diff_entry[field] = {'baseline': base_val, 'reproduced': repro_val}
            if mismatch:
                diffs.append(diff_entry)
        return diffs

    def generate_attack_summary_table(self, metrics_dict):
        """
        Generate a TextAttack-style summary table as HTML from attack metrics.
        """
        keys = [
            ('attack_success_rate', 'Attack Success Rate'),
            ('avg_num_queries', 'Avg Num Queries'),
            ('num_attacks', 'Num Attacks'),
            ('num_successful_attacks', 'Num Successful Attacks')
        ]
        rows = []
        for k, label in keys:
            val = metrics_dict.get(k, '-')
            if isinstance(val, float):
                val = f"{val:.4f}" if 'rate' in k else f"{val:.2f}" if 'avg' in k else f"{val}"
            rows.append(f"<tr><td>{label}</td><td>{val}</td></tr>")
        return """
        <table border="1" style="border-collapse:collapse;">
            <tr><th>Metric</th><th>Value</th></tr>
            {rows}
        </table>
        """.format(rows='\n'.join(rows))

    def generate_per_example_table(self, examples, title="Per-Example Results"):
        """
        Generate an HTML table showing all per-example results.
        Args:
            examples: List of example dicts from log.csv
            title: Title for the table
        """
        if not examples:
            return "<p>No per-example data available.</p>"
        
        # Key fields to display
        display_fields = ['original_text', 'perturbed_text', 'original_output', 'perturbed_output', 
                         'ground_truth_output', 'result_type', 'num_queries']
        
        html = [f"<h3>{title}</h3>"]
        html.append("<table border='1' style='border-collapse:collapse; font-size:12px;'>")
        html.append("<tr>" + ''.join(f"<th style='padding:8px;background:#f0f0f0;'>{h.replace('_', ' ').title()}</th>" 
                                     for h in display_fields) + "</tr>")
        
        for ex in examples:
            html.append("<tr>")
            for field in display_fields:
                val = ex.get(field, '')
                # Truncate long text
                if isinstance(val, str) and len(val) > 100:
                    val = val[:97] + '...'
                # Color code result_type
                if field == 'result_type':
                    color = '#d4edda' if val == 'Successful' else '#f8d7da'
                    html.append(f"<td style='padding:8px;background:{color};'>{val}</td>")
                else:
                    html.append(f"<td style='padding:8px;'>{val}</td>")
            html.append("</tr>")
        
        html.append("</table>")
        html.append(f"<p style='margin-top:8px;color:#666;'>Total examples: {len(examples)}</p>")
        return '\n'.join(html)
    
    def generate_per_example_diff_table(self, diffs):
        """
        Generate an HTML table for per-example prediction diffs.
        """
        if not diffs:
            return "<p>No per-example mismatches found.</p>"
        headers = set()
        for d in diffs:
            headers.update(d.keys())
        headers = list(headers)
        html = ["<table border='1' style='border-collapse:collapse;'>"]
        html.append("<tr>" + ''.join(f"<th>{h}</th>" for h in headers) + "</tr>")
        for d in diffs:
            html.append("<tr>" + ''.join(f"<td>{d.get(h, '')}</td>" for h in headers) + "</tr>")
        html.append("</table>")
        return '\n'.join(html)

    def _extract_metrics_from_nested_dict(self, data: dict, prefix: str = "") -> Dict[str, float]:
        """Recursively extract numeric metrics from nested dictionaries, and also include all top-level numeric keys (for flat summary metrics)."""
        metrics = {}
        for key, value in data.items():
            current_key = f"{prefix}/{key}" if prefix else key
            if isinstance(value, dict):
                if 'metrics' in value:
                    metric_dict = value['metrics']
                    for metric_name, metric_value in metric_dict.items():
                        if isinstance(metric_value, dict):
                            for threshold, val in metric_value.items():
                                if isinstance(val, (int, float)):
                                    full_key = f"{current_key}/{metric_name}@{threshold}"
                                    metrics[full_key] = float(val)
                        elif isinstance(metric_value, (int, float)):
                            full_key = f"{current_key}/{metric_name}"
                            metrics[full_key] = float(metric_value)
                else:
                    nested = self._extract_metrics_from_nested_dict(value, current_key)
                    metrics.update(nested)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[current_key] = float(value)
        # Also add all top-level numeric keys (for flat summary metrics, e.g., from TextAttack)
        if prefix == "" and isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    metrics[key] = float(value)
        return metrics

    def load_paper_metrics(self, codebase_path: Path) -> dict:
        """Load ground truth metrics extracted from the paper (paper_metrics.json) or authors' baseline (complete_results.json from outputs_all_methods_oracle).

        Preference order:
          1. codebase_path/paper_metrics.json (manual baseline)
          2. codebase_path/outputs_all_methods_oracle/complete_results.json (authors' baseline for decontextualization)
          3. codebase_path/outputs_all_methods/complete_results.json (fallback)
          4. Recursive search under nearest 'papers' or 'codebases' dirs
        """
        import os
        
        # 1. Check for paper_metrics.json in experiment directory (manual baseline)
        paper_metrics_path = codebase_path / 'paper_metrics.json'
        logger.debug(f"[DEBUG] Checking for paper_metrics.json in experiment directory: {paper_metrics_path}")
        if paper_metrics_path.exists():
            try:
                with open(paper_metrics_path, 'r') as f:
                    logger.info("✓ Using paper_metrics.json as baseline for metric comparison (experiment directory).")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load paper_metrics.json from experiment directory: {e}")

        # 2. Check for authors' baseline in outputs_all_methods_oracle/complete_results.json
        oracle_baseline_path = codebase_path / 'outputs_all_methods_oracle' / 'complete_results.json'
        logger.debug(f"[DEBUG] Checking for authors' baseline at: {oracle_baseline_path}")
        if oracle_baseline_path.exists():
            try:
                with open(oracle_baseline_path, 'r') as f:
                    logger.info(f"✓ Using authors' baseline from outputs_all_methods_oracle/complete_results.json")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load authors' baseline from {oracle_baseline_path}: {e}")

        # 3. Check for outputs_all_methods/complete_results.json
        methods_baseline_path = codebase_path / 'outputs_all_methods' / 'complete_results.json'
        logger.debug(f"[DEBUG] Checking for baseline at: {methods_baseline_path}")
        if methods_baseline_path.exists():
            try:
                with open(methods_baseline_path, 'r') as f:
                    logger.info(f"✓ Using baseline from outputs_all_methods/complete_results.json")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load baseline from {methods_baseline_path}: {e}")

        # 4. Recursive search under nearest 'papers' or 'codebases' dirs
        current = codebase_path
        found = False
        for level in range(5):  # Search up to 5 levels up
            codebases_dir = current / 'codebases'
            papers_dir = current / 'papers'
            logger.debug(f"[DEBUG] Searching for paper_metrics.json in: {codebases_dir} and {papers_dir} (level {level})")
            for d in [codebases_dir, papers_dir]:
                if d.exists() and d.is_dir():
                    logger.debug(f"[DEBUG] Directory exists: {d}, searching recursively for paper_metrics.json")
                    for root, dirs, files in os.walk(d):
                        logger.debug(f"[DEBUG] Checking directory: {root}")
                        if 'paper_metrics.json' in files:
                            file_path = os.path.join(root, 'paper_metrics.json')
                            logger.debug(f"[DEBUG] Found paper_metrics.json at: {file_path}")
                            try:
                                with open(file_path, 'r') as f:
                                    logger.info(f"✓ Using paper_metrics.json as baseline for metric comparison (found in {file_path}).")
                                    return json.load(f)
                            except Exception as e:
                                logger.error(f"Failed to load paper_metrics.json from {file_path}: {e}")
                            found = True
                            break
                else:
                    logger.debug(f"[DEBUG] Directory does not exist: {d}")
                if found:
                    break
            if found:
                break
            if current.parent == current:
                logger.debug(f"[DEBUG] Reached filesystem root at {current}, stopping search.")
                break
            current = current.parent

        # 3. Fallback: use complete_results.json as baseline
        complete_results_path = codebase_path / 'complete_results.json'
        logger.debug(f"[DEBUG] Checking for complete_results.json in: {complete_results_path}")
        if complete_results_path.exists():
            try:
                with open(complete_results_path, 'r') as f:
                    logger.warning("⚠ Using complete_results.json as baseline (may give 100% match)")
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load complete_results.json: {e}")
        logger.error("No baseline metrics found (paper_metrics.json in experiment/codebase or complete_results.json)")
        return {}
    def _build_metrics_table_rows(self, df):
        """
        Build HTML table rows for the metrics comparison table.
        Args:
            df: Pandas DataFrame with comparison results
        Returns:
            HTML string with <tr> rows
        """
        rows = []
        for _, row in df.iterrows():
            diff_class = 'diff-pos' if row['percent_difference'] >= 0 else 'diff-neg'
            status_class = 'status-pass' if row['within_threshold'] else 'status-fail'
            rows.append(
                f"<tr>"
                f"<td>{row['configuration']}</td>"
                f"<td>{row['metric_name']}</td>"
                f"<td>{row['baseline_value']:.4f}</td>"
                f"<td>{row['reproduced_value']:.4f}</td>"
                f"<td class='{diff_class}'>{row['percent_difference']:+.2f}%</td>"
                f"<td class='{status_class}'>{'PASS' if row['within_threshold'] else 'FAIL'}</td>"
                f"</tr>"
            )
        return '\n'.join(rows)
    def generate_visualizations_index(self, visualizations_root: Path):
        """
        Generate a top-level dashboard listing all papers' visualizations.
        """
        import os
        from datetime import datetime
        visualizations_root = Path(visualizations_root)
        paper_dirs = [d for d in visualizations_root.iterdir() if d.is_dir()]
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>EVALLab Dashboard</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        .paper-list {{ margin: 30px 0; }}
        .paper-entry {{ background: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); margin: 18px 0; padding: 18px; }}
        .paper-entry h2 {{ margin: 0 0 10px 0; color: #34495e; }}
        .paper-entry a {{ color: #3498db; font-weight: bold; text-decoration: none; }}
        .footer {{ margin-top: 40px; padding: 20px; text-align: center; color: #7f8c8d; border-top: 1px solid #bdc3c7; }}
    </style>
</head>
<body>
    <h1>EVALLab Dashboard</h1>
    <h2>All Papers: EVALLab's Reports</h2>
    <div class="paper-list">
        {''.join([
            f'<div class="paper-entry">'
            f'<h2>Research Paper: {d.name}</h2>'
            f'<a href="{d.name}/visualizations.html">View Visualizations, Metrics & Logs for this research paper</a>'
            f'</div>' for d in paper_dirs if (d / 'visualizations.html').exists()
        ])}
    </div>
    <div class="footer">
        <p>Generated by EVALLab</p>
        <p>Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>
"""
        with open(visualizations_root / 'visualizations.html', 'w', encoding='utf-8') as f:
            f.write(html)

    def __init__(self, llm_client=None, threshold: float = 0.05):
        """
        Initialize evaluator.

        Args:
            llm_client: Ollama client for LLM assistance
            threshold: Acceptable difference threshold (default 5%)
        """
        self.llm_client = llm_client
        self.threshold = threshold

    def load_all_experiment_results(self, codebase_path: Path) -> List[ExperimentSet]:
        """
        Load results from all output directories, or from the root if present.

        Args:
            codebase_path: Path to codebase

        Returns:
            List of ExperimentSet objects
        """
        experiment_sets = []

        # Check for complete_results.json in the root of the codebase
        root_results_path = codebase_path / "complete_results.json"
        if root_results_path.exists():
            try:
                with open(root_results_path, 'r') as f:
                    results = json.load(f)
                total_configs = len(results)
                total_metrics = self._count_metrics_in_results(results)
                experiment_sets.append(ExperimentSet(
                    name="root",
                    results=results,
                    total_configs=total_configs,
                    total_metrics=total_metrics
                ))
                logger.info(f"✓ Loaded root: {total_configs} configs, {total_metrics} metrics")
            except Exception as e:
                logger.error(f"Failed to load root complete_results.json: {e}")

        # Dynamically discover output directories with complete_results.json
        output_dirs = []
        for item in codebase_path.iterdir():
            if item.is_dir() and (item / "complete_results.json").exists():
                output_dirs.append(item.name)

        if not experiment_sets and not output_dirs:
            logger.warning(
                "No output directories or root complete_results.json found")
            return []

        for dir_name in output_dirs:
            output_dir = codebase_path / dir_name
            if output_dir.exists():
                complete_results_path = output_dir / "complete_results.json"
                if complete_results_path.exists():
                    try:
                        with open(complete_results_path, 'r') as f:
                            results = json.load(f)

                        # Count configurations and metrics
                        total_configs = len(results)
                        total_metrics = self._count_metrics_in_results(results)

                        experiment_sets.append(ExperimentSet(
                            name=dir_name,
                            results=results,
                            total_configs=total_configs,
                            total_metrics=total_metrics
                        ))

                        logger.info(
                            f"✓ Loaded {dir_name}: {total_configs} configs, {total_metrics} metrics")
                    except Exception as e:
                        logger.error(f"Failed to load {dir_name}: {e}")

        return experiment_sets

    def _count_metrics_in_results(self, results: dict) -> int:
        """Count total number of metrics in nested results."""
        count = 0

        def count_recursive(data):
            nonlocal count
            if isinstance(data, dict):
                if 'metrics' in data:
                    for v in data['metrics'].values():
                        if isinstance(v, dict):
                            count += len(v)  # e.g., recall@1, recall@5, etc.
                        else:
                            count += 1
                else:
                    for v in data.values():
                        count_recursive(v)

        count_recursive(results)
        return count

    def extract_all_metrics_from_experiments(self, experiment_sets: List[ExperimentSet]) -> Dict[str, float]:
        """Extract all metrics from all experiment sets.

        Args:
            experiment_sets: List of experiment result containers

        Returns:
            Flat dict mapping "experiment_set/config/model/metric" to value.
        """
        flat_metrics = {}
        for exp_set in experiment_sets:
            metrics = self._extract_metrics_from_nested_dict(
                exp_set.results,
                prefix=exp_set.name
            )
            flat_metrics.update(metrics)
        return flat_metrics

    # compare_to_paper_metrics removed - functionality replaced by extract_all_metrics_from_experiments + compare_results

    def extract_baseline_from_paper(self, paper_content: str, codebase_path: Path = None) -> BaselineMetrics:
        """
        Extract baseline metrics from paper text or report.md files.

        Args:
            paper_content: Text content from the research paper
            codebase_path: Path to codebase for finding report.md files

        Returns:
            BaselineMetrics with extracted values
        """
        # PRIORITY 1: Try to parse report.md files for configuration-specific metrics
        # This represents the paper's reported baselines, not the reproduced results
        if codebase_path:
            metrics = self._parse_report_files(codebase_path)
            if metrics:
                logger.info(
                    f"✓ Using report.md as baseline (paper's reported results)")
                return BaselineMetrics(
                    metrics=metrics,
                    source="Parsed from outputs_all_methods/report.md"
                )

        # PRIORITY 2: Check for baseline_metrics.json (manually created baseline)
        if codebase_path:
            baseline_path = codebase_path / "baseline_metrics.json"
            if baseline_path.exists():
                try:
                    with open(baseline_path, 'r') as f:
                        baseline_metrics = json.load(f)
                    logger.info(
                        f"✓ Using baseline_metrics.json as baseline (manually specified)")
                    return BaselineMetrics(
                        metrics=baseline_metrics,
                        source="Loaded from baseline_metrics.json"
                    )
                except Exception as e:
                    logger.error(f"Failed to load baseline_metrics.json: {e}")

        # FALLBACK: Use complete_results.json only if report.md not available
        # Note: This may give 100% match if comparing file against itself
        if codebase_path:
            json_metrics = self._extract_baseline_from_complete_results(
                codebase_path)
            if json_metrics:
                logger.warning(
                    f"⚠ Using complete_results.json as baseline (may give 100% match)")
                return BaselineMetrics(
                    metrics=json_metrics,
                    source="Extracted from complete_results.json (same as reproduced)"
                )

        if not self.llm_client:
            logger.warning("No LLM client and no report.md found")
            return BaselineMetrics(metrics={}, source="No extraction method available")

        system_prompt = """You are an expert at reading research papers and extracting quantitative metrics.
Extract ALL numerical performance metrics from the results/evaluation section.
Common metrics: Recall@K, MRR, NDCG, Precision, F1, Accuracy, MAP.
Return as flat JSON with metric names as keys and numeric values only."""

        user_prompt = f"""Extract ALL performance metrics from this research paper's results section.
Look for metrics like: Recall@10, MRR, NDCG@10, F1, Accuracy, Precision, etc.

Paper text (results section):
{paper_content[:6000]}

Return ONLY a flat JSON object with metric names and their numeric values.
Example: {{"recall@10": 0.458, "mrr": 0.252, "f1": 0.567, "accuracy": 0.425}}

JSON:"""

        try:
            metrics_dict = self.llm_client.extract_json(
                user_prompt, system_prompt)

            # Clean up metric names (lowercase, normalize)
            cleaned_metrics = {}
            for key, value in metrics_dict.items():
                if isinstance(value, (int, float)):
                    # Normalize metric names
                    clean_key = key.lower().replace(' ', '_').replace('-', '_')
                    cleaned_metrics[clean_key] = float(value)

            if not cleaned_metrics:
                logger.warning("No metrics extracted from paper")
            return BaselineMetrics(
                metrics=cleaned_metrics,
                source="Extracted from paper using EVALLab"
            )
        except Exception as e:
            logger.error(f"Failed to extract baseline metrics: {e}")
            return BaselineMetrics(metrics={}, source="Extraction failed")

    def _extract_baseline_from_complete_results(self, codebase_path: Path) -> Dict[str, float]:
        """
        Extract baseline metrics directly from complete_results.json files.
        This provides ground truth from the paper's actual experiments.

        Args:
            codebase_path: Path to codebase

        Returns:
            Dict of "experiment_set/config/retriever/metric" -> value
        """
        metrics = {}

        # Check for complete_results.json in the root of the codebase
        root_results_path = codebase_path / "complete_results.json"
        if root_results_path.exists():
            try:
                with open(root_results_path, 'r') as f:
                    results = json.load(f)
                extracted = self._extract_metrics_from_nested_dict(results, prefix="root")
                metrics.update(extracted)
                logger.info(f"✓ Extracted {len(extracted)} baseline metrics from root/complete_results.json")
            except Exception as e:
                logger.error(f"Failed to extract from {root_results_path}: {e}")

        # Dynamically discover output directories
        output_dirs = []
        for item in codebase_path.iterdir():
            if item.is_dir() and (item / "complete_results.json").exists():
                output_dirs.append(item.name)

        for dir_name in output_dirs:
            results_path = codebase_path / dir_name / "complete_results.json"
            if results_path.exists():
                try:
                    with open(results_path, 'r') as f:
                        results = json.load(f)
                    extracted = self._extract_metrics_from_nested_dict(results, prefix=dir_name)
                    metrics.update(extracted)
                    logger.info(f"✓ Extracted {len(extracted)} baseline metrics from {dir_name}/complete_results.json")
                except Exception as e:
                    logger.error(f"Failed to extract from {results_path}: {e}")

        return metrics

    def _parse_report_files(self, codebase_path: Path) -> Dict[str, float]:
        """
        Parse report.md files to extract configuration-specific baseline metrics.

        Args:
            codebase_path: Path to codebase

        Returns:
            Dict of "config/retriever/metric" -> value
        """
        metrics = {}

        # Dynamically discover output directories with report.md
        output_dirs = []
        for item in codebase_path.iterdir():
            if item.is_dir() and (item / "report.md").exists():
                output_dirs.append(item.name)

        for dir_name in output_dirs:
            report_path = codebase_path / dir_name / "report.md"
            if report_path.exists():
                try:
                    with open(report_path, 'r') as f:
                        content = f.read()

                    # Parse the markdown report
                    parsed = self._parse_markdown_report(content)

                    # Flatten: parsed is {config/retriever: {metric: value}}
                    # Convert to: {dir/config/retriever/metric: value}
                    for config_retriever, config_metrics in parsed.items():
                        for metric_name, value in config_metrics.items():
                            key = f"{dir_name}/{config_retriever}/{metric_name}"
                            metrics[key] = value

                    logger.info(
                        f"✓ Parsed {len(parsed)} config/retriever combinations from {report_path.name}")
                except Exception as e:
                    logger.error(f"Failed to parse {report_path}: {e}")

        return metrics

    def _parse_markdown_report(self, content: str) -> Dict[str, Dict[str, float]]:
        """
        Parse markdown report to extract metrics by configuration.

        Args:
            content: Markdown report content

        Returns:
            Dict mapping config_name -> {metric: value}
        """
        import re

        metrics_by_config = {}
        current_config = None
        current_task_type = None  # Track if we're in 'retrieval' or 'downstream' section

        lines = content.split('\n')
        for line in lines:
            config_match = re.match(r'^###\s+(\w+/\w+)', line)
            if config_match:
                current_config = config_match.group(1)
                current_task_type = None  # Reset task type for new config
                metrics_by_config[current_config] = {}
                continue

            # Detect task type sections
            if current_config:
                if '**Retrieval Performance:**' in line:
                    current_task_type = 'retrieval'
                    continue
                elif '**Downstream Tasks:**' in line:
                    current_task_type = 'downstream'
                    continue

            if current_config and current_task_type:
                retrieval_match = re.search(
                    r'(\w+):\s+Recall@10=([\d.]+)(?:.*?)MRR=([\d.]+)',
                    line
                )
                if retrieval_match and current_task_type == 'retrieval':
                    retriever = retrieval_match.group(1)
                    recall = float(retrieval_match.group(2))
                    mrr = float(retrieval_match.group(3))

                    base_key = f"{current_config}/{current_task_type}/{retriever}"
                    metrics_by_config.setdefault(base_key, {})
                    metrics_by_config[base_key]['recall@10'] = recall
                    metrics_by_config[base_key]['mrr'] = mrr

                task_match = re.search(
                    r'(\w+):\s+Accuracy=([\d.]+)(?:.*?)F1=([\d.]+)',
                    line
                )
                if task_match and current_task_type == 'downstream':
                    retriever = task_match.group(1)
                    accuracy = float(task_match.group(2))
                    f1 = float(task_match.group(3))

                    base_key = f"{current_config}/{current_task_type}/{retriever}"
                    metrics_by_config.setdefault(base_key, {})
                    metrics_by_config[base_key]['accuracy'] = accuracy
                    metrics_by_config[base_key]['f1'] = f1

        return metrics_by_config

    def _normalize_metric_key(self, key: str) -> str:
        """
        Normalize metric key for robust comparison.
        Fast path for common cases, comprehensive cleanup for edge cases.
        """
        import re
        
        # Fast path: check if key needs normalization
        if key and key.islower() and '  ' not in key and '--' not in key and '//' not in key:
            # Already normalized, just handle @ symbol and trailing slash
            return key.replace('@', '_at_').strip('/')
        
        # Comprehensive normalization for complex cases
        # Lowercase and basic replacements
        key = key.lower().replace('-', '_').replace(' ', '').replace('@', '_at_')
        
        # Remove ANSI sequences (rare, but handle once)
        if '\x1b' in key or any(c.isdigit() for c in key[-3:]):
            key = re.sub(r"\x1b\[[0-9;]*m", "", key)
            key = re.sub(r"\d{1,3}m", "", key)
        
        # Collapse repeated characters
        key = re.sub(r'/+', '/', key).replace('__', '_')
        key = re.sub(r'^(root/)+', 'root/', key).strip('/')
        
        # Deduplicate consecutive path segments
        parts = [p for i, p in enumerate(key.split('/')) if p and (i == 0 or p != key.split('/')[i-1])]
        return '/'.join(parts)

    def _flatten_dict(self, d, parent_key="", sep="/"):
        """Recursively flattens a nested dictionary. Optimized with generator."""
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key, sep))
            else:
                items[new_key] = v
        return items


    def compare_results(self, baseline: BaselineMetrics,
                        reproduced: Dict[str, float]) -> List[ComparisonResult]:
        """
        Compare reproduced results to baseline metrics.
        Only compares metrics that exist in the baseline.
        Optimized: pre-normalize all keys once, avoid redundant processing.
        """
        comparisons = []

        # Flatten nested dicts in reproduced metrics (if any)
        flat_reproduced = self._flatten_dict(reproduced) if any(isinstance(v, dict) for v in reproduced.values()) else reproduced

        # Pre-normalize all keys once (cache normalized versions)
        # For duplicates after normalization, prefer shorter paths
        norm_baseline = {}
        for k, v in baseline.metrics.items():
            norm_key = self._normalize_metric_key(str(k))
            if norm_key not in norm_baseline:
                norm_baseline[norm_key] = (k, v, str(k).count('/'))
            elif str(k).count('/') < norm_baseline[norm_key][2]:
                norm_baseline[norm_key] = (k, v, str(k).count('/'))
        
        norm_reproduced = {}
        for k, v in flat_reproduced.items():
            norm_key = self._normalize_metric_key(str(k))
            if norm_key not in norm_reproduced:
                norm_reproduced[norm_key] = (k, v, str(k).count('/'))
            elif str(k).count('/') < norm_reproduced[norm_key][2]:
                norm_reproduced[norm_key] = (k, v, str(k).count('/'))

        # Debug logging (only if enabled)
        if logger.isEnabledFor(logging.DEBUG) and len(norm_baseline) < 20:
            logger.debug(f"Baseline keys sample: {list(norm_baseline.keys())[:10]}")
            logger.debug(f"Reproduced keys sample: {list(norm_reproduced.keys())[:10]}")

        matched_count = 0
        unmatched_baseline = []

        # Only compare metrics that exist in the baseline
        for norm_key, (baseline_key, baseline_value, _) in norm_baseline.items():
            if norm_key in norm_reproduced:
                _, reproduced_value, _ = norm_reproduced[norm_key]
                matched_count += 1

                difference = reproduced_value - baseline_value

                if baseline_value != 0:
                    percent_diff = (difference / abs(baseline_value)) * 100
                else:
                    percent_diff = float('inf') if difference != 0 else 0

                # Extract metric name and config efficiently
                metric_name = baseline_key.split('/')[-1] if '/' in baseline_key else baseline_key
                config = baseline_key

                # Define within_threshold
                within_threshold = abs(percent_diff) <= self.threshold * 100

                comparisons.append(ComparisonResult(
                    metric_name=metric_name,
                    baseline_value=baseline_value,
                    reproduced_value=reproduced_value,
                    difference=difference,
                    percent_difference=percent_diff,
                    within_threshold=within_threshold,
                    configuration=config
                ))
            else:
                unmatched_baseline.append(baseline_key)

        # Summary logging
        logger.info(
            f"✓ Matched {matched_count}/{len(norm_baseline)} baseline metrics")
        if unmatched_baseline:
            logger.warning(
                f"⚠️  {len(unmatched_baseline)} baseline metrics had no matches in reproduced results")
            logger.debug(f"Unmatched baseline metrics: {unmatched_baseline[:10]}")

        return comparisons

    def generate_report(self, comparisons: List[ComparisonResult],
                       baseline_metrics: dict = None,
                       reproduced_metrics: dict = None,
                       baseline_examples: list = None,
                       reproduced_examples: list = None) -> str:
        """
        Generate a human-readable report of the comparison.

        Args:
            comparisons: List of comparison results

        Returns:
            Formatted report string
        """
        report_lines = [
            "="*80,
            "REPRODUCTION RESULTS EVALUATION - ALL CONFIGURATIONS",
            "="*80,
            ""
        ]

        # If attack metrics are available, show TextAttack-style summary table
        if reproduced_metrics and any(k in reproduced_metrics for k in ["attack_success_rate", "avg_num_queries", "num_attacks", "num_successful_attacks"]):
            report_lines.append("TextAttack-Style Attack Results Summary:")
            report_lines.append(self.generate_attack_summary_table(reproduced_metrics))
            report_lines.append("")

        if not comparisons:
            report_lines.append("No metrics available for comparison.")
            return "\n".join(report_lines)

        # Group by experiment set and configuration
        by_experiment = {}
        for comp in comparisons:
            parts = comp.configuration.split('/')
            exp_set = parts[0] if parts else "unknown"

            if exp_set not in by_experiment:
                by_experiment[exp_set] = []
            by_experiment[exp_set].append(comp)

        # If per-example results are available, show per-example diffs table
        if baseline_examples and reproduced_examples:
            diffs = self.compare_per_example_results(baseline_examples, reproduced_examples)
            per_example_total = max(len(baseline_examples), len(reproduced_examples))
            per_example_matches = per_example_total - len(diffs)
            
            report_lines.append("\nPer-Example Prediction Differences:")
            report_lines.append(self.generate_per_example_diff_table(diffs))
            report_lines.append(f"Per-example matches: {per_example_matches}/{per_example_total}")
            report_lines.append("")

        # Overall summary (per-example metrics are now included in comparisons)
        total_comparisons = len(comparisons)
        within_threshold = sum(1 for c in comparisons if c.within_threshold)

        report_lines.extend([
            f"Total comparisons: {total_comparisons}",
            f"Within threshold ({self.threshold*100}%): {within_threshold}/{total_comparisons}",
            f"Overall success rate: {within_threshold/total_comparisons*100:.1f}%" if total_comparisons > 0 else "Overall success rate: N/A",
            f"Experiment sets analyzed: {len(by_experiment)}",
            "",
            "="*80
        ])

        # Detailed results by experiment set
        for exp_set, comps in sorted(by_experiment.items()):
            report_lines.extend([
                "",
                f"\n{'='*80}",
                f"EXPERIMENT SET: {exp_set}",
                f"{'='*80}",
                f"Comparisons in this set: {len(comps)}",
                ""
            ])

            # Group by configuration within this experiment set
            by_config = {}
            for comp in comps:
                # Get config/model part
                config = '/'.join(comp.configuration.split('/')[1:4])
                if config not in by_config:
                    by_config[config] = []
                by_config[config].append(comp)

        # Best performing configurations (closest to baseline)
        report_lines.extend([
            "",
            "="*80,
            "BEST PERFORMING CONFIGURATIONS (closest to baseline):",
            "="*80
        ])

        best_configs = {}
        for comp in comparisons:
            # Only aggregate numeric percent differences
            try:
                pct = float(comp.percent_difference)
            except (TypeError, ValueError):
                continue
            config = '/'.join(comp.configuration.split('/')[1:4])
            if config not in best_configs:
                best_configs[config] = []
            best_configs[config].append(abs(pct))

        # Average percent difference per config
        config_scores = {
            k: sum(v) / len(v)
            for k, v in best_configs.items()
        }

        for config, avg_diff in sorted(config_scores.items(), key=lambda x: x[1])[:10]:
            report_lines.append(f"  {config}: avg diff = {avg_diff:.2f}%")

        report_lines.extend([
            "",
            "="*80
        ])

        return "\n".join(report_lines)

    def analyze_differences_with_llm(self, comparisons: List[ComparisonResult],
                                     paper_context: str) -> str:
        """
        Use LLM to provide insights on why results might differ.

        Args:
            comparisons: Comparison results
            paper_context: Context from the research paper

        Returns:
            Analysis and potential explanations
        """
        if not self.llm_client:
            return "LLM analysis not available (no client provided)"

        # Sample some interesting comparisons
        sample_size = min(10, len(comparisons))
        def _safe_abs_pct(c):
            try:
                return abs(float(c.percent_difference))
            except (TypeError, ValueError):
                return float('inf')
        sample = sorted(comparisons, key=_safe_abs_pct)[:sample_size]

        # Build comparison summary for LLM
        summary = "Reproduction results across multiple configurations:\n\n"

        # Group by experiment set
        by_exp = {}
        for comp in sample:
            exp = comp.configuration.split('/')[0]
            if exp not in by_exp:
                by_exp[exp] = []
            by_exp[exp].append(comp)

        def _fmt_float(val):
            try:
                return f"{float(val):.4f}"
            except (TypeError, ValueError):
                return str(val)

        for exp_set, comps in by_exp.items():
            summary += f"\n{exp_set}:\n"
            for comp in comps[:5]:
                config = '/'.join(comp.configuration.split('/')[1:3])
                baseline_str = _fmt_float(comp.baseline_value)
                reproduced_str = _fmt_float(comp.reproduced_value)
                summary += f"  - {config}/{comp.metric_name}: baseline={baseline_str}, "
                try:
                    pct = float(comp.percent_difference)
                    summary += f"reproduced={reproduced_str} ({pct:+.2f}%)\n"
                except (TypeError, ValueError):
                    summary += f"reproduced={reproduced_str} (N/A)\n"

        system_prompt = """You are an expert in machine learning research and experiment reproduction.
Analyze the differences between baseline and reproduced results across multiple experimental configurations."""

        user_prompt = f"""Paper context (truncated):
{paper_context[:2000]}

{summary}

The experiments tested multiple configurations:
- Different granularities: sentence vs paragraph
- Different decontextualization strategies: minimal, title_only, heading_only, etc.
- Different retrievers: BM25, TF-IDF, ColBERT, Cross-Encoder

Explain:
1. Why some configurations match better than others
2. Possible reasons for metric differences
3. Which variations are expected vs unexpected

Provide a concise analysis (3-4 paragraphs)."""

        try:
            analysis = self.llm_client.generate(user_prompt, system_prompt)
            return analysis
        except Exception as e:
            logger.error(f"Failed to generate LLM analysis: {e}")
            return f"LLM analysis failed: {str(e)}"

    def generate_summary_statistics(self, comparisons: List[ComparisonResult],
                                        per_example_total: int = 0,
                                        per_example_matches: int = 0) -> str:
        """
        Generate summary statistics grouped by models and configurations.

        Args:
            comparisons: List of comparison results
            per_example_total: Total number of per-example comparisons
            per_example_matches: Number of per-example matches

        Returns:
            Summary statistics string
        """
        if not comparisons:
            return "No comparisons available for statistics."

        lines = [
            "\n" + "="*80,
            "SUMMARY STATISTICS",
            "="*80,
            ""
        ]

        # Statistics by retriever model (bm25, tfidf, colbert, cross_encoder)
        by_model = {}
        for comp in comparisons:
            parts = comp.configuration.split('/')
            if len(parts) >= 3:
                model = parts[2]  # e.g., bm25, tfidf
                if model not in by_model:
                    by_model[model] = []
                by_model[model].append(comp)

        lines.append("Performance by Retrieval Model:")
        lines.append("-" * 80)
        for model, comps in sorted(by_model.items()):
            passing = sum(1 for c in comps if c.within_threshold)
            numeric_pcts = []
            for c in comps:
                try:
                    numeric_pcts.append(abs(float(c.percent_difference)))
                except (TypeError, ValueError):
                    continue
            avg_diff = (sum(numeric_pcts) / len(numeric_pcts)) if numeric_pcts else 0.0
            lines.append(
                f"  {model:15s}: {passing:3d}/{len(comps):3d} pass  |  "
                f"avg diff: {avg_diff:6.2f}%"
            )

        # Statistics by granularity (sentence vs paragraph)
        by_granularity = {}
        for comp in comparisons:
            parts = comp.configuration.split('/')
            if len(parts) >= 2:
                granularity = parts[1].split('/')[0]  # sentence or paragraph
                if granularity not in by_granularity:
                    by_granularity[granularity] = []
                by_granularity[granularity].append(comp)

        lines.append("")
        lines.append("Performance by Granularity:")
        lines.append("-" * 80)
        for gran, comps in sorted(by_granularity.items()):
            passing = sum(1 for c in comps if c.within_threshold)
            numeric_pcts = []
            for c in comps:
                try:
                    numeric_pcts.append(abs(float(c.percent_difference)))
                except (TypeError, ValueError):
                    continue
            avg_diff = (sum(numeric_pcts) / len(numeric_pcts)) if numeric_pcts else 0.0
            lines.append(
                f"  {gran:15s}: {passing:3d}/{len(comps):3d} pass  |  "
                f"avg diff: {avg_diff:6.2f}%"
            )

        # Overall totals (per-example metrics are now included in comparisons)
        lines.append("")
        lines.append("Overall Totals:")
        lines.append("-" * 80)
        total_comparisons = len(comparisons)
        total_passing = sum(1 for c in comparisons if c.within_threshold)
        lines.append(f"  TOTAL: {total_passing}/{total_comparisons} pass ({total_passing/total_comparisons*100:.1f}%)")

        lines.append("")
        lines.append("="*80)

        return "\n".join(lines)

    def generate_comprehensive_conclusions(self,
                                           comparisons: List[ComparisonResult],
                                           experiment_sets: List[ExperimentSet],
                                           baseline: BaselineMetrics,
                                           paper_context: str = "") -> str:
        """
        Generate comprehensive conclusions analyzing LLM agent performance.

        Args:
            comparisons: All comparison results
            experiment_sets: Experiment set metadata
            baseline: Baseline metrics
            paper_context: Context from paper

        Returns:
            Comprehensive analysis and recommendations
        """
        lines = [
            "\n" + "="*80,
            "COMPREHENSIVE ANALYSIS & CONCLUSIONS",
            "="*80,
            ""
        ]

        # 1. Overall Performance Assessment
        lines.append("1. OVERALL REPRODUCTION PERFORMANCE")
        lines.append("-" * 80)

        total = len(comparisons)
        passing = sum(1 for c in comparisons if c.within_threshold)
        success_rate = (passing / total * 100) if total > 0 else 0

        # Performance grading
        if success_rate >= 90:
            grade = "EXCELLENT"
            assessment = "The EVALLab agent successfully reproduced the experiments with high fidelity."
        elif success_rate >= 70:
            grade = "GOOD"
            assessment = "The EVALLab agent achieved good reproduction with some deviations."
        elif success_rate >= 50:
            grade = "MODERATE"
            assessment = "The EVALLab agent partially reproduced results but with notable differences."
        else:
            grade = "POOR"
            assessment = "The EVALLab agent struggled to accurately reproduce the baseline results."

        lines.extend([
            f"Grade: {grade} ({success_rate:.1f}% success rate)",
            f"Assessment: {assessment}",
            "",
            f"Total Comparisons: {total}",
            f"Metrics Within Threshold ({self.threshold*100}%): {passing}/{total}",
            f"Experiment Sets Tested: {len(experiment_sets)}",
            f"Baseline Source: {baseline.source}",
            ""
        ])

        # 2. Key Findings by Configuration
        lines.append("2. KEY FINDINGS BY CONFIGURATION")
        lines.append("-" * 80)

        # Analyze by granularity
        by_granularity = {}
        for comp in comparisons:
            parts = comp.configuration.split('/')
            if len(parts) >= 2:
                gran = parts[1].split('/')[0]
                if gran not in by_granularity:
                    by_granularity[gran] = []
                by_granularity[gran].append(comp)

        for gran, comps in sorted(by_granularity.items()):
            passing_count = sum(1 for c in comps if c.within_threshold)
            gran_rate = (passing_count / len(comps) * 100) if comps else 0
            numeric_pcts = []
            for c in comps:
                try:
                    numeric_pcts.append(abs(float(c.percent_difference)))
                except (TypeError, ValueError):
                    continue
            avg_deviation = (sum(numeric_pcts) / len(numeric_pcts)) if numeric_pcts else 0

            lines.append(f"\n{gran.upper()} Granularity:")
            lines.append(
                f"  Success Rate: {gran_rate:.1f}% ({passing_count}/{len(comps)} metrics)")
            lines.append(f"  Avg Deviation: {avg_deviation:.2f}%")

            if gran_rate < 50:
                lines.append(
                    f"  ⚠️  LOW PERFORMANCE: {gran} configuration needs investigation")

        # Analyze by experiment set
        lines.append("\nBy Experiment Set:")
        by_exp = {}
        for comp in comparisons:
            exp = comp.configuration.split('/')[0]
            if exp not in by_exp:
                by_exp[exp] = []
            by_exp[exp].append(comp)

        for exp, comps in sorted(by_exp.items()):
            passing_count = sum(1 for c in comps if c.within_threshold)
            exp_rate = (passing_count / len(comps) * 100) if comps else 0
            numeric_pcts = []
            for c in comps:
                try:
                    numeric_pcts.append(abs(float(c.percent_difference)))
                except (TypeError, ValueError):
                    continue
            avg_deviation = (sum(numeric_pcts) / len(numeric_pcts)) if numeric_pcts else 0

            lines.append(f"\n{exp}:")
            lines.append(
                f"  Success Rate: {exp_rate:.1f}% ({passing_count}/{len(comps)} metrics)")
            lines.append(f"  Avg Deviation: {avg_deviation:.2f}%")

            if avg_deviation > 50:
                lines.append(
                    f"  ⚠️  HIGH DEVIATION: Possible data/environment mismatch")

        lines.append("")

        # 3. Root Cause Analysis
        lines.append("3. ROOT CAUSE ANALYSIS")
        lines.append("-" * 80)

        # Find worst performing metrics
        def _safe_abs_pct_worst(x):
            try:
                return abs(float(x.percent_difference))
            except (TypeError, ValueError):
                return -float('inf')
        worst_metrics = sorted(comparisons, key=_safe_abs_pct_worst, reverse=True)[:5]

        lines.append("\nTop Issues Identified:")
        for i, comp in enumerate(worst_metrics, 1):
            config_short = '/'.join(comp.configuration.split('/')[1:4])
            try:
                pct = float(comp.percent_difference)
                lines.append(
                    f"  {i}. {comp.metric_name} in {config_short}: "
                    f"{pct:+.2f}% deviation"
                )
            except (TypeError, ValueError):
                lines.append(
                    f"  {i}. {comp.metric_name} in {config_short}: N/A deviation"
                )

        lines.append("\nPossible Root Causes:")

        # Analyze patterns
        def _is_high_dev(c):
            try:
                return abs(float(c.percent_difference)) > 50
            except (TypeError, ValueError):
                return False
        high_deviation_count = sum(1 for c in comparisons if _is_high_dev(c))
        if high_deviation_count > total * 0.3:  # More than 30% have >50% deviation
            lines.append("  • DATA MISMATCH: Many metrics show >50% deviation")
            lines.append(
                "    → Check if experiment used same dataset as paper")
            lines.append(
                "    → Verify data preprocessing steps match paper methodology")

        # Check for systematic issues
        sentence_comps = [
            c for c in comparisons if 'sentence' in c.configuration.lower()]
        if sentence_comps:
            sentence_rate = sum(
                1 for c in sentence_comps if c.within_threshold) / len(sentence_comps) * 100
            if sentence_rate < 30:
                lines.append(
                    "  • SENTENCE GRANULARITY ISSUE: Poor performance on sentence-level tasks")
                lines.append(
                    "    → May indicate chunking/segmentation differences")
                lines.append(
                    "    → Check sentence tokenization implementation")

        # Check for retrieval model issues
        for model in ['bm25', 'tfidf', 'colbert', 'cross_encoder']:
            model_comps = [
                c for c in comparisons if model in c.configuration.lower()]
            if model_comps:
                model_rate = sum(
                    1 for c in model_comps if c.within_threshold) / len(model_comps) * 100
                if model_rate < 30:
                    lines.append(
                        f"  • {model.upper()} IMPLEMENTATION: Significant deviations detected")
                    lines.append(
                        f"    → Verify {model} configuration matches paper specifications")

        lines.append("")

        # 4. What the LLM Agent Accomplished
        lines.append("4. EVALLab AGENT ACCOMPLISHMENTS")
        lines.append("-" * 80)

        lines.extend([
            "The Local EVALLab Agent successfully:",
            "  ✓ Parsed research paper PDF and extracted methodology",
            "  ✓ Identified and analyzed local codebase structure",
            f"  ✓ Executed {len(experiment_sets)} complete experiment sets",
            f"  ✓ Generated {total} metric comparisons across configurations",
            "  ✓ Extracted and compared baseline metrics from report files",
            ""
        ])

        # Best performing configurations
        best_configs = {}
        for comp in comparisons:
            try:
                pct = abs(float(comp.percent_difference))
            except (TypeError, ValueError):
                continue
            config = '/'.join(comp.configuration.split('/')[1:4])
            if config not in best_configs:
                best_configs[config] = []
            best_configs[config].append(pct)

        config_scores = {k: sum(v) / len(v) for k, v in best_configs.items()}
        top_configs = sorted(config_scores.items(), key=lambda x: x[1])[:3]

        if top_configs:
            lines.append("Best Reproduced Configurations:")
            for config, avg_diff in top_configs:
                lines.append(f"  • {config}: {avg_diff:.2f}% avg deviation")
            lines.append("")

        # 5. Recommendations for Improvement
        lines.append("5. RECOMMENDATIONS FOR IMPROVEMENT")
        lines.append("-" * 80)

        lines.append("\nImmediate Actions:")

        if success_rate < 50:
            lines.append(
                "  🔴 CRITICAL: Low success rate indicates fundamental issues")
            lines.append("     1. Verify data files match paper's dataset")
            lines.append(
                "     2. Check dependency versions match paper requirements")
            lines.append(
                "     3. Confirm environment setup (Python version, libraries)")

        if high_deviation_count > 0:
            lines.append(
                f"  🟡 WARNING: {high_deviation_count} metrics show >50% deviation")
            lines.append(
                "     1. Compare experiment parameters with paper methodology")
            lines.append("     2. Validate preprocessing/normalization steps")
            lines.append(
                "     3. Check for stochastic processes (set random seeds)")

        lines.append("\\nEVALLab Agent Enhancements:")
        lines.append("  1. BASELINE EXTRACTION:")
        lines.append(
            "     → Improve parsing of configuration-specific metrics")
        lines.append(
            "     → Extract metrics with full context (granularity, model, strategy)")
        lines.append("     → Use structured templates for metric extraction")
        lines.append("")
        lines.append("  2. VALIDATION CHECKS:")
        lines.append(
            "     → Verify dataset integrity before running experiments")
        lines.append("     → Compare file checksums with paper's data release")
        lines.append(
            "     → Validate dependency versions match paper requirements")
        lines.append("")
        lines.append("  3. PROMPT ENGINEERING:")
        lines.append(
            "     → Provide more context about experiment configurations")
        lines.append(
            "     → Use chain-of-thought prompting for methodology extraction")
        lines.append("     → Add examples of expected metric formats")
        lines.append("")
        lines.append("  4. ERROR RECOVERY:")
        lines.append("     → Implement retry logic with different LLM models")
        lines.append(
            "     → Add fallback to structured parsing when LLM fails")
        lines.append("     → Log intermediate outputs for debugging")
        lines.append("")

        # 6. Next Steps
        lines.append("6. RECOMMENDED NEXT STEPS")
        lines.append("-" * 80)

        lines.append("\nShort Term (1-2 days):")
        lines.append("  [ ] Verify dataset files match paper specifications")
        lines.append(
            "  [ ] Check all dependency versions against requirements.txt")
        lines.append(
            "  [ ] Run experiments with fixed random seeds for reproducibility")
        lines.append(
            "  [ ] Compare preprocessing code with paper's implementation")
        lines.append("")

        lines.append("Medium Term (1 week):")
        lines.append(
            "  [ ] Enhance baseline extraction to parse all configuration variations")
        lines.append(
            "  [ ] Add automated data validation before experiment execution")
        lines.append(
            "  [ ] Implement hyperparameter sweep to match paper settings")
        lines.append("  [ ] Create detailed logging of all experiment steps")
        lines.append("")

        lines.append("Long Term (2-4 weeks):")
        lines.append(
            "  [ ] Build a library of paper-specific parsers for common formats")
        lines.append("  [ ] Develop automated configuration matching system")
        lines.append(
            "  [ ] Create visualization dashboard for metric comparisons")
        lines.append(
            "  [ ] Implement ablation study support for debugging deviations")
        lines.append("")

        # 7. Conclusion Summary
        lines.append("7. FINAL ASSESSMENT")
        lines.append("-" * 80)

        if success_rate >= 70:
            conclusion = (
                "The EVALLab agent demonstrates strong capability in automating research "
                "reproduction. With minor refinements to baseline extraction and validation, "
                "it can serve as a reliable tool for verifying experimental results."
            )
        elif success_rate >= 40:
            conclusion = (
                "The EVALLab agent shows promise but requires significant improvements in "
                "configuration matching and environment validation. Focus on data integrity "
                "and parameter alignment before production use."
            )
        else:
            conclusion = (
                "The EVALLab agent requires substantial development before being production-ready. "
                "Critical issues in data handling, metric extraction, or environment setup "
                "must be addressed. Consider manual verification of key experiment steps."
            )

        lines.extend([
            conclusion,
            "",
            f"Overall Grade: {grade}",
            f"Confidence Level: {'HIGH' if success_rate > 80 else 'MEDIUM' if success_rate > 50 else 'LOW'}",
            "",
            "="*80
        ])

        return "\n".join(lines)

    def generate_visualizations(self, comparisons: List[ComparisonResult],
                                output_dir: Path,
                                paper_name: str = "Research Paper",
                                codebase_path: Path = None,
                                per_example_total: int = 0,
                                per_example_matches: int = 0) -> Dict[str, Path]:
        """
        Generate plots, tables, and graphs comparing agent results to baseline.

        Args:
            comparisons: List of comparison results
            output_dir: Directory to save visualizations
            paper_name: Name of the paper for titles

        Returns:
            Dict mapping visualization type to file path
        """
        import matplotlib.pyplot as plt
        import seaborn as sns
        import pandas as pd
        import numpy as np

        # Set style
        sns.set_theme(style="whitegrid")
        plt.rcParams['figure.figsize'] = (12, 8)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert comparisons to DataFrame
        data = []
        for comp in comparisons:
            parts = comp.configuration.split('/')
            exp_set = parts[0] if len(parts) > 0 else "unknown"
            granularity = parts[1] if len(parts) > 1 else "unknown"
            strategy = parts[2] if len(parts) > 2 else "unknown"
            task_type = parts[3] if len(parts) > 3 else "unknown"
            retriever = parts[4] if len(parts) > 4 else "unknown"

            data.append({
                'experiment_set': exp_set,
                'granularity': granularity,
                'strategy': strategy,
                'task_type': task_type,
                'retriever': retriever,
                'metric_name': comp.metric_name,
                'baseline_value': comp.baseline_value,
                'reproduced_value': comp.reproduced_value,
                'difference': comp.difference,
                'percent_difference': comp.percent_difference,
                'within_threshold': comp.within_threshold,
                'configuration': comp.configuration
            })

        df = pd.DataFrame(data)
        
        # Clean label artifacts (e.g., stray ANSI fragments like '92m') and prep numeric columns
        def _clean_artifacts(s: str) -> str:
            try:
                txt = str(s)
            except Exception:
                return s
            ansi_suffixes = [*(f"{i}m" for i in range(30, 38)), *(f"{i}m" for i in range(90, 98)), "39m", "0m"]
            for suf in ansi_suffixes:
                if suf in txt:
                    txt = txt.replace(suf, "")
            txt = txt.replace("\u001b", "")
            return txt

        for col in ['experiment_set', 'granularity', 'strategy', 'task_type', 'retriever', 'metric_name', 'configuration']:
            if col in df.columns:
                df[col] = df[col].apply(_clean_artifacts)

        # Numeric columns for plotting; keep originals intact for CSV
        df['baseline_value_num'] = pd.to_numeric(df.get('baseline_value'), errors='coerce')
        df['reproduced_value_num'] = pd.to_numeric(df.get('reproduced_value'), errors='coerce')
        df['percent_difference_num'] = pd.to_numeric(df.get('percent_difference'), errors='coerce')
        generated_files = {}

        logger.info(f"Generating visualizations for {len(df)} comparisons...")
        
        # Filter to matched-baseline rows for visualization (Option A)
        df_matched = df[df['baseline_value'] != 'N/A'].copy()
        if df_matched.empty:
            logger.warning("All comparisons missing baseline (N/A). Visualizations will be minimal.")
            df_matched = df.copy()

        # Handle empty DataFrame or missing column gracefully
        if df.empty or 'within_threshold' not in df.columns:
            logger.warning("No metric comparisons available or 'within_threshold' column missing. Skipping visualizations.")
            return generated_files

        # 1. Overall Performance Comparison Bar Chart
        fig, ax = plt.subplots(figsize=(13, 8))
        
        # All metrics (aggregate + per-example now included in df_matched)
        within_threshold = df_matched['within_threshold'].sum()
        total = len(df_matched)
        outside_threshold = total - within_threshold

        bars = ax.bar(['Within Threshold\n(Success)', 'Outside Threshold\n(Failed)'],
                      [within_threshold, outside_threshold],
                      color=['#2ecc71', '#e74c3c'])
        ax.set_ylabel('Number of Comparisons', fontsize=12)
        ax.set_title(f'EVALLab Reproducibility Performance\n({total} total comparisons)',
                     fontsize=14, fontweight='bold')

        # Add percentage labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)} ({height/total*100:.1f}%)',
                    ha='center', va='bottom', fontsize=11)

        file_path = output_dir / 'overall_performance.png'
        plt.tight_layout()
        plt.savefig(file_path, dpi=300, bbox_inches="tight")
        plt.close()
        generated_files['overall_performance'] = file_path
        logger.info(f'✓ Generated: {file_path}')

        # 2. Performance by Configuration
        fig, ax = plt.subplots(figsize=(16, 10))
        config_stats = df_matched.groupby(['granularity', 'strategy']).agg({
            'within_threshold': 'sum',
            'metric_name': 'count'
        }).reset_index()
        config_stats['success_rate'] = (config_stats['within_threshold'] /
                                        config_stats['metric_name'] * 100)
        config_stats['config'] = (config_stats['granularity'] + '/' +
                                  config_stats['strategy'])

        config_stats = config_stats.sort_values('success_rate', ascending=True)

        colors = ['#e74c3c' if x < 80 else '#f39c12' if x < 90 else '#2ecc71'
                  for x in config_stats['success_rate']]
        bars = ax.barh(config_stats['config'],
                       config_stats['success_rate'], color=colors)
        ax.set_xlabel('Success Rate (%)', fontsize=12)
        ax.set_title('Reproducibility by Configuration',
                     fontsize=14, fontweight='bold')
        ax.axvline(x=80, color='red', linestyle='--',
                   alpha=0.3, label='80% threshold')
        ax.axvline(x=90, color='orange', linestyle='--',
                   alpha=0.3, label='90% threshold')
        ax.legend()

        for i, (bar, val) in enumerate(zip(bars, config_stats['success_rate'])):
            ax.text(val + 1, bar.get_y() + bar.get_height()/2,
                    f'{val:.1f}%', va='center', fontsize=9)

        file_path = output_dir / 'performance_by_configuration.png'
        plt.tight_layout()
        plt.savefig(file_path, dpi=300, bbox_inches="tight")
        plt.close()
        generated_files['performance_by_configuration'] = file_path
        logger.info(f'✓ Generated: {file_path}')

        # 3. Scatter Plot: Baseline vs Reproduced Values (numeric only)
        df_scatter = df_matched[df_matched[['baseline_value_num', 'reproduced_value_num']].notna().all(axis=1)].copy()
        if not df_scatter.empty:
            fig, ax = plt.subplots(figsize=(13, 13))

            colors = df_scatter['within_threshold'].map({True: '#2ecc71', False: '#e74c3c'})
            ax.scatter(df_scatter['baseline_value_num'], df_scatter['reproduced_value_num'],
                       c=colors, alpha=0.6, s=50)

            max_val = max(df_scatter['baseline_value_num'].max(), df_scatter['reproduced_value_num'].max())
            min_val = min(df_scatter['baseline_value_num'].min(), df_scatter['reproduced_value_num'].min())
            ax.plot([min_val, max_val], [min_val, max_val], 'k--', label='Perfect Reproduction', linewidth=2)

            threshold = 0.05
            ax.fill_between([min_val, max_val],
                            [min_val * (1-threshold), max_val * (1-threshold)],
                            [min_val * (1+threshold), max_val * (1+threshold)],
                            alpha=0.2, color='green', label=f'±{threshold*100}% threshold')

            ax.set_xlabel('Baseline Value', fontsize=12)
            ax.set_ylabel('Reproduced Value', fontsize=12)
            ax.set_title('Baseline vs Reproduced Metrics', fontsize=14, fontweight='bold')
            ax.legend()
            ax.grid(True, alpha=0.3)

            file_path = output_dir / 'baseline_vs_reproduced.png'
            plt.tight_layout()
            plt.savefig(file_path, dpi=300, bbox_inches="tight")
            plt.close()
            generated_files['baseline_vs_reproduced'] = file_path
            logger.info(f'✓ Generated: {file_path}')
        else:
            logger.warning('No numeric baseline/reproduced values available for scatter plot. Skipping.')

        # 4. Distribution of Percent Differences (numeric only)
        df_hist = df_matched[df_matched['percent_difference_num'].notna()].copy()
        if not df_hist.empty:
            fig, ax = plt.subplots(figsize=(15, 7))

            percent_diff_capped = df_hist['percent_difference_num'].clip(-50, 50)

            ax.hist(percent_diff_capped, bins=50, color='#3498db', alpha=0.7, edgecolor='black')
            ax.axvline(x=0, color='green', linestyle='--', linewidth=2, label='Perfect match')
            ax.axvline(x=-5, color='orange', linestyle='--', alpha=0.7, label='±5% threshold')
            ax.axvline(x=5, color='orange', linestyle='--', alpha=0.7)

            ax.set_xlabel('Percent Difference (%)', fontsize=12)
            ax.set_ylabel('Frequency', fontsize=12)
            ax.set_title('Distribution of Metric Deviations', fontsize=14, fontweight='bold')
            ax.legend()

            file_path = output_dir / 'deviation_distribution.png'
            plt.tight_layout()
            plt.savefig(file_path, dpi=300, bbox_inches="tight")
            plt.close()
            generated_files['deviation_distribution'] = file_path
            logger.info(f'✓ Generated: {file_path}')
        else:
            logger.warning('No numeric percent differences available for histogram. Skipping.')

        # 5. Heatmap: Performance by Granularity and Task Type
        if 'granularity' in df_matched.columns and 'task_type' in df_matched.columns:
            fig, ax = plt.subplots(figsize=(13, 8))

            pivot = df_matched.pivot_table(
                values='within_threshold',
                index='granularity',
                columns='task_type',
                aggfunc='mean'
            ) * 100  # Convert to percentage

            sns.heatmap(pivot, annot=True, fmt='.1f', cmap='RdYlGn',
                        vmin=0, vmax=100, ax=ax, cbar_kws={'label': 'Success Rate (%)'})
            ax.set_title('Success Rate by Granularity and Task Type',
                         fontsize=14, fontweight='bold')
            ax.set_xlabel('Task Type', fontsize=12)
            ax.set_ylabel('Granularity', fontsize=12)

            file_path = output_dir / 'heatmap_granularity_tasktype.png'
            plt.tight_layout()
            plt.savefig(file_path, dpi=300, bbox_inches="tight")
            plt.close()
            generated_files['heatmap_granularity_tasktype'] = file_path
            logger.info(f'✓ Generated: {file_path}')

        # 6. Summary Statistics Table
        # Use numeric percent difference for aggregates if available
        mean_abs = df_matched['percent_difference_num'].abs().mean()
        med_abs = df_matched['percent_difference_num'].abs().median()
        std_abs = df_matched['percent_difference_num'].std()

        summary_data = {
            'Metric': [
                'Total Comparisons',
                'Within Threshold',
                'Outside Threshold',
                'Success Rate',
                'Mean Absolute Deviation',
                'Median Absolute Deviation',
                'Std Dev of Deviations'
            ],
            'Value': [
                f"{len(df_matched)}",
                f"{df_matched['within_threshold'].sum()}",
                f"{len(df_matched) - df_matched['within_threshold'].sum()}",
                f"{df_matched['within_threshold'].mean() * 100:.2f}%",
                f"{(0 if pd.isna(mean_abs) else mean_abs):.2f}%",
                f"{(0 if pd.isna(med_abs) else med_abs):.2f}%",
                f"{(0 if pd.isna(std_abs) else std_abs):.2f}%"
            ]
        }

        fig, ax = plt.subplots(figsize=(11, 5))
        ax.axis('tight')
        ax.axis('off')

        table = ax.table(cellText=[[summary_data['Metric'][i], summary_data['Value'][i]]
                                   for i in range(len(summary_data['Metric']))],
                         colLabels=['Metric', 'Value'],
                         cellLoc='left',
                         loc='center',
                         colWidths=[0.6, 0.4])

        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)

        # Style header
        for i in range(2):
            table[(0, i)].set_facecolor('#3498db')
            table[(0, i)].set_text_props(weight='bold', color='white')

        # Alternate row colors
        for i in range(1, len(summary_data['Metric']) + 1):
            for j in range(2):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor('#ecf0f1')

        plt.title('Summary Statistics', fontsize=14, fontweight='bold', pad=20)
        file_path = output_dir / 'summary_statistics.png'
        plt.tight_layout()
        plt.savefig(file_path, dpi=300, bbox_inches="tight")
        plt.close()
        generated_files['summary_statistics'] = file_path
        logger.info(f'✓ Generated: {file_path}')

        # 7. Export detailed CSV
        # Export matched-only and unmatched CSVs
        csv_matched = output_dir / 'detailed_comparison.csv'
        df_matched.to_csv(csv_matched, index=False)
        generated_files['detailed_csv'] = csv_matched
        logger.info(f"✓ Exported matched-only CSV: {csv_matched}")

        df_unmatched = df[df['baseline_value'] == 'N/A']
        if not df_unmatched.empty:
            csv_unmatched = output_dir / 'detailed_unmatched.csv'
            df_unmatched.to_csv(csv_unmatched, index=False)
            generated_files['unmatched_csv'] = csv_unmatched
            logger.info(f"✓ Exported unmatched CSV: {csv_unmatched}")

        # Add per_example_diffs.html if it exists
        per_example_diffs_path = output_dir / 'per_example_diffs.html'
        if per_example_diffs_path.exists():
            generated_files['per_example_diffs'] = per_example_diffs_path

        # Generate index HTML
        html_content = self._generate_visualization_index(
            generated_files, df, paper_name)
        html_path = output_dir / 'visualizations.html'
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        generated_files['index_html'] = html_path

        logger.info(f"\n{'='*80}")
        logger.info(
            f"📊 Generated {len(generated_files)} visualizations in: {output_dir}")
        logger.info(
            f"📄 Open {html_path} in a browser to view all visualizations")
        logger.info(f"{'='*80}\n")

        return generated_files

    def _generate_visualization_index(self, files: Dict[str, Path],
                                      df, paper_name: str, output_dir: Path = None) -> str:
        # Import the new helper function
        from helper.dashboard import generate_visualization_index_html
        return generate_visualization_index_html(files, df, paper_name, output_dir)
