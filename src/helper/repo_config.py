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


def list_supported_repos() -> List[str]:
    """Return list of supported repository names."""
    return sorted(REPO_REGISTRY.keys())


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
