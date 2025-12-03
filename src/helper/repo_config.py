"""
Repository-specific configuration system for EVALLab.

Centralizes all hardcoded repo handling logic from pipeline.py into
declarative YAML configurations. Each repo can specify:
- Custom dependencies and version constraints
- Pre-run patches and fixes
- Experiment runners and metric extraction
- Baseline comparison strategies

Configurations are stored in configs/repos/ as YAML files.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
import logging
import yaml
import subprocess
import json
import re

logger = logging.getLogger(__name__)

# Get configs directory (relative to this file's location)
CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs" / "repos"


@dataclass
class RepoConfig:
    """Configuration for a specific research repository (loaded from YAML)."""
    
    name: str
    """Unique identifier for this repo (e.g., 'decontextualization')"""
    
    path_pattern: str
    """Pattern to match repo path (e.g., 'decontextualization')"""
    
    dependencies: List[str] = field(default_factory=list)
    """Extra dependencies to install before running experiments"""
    
    pre_run_setup: List[Dict[str, Any]] = field(default_factory=list)
    """Pre-run setup actions (patches, commands, etc.)"""
    
    experiments: List[Dict[str, Any]] = field(default_factory=list)
    """Experiment configurations"""
    
    baseline: Dict[str, Any] = field(default_factory=dict)
    """Baseline strategy configuration"""
    
    metrics: Dict[str, Any] = field(default_factory=dict)
    """Metrics extraction configuration"""
    
    outputs: Dict[str, str] = field(default_factory=dict)
    """Output file locations"""
    
    data_validation: Dict[str, Any] = field(default_factory=dict)
    """Data validation configuration (optional)"""
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> 'RepoConfig':
        """Load configuration from YAML file."""
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        return cls(
            name=data.get('name', ''),
            path_pattern=data.get('path_pattern', ''),
            dependencies=data.get('dependencies', []),
            pre_run_setup=data.get('pre_run_setup', []),
            experiments=data.get('experiments', []),
            baseline=data.get('baseline', {}),
            metrics=data.get('metrics', {}),
            outputs=data.get('outputs', {}),
            data_validation=data.get('data_validation', {})
        )


def load_all_configs() -> Dict[str, RepoConfig]:
    """Load all YAML configurations from configs/repos/ directory."""
    configs = {}
    
    if not CONFIGS_DIR.exists():
        logger.warning(f"Config directory not found: {CONFIGS_DIR}")
        return configs
    
    for yaml_file in CONFIGS_DIR.glob("*.yaml"):
        if yaml_file.name == "README.md":
            continue
        
        try:
            config = RepoConfig.from_yaml(yaml_file)
            configs[config.name] = config
            logger.debug(f"Loaded config for {config.name} from {yaml_file.name}")
        except Exception as e:
            logger.error(f"Failed to load config {yaml_file.name}: {e}")
    
    return configs


# Load all configs at module import
REPO_REGISTRY = load_all_configs()


def llm_generate_repo_config(
    llm_client: Any,
    codebase_path: Path,
    readme_commands: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None
) -> Optional[RepoConfig]:
    """
    Use LLM to analyze codebase and generate a RepoConfig automatically.
    
    Args:
        llm_client: LLM client for analysis (must have query_llm method)
        codebase_path: Path to the codebase root
        readme_commands: Optional pre-parsed README commands from parse_readme_commands()
        logger: Logger instance
        
    Returns:
        Generated RepoConfig or None if generation fails
    """
    if not llm_client:
        return None
    
    log = logger or logging.getLogger(__name__)
    
    try:
        # Gather codebase context
        repo_name = codebase_path.name
        
        # Read README if available and not pre-parsed
        readme_content = ""
        readme_names = ['README.md', 'README.txt', 'README', 'readme.md', 'Readme.md']
        for name in readme_names:
            readme_path = codebase_path / name
            if readme_path.exists():
                try:
                    readme_content = readme_path.read_text(encoding='utf-8', errors='ignore')[:3000]
                    break
                except Exception:
                    continue
        
        # Scan for Python files, requirements, setup files
        python_files = list(codebase_path.rglob("*.py"))[:20]  # Limit to first 20
        
        # Find main scripts with their ACTUAL relative paths
        main_scripts = []
        for f in python_files:
            if 'main' in f.name.lower() or 'run' in f.name.lower() or 'train' in f.name.lower():
                rel_path = f.relative_to(codebase_path)
                main_scripts.append(str(rel_path))
        
        has_requirements = (codebase_path / 'requirements.txt').exists()
        has_setup_py = (codebase_path / 'setup.py').exists()
        
        # Read requirements if available
        dependencies_list = []
        if has_requirements:
            try:
                reqs = (codebase_path / 'requirements.txt').read_text()
                dependencies_list = [line.strip() for line in reqs.split('\n') if line.strip() and not line.startswith('#')][:15]
            except Exception:
                pass
        
        # Get directory structure (limited depth)
        def get_tree(path: Path, max_depth: int = 2, current_depth: int = 0) -> str:
            if current_depth >= max_depth:
                return ""
            lines = []
            try:
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                for item in items[:12]:
                    if item.name.startswith('.'):
                        continue
                    prefix = "  " * current_depth
                    if item.is_dir():
                        lines.append(f"{prefix}{item.name}/")
                        lines.append(get_tree(item, max_depth, current_depth + 1))
                    else:
                        lines.append(f"{prefix}{item.name}")
            except PermissionError:
                pass
            return "\n".join(filter(None, lines))
        
        dir_tree = get_tree(codebase_path, max_depth=3)
        
        # Scan for output/result files and markdown documentation
        output_files = []
        markdown_docs = []
        
        # Find result/output JSON files
        for pattern in ['**/results*.json', '**/complete_results.json', '**/output*.json', '**/metrics*.json']:
            for f in codebase_path.glob(pattern):
                if 'venv' not in str(f) and '.venv' not in str(f):
                    rel_path = f.relative_to(codebase_path)
                    output_files.append(str(rel_path))
                    if len(output_files) >= 5:
                        break
        
        # Find markdown files (excluding venv)
        for md_file in codebase_path.rglob('*.md'):
            if 'venv' not in str(md_file) and '.venv' not in str(md_file):
                # Read first 500 chars to see if it mentions outputs
                try:
                    content = md_file.read_text(encoding='utf-8', errors='ignore')[:500]
                    if any(keyword in content.lower() for keyword in ['output', 'result', 'report', 'metrics']):
                        rel_path = md_file.relative_to(codebase_path)
                        markdown_docs.append({
                            'path': str(rel_path),
                            'snippet': content[:300]
                        })
                        if len(markdown_docs) >= 3:
                            break
                except Exception:
                    pass
        
        output_files_info = "\n".join(f"  - {f}" for f in output_files) if output_files else "None found"
        markdown_info = ""
        if markdown_docs:
            markdown_info = "\n\nMarkdown files mentioning outputs:\n"
            for doc in markdown_docs:
                markdown_info += f"\n{doc['path']}:\n{doc['snippet']}...\n"
        
        # Build LLM prompt
        readme_info = f"\nREADME Content:\n```\n{readme_content}\n```\n" if readme_content else ""
        readme_cmds_info = ""
        if readme_commands:
            readme_cmds_info = f"\nParsed README Commands:\n{json.dumps(readme_commands, indent=2)}\n"
        
        prompt = f"""You are analyzing a research paper's codebase to generate a configuration file.

Repository: {repo_name}
Directory Structure:
```
{dir_tree}
```

Main Scripts Found: {', '.join(main_scripts) if main_scripts else 'None'}
Has requirements.txt: {has_requirements}
Has setup.py: {has_setup_py}
{readme_info}{readme_cmds_info}

Dependencies List:
{chr(10).join(dependencies_list[:10]) if dependencies_list else 'None found'}

Output/Result Files Found:
{output_files_info}{markdown_info}

Generate a YAML configuration in this EXACT format:

{{
  "name": "{repo_name}",
  "path_pattern": "{repo_name.lower()}",
  "dependencies": ["package1>=1.0.0", "package2>=2.0.0"],
  "pre_run_setup": [],
  "experiments": [
    {{
      "name": "main_experiment",
      "type": "python_script",
      "path": "main.py",
      "args": ["--config", "config.yaml"],
      "timeout": 1200,
      "description": "Main experiment description"
    }}
  ],
  "baseline": {{
    "save_baseline": true,
    "baseline_file": "paper_metrics.json"
  }},
  "metrics": {{
    "per_example": false,
    "extractors": [
      {{"pattern": "Accuracy[=:]\\\\s*([0-9.]+)", "name": "accuracy"}},
      {{"pattern": "F1[=:]\\\\s*([0-9.]+)", "name": "f1_score"}}
    ]
  }},
  "outputs": {{
    "results_file": "results.json",
    "report_file": "report.md"
  }},
  "data_validation": {{
    "data_dir": "data",
    "required_files": []
  }}
}}

IMPORTANT:
1. For the experiment path, use EXACTLY one of these main scripts WITH THE SAME RELATIVE PATH shown (do not add or remove directories):
    {', '.join(main_scripts) if main_scripts else 'None'}
2. Include all dependencies from requirements.txt
3. Extract metric patterns from README (look for evaluation metrics like Accuracy, F1, Recall, MRR)
4. For outputs.results_file and outputs.report_file, use the ACTUAL paths found in "Output/Result Files Found" section
5. If complete_results.json is found, use its actual path (e.g., "code/outputs_all_methods/complete_results.json")
6. Return ONLY valid JSON, no markdown formatting
7. DO NOT modify the script paths - use them EXACTLY as listed in "Main Scripts Found"

Return ONLY the JSON configuration:"""

        response = llm_client.query_llm(prompt)
        if not response:
            log.warning("LLM returned empty response for config generation")
            return None
        
        # Extract JSON from response
        def extract_json(text: str) -> Optional[Dict]:
            """Extract JSON from LLM response."""
            # Try direct parse
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
            
            # Try finding JSON block
            patterns = [
                r'```json\s*(.*?)\s*```',
                r'```\s*(.*?)\s*```',
                r'\{.*\}',
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1) if '```' in pattern else match.group(0))
                    except json.JSONDecodeError:
                        continue
            return None
        
        config_data = extract_json(response)
        if not config_data or not isinstance(config_data, dict):
            log.warning("Failed to parse LLM response as JSON")
            return None
        
        # Convert JSON to RepoConfig
        config = RepoConfig(
            name=config_data.get('name', repo_name),
            path_pattern=config_data.get('path_pattern', repo_name.lower()),
            dependencies=config_data.get('dependencies', []),
            pre_run_setup=config_data.get('pre_run_setup', []),
            experiments=config_data.get('experiments', []),
            baseline=config_data.get('baseline', {'save_baseline': True, 'baseline_file': 'paper_metrics.json'}),
            metrics=config_data.get('metrics', {'per_example': False, 'extractors': []}),
            outputs=config_data.get('outputs', {'results_file': 'results.json', 'report_file': 'report.md'}),
            data_validation=config_data.get('data_validation', {'data_dir': 'data', 'required_files': []})
        )
        
        log.info(f"✓ LLM generated config for {repo_name}")
        log.debug(f"  Experiments: {len(config.experiments)}")
        log.debug(f"  Dependencies: {len(config.dependencies)}")
        
        return config
        
    except Exception as e:
        if logger:
            logger.error(f"Failed to generate config with LLM: {e}")
        return None


def save_repo_config(config: RepoConfig, output_path: Optional[Path] = None) -> bool:
    """
    Save a RepoConfig to YAML file.
    
    Args:
        config: RepoConfig to save
        output_path: Optional custom path, defaults to configs/repos/{name}.yaml
        
    Returns:
        True if saved successfully
    """
    try:
        if output_path is None:
            output_path = CONFIGS_DIR / f"{config.name.lower()}.yaml"
        
        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict
        config_dict = {
            'name': config.name,
            'path_pattern': config.path_pattern,
            'dependencies': config.dependencies,
            'pre_run_setup': config.pre_run_setup,
            'experiments': config.experiments,
            'baseline': config.baseline,
            'metrics': config.metrics,
            'outputs': config.outputs,
            'data_validation': config.data_validation
        }
        
        # Write YAML
        with open(output_path, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False, indent=2)
        
        logger.info(f"✓ Saved config to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def generate_repo_config_from_filesystem(codebase_path: Path) -> RepoConfig:
    """Generate a minimal RepoConfig by inspecting the filesystem (no LLM required).

    - Detect entry script under `code/` if present, else top-level scripts
    - Detect output directories with `complete_results.json`
    - Prefer `outputs_all_methods` paths for results/report hints
    """
    repo_name = codebase_path.name

    # Determine prefix if codebase_path is a 'code' directory
    prefix = ""
    if codebase_path.name == "code":
        prefix = "code/"

    # Find entry script
    entry_candidates = ["main_local_all_new.py", "main.py", "run.py", "experiment.py"]
    entry_point = None
    for name in entry_candidates:
        candidate = codebase_path / name
        if candidate.exists():
            entry_point = f"{prefix}{name}"
            break

    # Detect outputs dirs
    outputs_dirs = [d for d in codebase_path.iterdir() if d.is_dir() and (d / "complete_results.json").exists()]
    # Choose primary methods dir
    methods_dir = (
        next((d for d in outputs_dirs if d.name == "outputs_all_methods"), None)
        or next((d for d in outputs_dirs if "methods" in d.name), None)
    )

    results_file = None
    report_file = None
    if methods_dir:
        if (methods_dir / "complete_results.json").exists():
            results_file = f"{prefix}{methods_dir.name}/complete_results.json"
        if (methods_dir / "report.md").exists():
            report_file = f"{prefix}{methods_dir.name}/report.md"

    outputs = {}
    if results_file:
        outputs["results_file"] = results_file
    if report_file:
        outputs["report_file"] = report_file

    experiments = []
    if entry_point:
        experiments.append({
            "name": "main_experiment",
            "type": "python_script",
            "path": entry_point,
            "args": [],
            "timeout": 1800,
            "description": "Auto-detected entry point"
        })

    return RepoConfig(
        name=repo_name,
        path_pattern=repo_name.lower(),
        dependencies=[],
        pre_run_setup=[],
        experiments=experiments,
        baseline={"save_baseline": True, "baseline_file": "paper_metrics.json"},
        metrics={"per_example": False, "extractors": []},
        outputs=outputs,
        data_validation={"data_dir": "data", "required_files": []}
    )


def get_repo_config(repo_path: Path) -> Optional[RepoConfig]:
    """
    Match a repo path to a configuration.
    
    Args:
        repo_path: Path to the repository
        
    Returns:
        RepoConfig if matched, None otherwise
    """
    repo_name = repo_path.name
    
    for config in REPO_REGISTRY.values():
        if config.path_pattern.lower() in repo_name.lower():
            logger.debug(f"Matched repo {repo_name} to config {config.name}")
            return config
    
    logger.debug(f"No config found for repo {repo_name}")
    return None


# Removed unused function: list_supported_repos


# ============================================================================
# Execution Helpers
# ============================================================================

def execute_pre_run_setup(config: RepoConfig, repo_path: Path, logger: logging.Logger) -> None:
    """Execute pre-run setup actions defined in config."""
    
    # Install dependencies
    if config.dependencies:
        venv_python = repo_path / "venv" / "bin" / "python"
        if venv_python.exists():
            logger.info(f"  Installing dependencies: {', '.join(config.dependencies)}")
            for dep in config.dependencies:
                try:
                    subprocess.run(
                        [str(venv_python), "-m", "pip", "install", dep],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to install {dep}: {e}")
    
    # Execute setup actions
    for action in config.pre_run_setup:
        action_type = action.get('type')
        
        if action_type == 'patch_file':
            file_path = repo_path / action['file']
            if file_path.exists():
                try:
                    content = file_path.read_text()
                    search = action['search']
                    replace = action['replace']
                    
                    if search in content:
                        patched = content.replace(search, replace)
                        file_path.write_text(patched)
                        logger.info(f"  → Patched {action['file']}: {action.get('description', '')}")
                except Exception as e:
                    logger.warning(f"  ⚠ Failed to patch {action['file']}: {e}")
        
        elif action_type == 'run_command':
            try:
                working_dir = repo_path / action.get('working_dir', '.')
                result = subprocess.run(
                    action['command'],
                    shell=True,
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    logger.info(f"  → Ran command: {action['command']}")
                else:
                    logger.warning(f"  ⚠ Command failed: {result.stderr[:200]}")
            except Exception as e:
                logger.warning(f"  ⚠ Failed to run command: {e}")


def execute_experiments(config: RepoConfig, repo_path: Path, logger: logging.Logger, executor: Any) -> List[Dict[str, Any]]:
    """Execute experiments defined in config."""
    results = []
    
    for exp in config.experiments:
        exp_name = exp.get('name', 'unnamed')
        exp_type = exp.get('type')
        exp_path = repo_path / exp['path']
        
        # Generate script if needed
        if exp.get('generate', False) and 'template' in exp:
            try:
                exp_path.write_text(exp['template'])
                exp_path.chmod(0o755)
                logger.info(f"  → Generated {exp_path.name}")
            except Exception as e:
                logger.warning(f"  ⚠ Failed to generate {exp_path.name}: {e}")
                continue
        
        # Run experiment
        actual_path = exp_path
        logger.info(f"  → Running {exp_name}: {exp_path.name}")
        
        try:
            from src.experiment_executor import ExperimentConfig
            
            exp_config = ExperimentConfig(
                script_path=actual_path,
                args=exp.get('args', []),
                env_vars={},
                working_dir=repo_path,
                timeout=exp.get('timeout', 600),
                metrics_config=config.metrics  # Pass metrics config from YAML
            )
            
            result = executor.run_experiment(exp_config)
            results.append(result)
            
            if result.success:
                logger.info(f"  ✓ {exp_name} complete (duration: {result.duration:.2f}s)")
            else:
                logger.warning(f"  ✗ {exp_name} failed")
        except Exception as e:
            logger.error(f"  ✗ Failed to run {exp_name}: {e}")
        finally:
            # Clean up temp file if created
            if actual_path != exp_path and actual_path.exists():
                try:
                    actual_path.unlink()
                except OSError:
                    pass  # Ignore cleanup failures
    
    return results
