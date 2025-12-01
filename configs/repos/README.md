# Repository Configuration Schema
#
# This file defines the structure for repo-specific configurations.
# Each repo can specify custom handling for dependencies, experiments, and baselines.

name: string                    # Unique identifier (e.g., "AIX360", "TextAttack")
path_pattern: string            # Pattern to match repo path (case-insensitive)

# Dependencies
dependencies:
  - package_name                # List of pip packages to install
  - "package_name<version"      # Can include version constraints

# Pre-run setup commands
pre_run_setup:
  - type: "patch_file"          # Patch deprecated imports
    file: "path/to/file.py"
    search: "old import"
    replace: "new import"
  - type: "run_command"         # Run custom command
    command: "pip install extra_package"
    working_dir: "."

# Experiment configuration
experiments:
  - name: "main_test"           # Experiment identifier
    type: "pytest"              # Type: pytest, shell_script, python_script
    path: "tests/test_main.py"  # Path to test/script
    args: []                    # Command-line arguments
    timeout: 600                # Timeout in seconds
    
  - name: "metrics_extraction"
    type: "python_script"
    path: "run_metrics.py"
    generate: true              # Auto-generate this script
    template: "rbm_metrics"     # Template name for generation

# Baseline strategy
baseline:
  strategy: "double_run"        # Options: double_run, paper_metrics, none
  save_baseline: true           # Whether to save Run 1 as baseline
  baseline_file: "paper_metrics.json"
  comparison_file: "log.csv"    # For per-example comparisons

# Metrics extraction
metrics:
  per_example: false            # Whether repo supports per-example metrics
  extractors:                   # Custom metric extraction patterns
    - pattern: "Accuracy:\\s+([0-9.]+)"
      name: "accuracy"
    - pattern: "F1 Score:\\s+([0-9.]+)"
      name: "f1_score"

# Output handling
outputs:
  log_file: "log.csv"           # Expected log file location
  results_file: "complete_results.json"
