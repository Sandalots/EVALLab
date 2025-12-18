"""===============================================================================
EVALLAB STAGE 3/4: EXPERIMENT EXECUTION

Analyzes codebase, sets up isolated environment, runs experiments.
Outputs reproduced metrics (JSON) for Stage 4 (Result Evaluation).
===============================================================================
"""

import os
import platform
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import json
import time
import shutil
import traceback
from datetime import datetime
import threading
import re


logger = logging.getLogger(__name__)

def _get_python_executable():
    """Get the appropriate Python executable for the current platform."""
    if platform.system() == 'Windows':

        # Try python first, then py launcher
        for cmd in ['python', 'py']:

            try:
                result = subprocess.run(
                    [cmd, '--version'], capture_output=True, text=True)
                
                if result.returncode == 0:
                    return cmd
                
            except FileNotFoundError:
                continue

        return 'python'  # fallback
    
    else:
        # Unix/macOS - prefer python3
        return 'python3'


def _get_venv_paths(venv_path: Path):
    """Get platform-specific paths for venv executables.

    Returns:
        Tuple of (python_executable, pip_executable, scripts_dir)
    """
    if platform.system() == 'Windows':
        scripts_dir = venv_path / 'Scripts'
        python_exe = scripts_dir / 'python.exe'
        pip_exe = scripts_dir / 'pip.exe'

    else:
        scripts_dir = venv_path / 'bin'
        python_exe = scripts_dir / 'python'
        pip_exe = scripts_dir / 'pip'

    return python_exe, pip_exe, scripts_dir


@dataclass
class CodebaseInfo:
    """Information about a codebase."""
    path: Path
    language: str
    entry_points: List[Path]
    dependencies: List[str]
    readme_content: Optional[str] = None


@dataclass
class ExperimentConfig:
    """Configuration for running an experiment."""
    script_path: Path
    args: List[str]
    env_vars: Dict[str, str]
    working_dir: Path
    timeout: int = 3600  # 1 hour default
    metrics_config: Optional[Dict[str, Any]] = None  # Metrics extraction config from YAML


@dataclass
class ExperimentResult:
    """Results from running an experiment."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    duration: float
    outputs: Dict[str, Any] = None

    def __post_init__(self):
        if self.outputs is None:
            self.outputs = {}


class ExperimentExecutor:
    """Analyze codebase and execute experiments - Stage 3 of the agent."""

    def _collect_outputs(self, working_dir: Path) -> dict:
        """Collect output files from experiment execution."""
        outputs = {}

        # Look for common output patterns
        output_patterns = ('output*.json', 'results*.json', '*.json')

        for pattern in output_patterns:
            for output_file in working_dir.glob(pattern):
                
                # Skip baseline_metrics.json - it's for comparison, not experiment output
                if output_file.name == 'baseline_metrics.json':
                    continue

                try:
                    with open(output_file, 'r') as f:
                        outputs[output_file.name] = json.load(f)

                except Exception as e:
                    self.logger.debug(f"Could not parse {output_file}: {e}")

        return outputs

    def __init__(self, config=None, paper_name=None):
        """
        Initialize experiment executor.

        Args:
            config: Configuration dict from config.yaml
            paper_name: Name of the paper for per-paper logging
        """
        self.config = config or {}
        self.logger = logger

        if paper_name:
            log_filename = f"agent_execution_{paper_name}.log"
            file_handler = logging.FileHandler(log_filename)
            file_handler.setFormatter(logging.Formatter(
                '{asctime} {levelname}: {message}', style='{'))
            
            self.logger.addHandler(file_handler)

    # ============================================================================
    # PART 1: CODEBASE ANALYSIS
    # ============================================================================

    def analyze_codebase(self, codebase_path: Path) -> CodebaseInfo:
        """
        Analyze a codebase to extract structure and metadata.

        Args:
            codebase_path: Path to the codebase directory

        Returns:
            CodebaseInfo object with analysis results
        """
        if not codebase_path.exists():
            raise ValueError(f"Codebase path does not exist: {codebase_path}")

        logger.info(f"Analyzing codebase at: {codebase_path}")

        # Detect primary language
        language = self._detect_language(codebase_path)
        logger.info(f"  Detected language: {language}")

        # Find entry points (main scripts, train scripts, etc.)
        entry_points = self._find_entry_points(codebase_path, language)
        logger.info(f"  Found {len(entry_points)} entry point(s)")

        # Extract dependencies
        dependencies = self._extract_dependencies(codebase_path, language)
        logger.info(f"  Found {len(dependencies)} dependencies")

        # Read README if available
        readme_content = self._read_readme(codebase_path)

        return CodebaseInfo(
            path=codebase_path,
            language=language,
            entry_points=entry_points,
            dependencies=dependencies,
            readme_content=readme_content
        )

    def _detect_language(self, path: Path) -> str:
        """Detect the primary programming language of the codebase."""
        extensions = {}

        for file_path in path.rglob('*'):
            if file_path.is_file() and not any(p.startswith('.') for p in file_path.parts):
                ext = file_path.suffix.lower()
                extensions[ext] = extensions.get(ext, 0) + 1

        # Map extensions to languages
        lang_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust',
            '.r': 'r',
            '.jl': 'julia'
        }

        for ext, lang in lang_map.items():
            if ext in extensions:
                return lang

        return 'unknown'

    def _find_entry_points(self, path: Path, language: str) -> List[Path]:
        """Find potential entry point scripts (main, train, experiment, etc.)."""
        entry_patterns = [
            'main*.py', 'train*.py', 'run*.py', 'experiment*.py',
            'evaluate*.py', 'test*.py'
        ]

        entry_points = []

        # Recursively search for entry points, excluding unwanted dirs
        exclude_dirs = {'venv', 'env', 'site-packages', '__pycache__'}

        for pattern in entry_patterns:
            entry_points.extend([
                match for match in path.rglob(pattern)

                if match.is_file() and match not in entry_points
                and not any(part.startswith('.') or part in exclude_dirs for part in match.parts)
            ])

        # Sort by likelihood (evaluate > test > main > run > train > experiment)
        priority_order = ('evaluate', 'test', 'main', 'run', 'train', 'experiment')

        def sort_key(p: Path):
            name = p.stem.lower()
            for i, prefix in enumerate(priority_order):

                if name.startswith(prefix):
                    return i
                
            return len(priority_order)

        entry_points.sort(key=sort_key)

        return entry_points

    def _extract_dependencies(self, path: Path, language: str) -> List[str]:
        """Extract project dependencies from requirements files and entry script imports."""
        dependencies = []

        # Auto-detect additional dependencies from entry script imports
        entry_points = self._find_entry_points(path, language)

        if entry_points:
            main_script = entry_points[0]

            try:
                code = Path(main_script).read_text(encoding='utf-8')
                import_lines = [line for line in code.splitlines() if line.strip(
                ).startswith(('import', 'from'))]

                import_text = ' '.join(import_lines)
                dependencies_set = set(dependencies)

                for dep in ('numpy', 'matplotlib', 'torch', 'torchvision'):
                        if dep in import_text and dep not in dependencies_set:
                            dependencies.append(dep)
                            dependencies_set.add(dep)

            except OSError as e:
                self.logger.warning(f"Error auto-detecting dependencies from entry script: {e}")

        if language == 'python':
            req_files = [
                'requirements.txt',
                'floyd_requirements.txt',
                'requirements-dev.txt',
                'requirements-prod.txt',
                'requirements_test.txt',
            ]
            found_req = False
            for req_name in req_files:
                req_file = path / req_name

                if req_file.exists():
                    found_req = True
                    self.logger.info(
                        f"✓ Found requirements file: {req_file.name}")
                    
                    try:
                        with open(req_file) as f:
                            dependencies_set = set(dependencies)

                            for line in f:
                                line = line.strip()

                                if line and not line.startswith('#'):
                                    dep = line.split('#')[0].strip()

                                    if dep and dep not in dependencies_set:
                                        dependencies.append(dep)
                                        dependencies_set.add(dep)

                    except Exception as e:
                        self.logger.warning(
                            f"Error reading {req_file.name}: {e}")

            setup_file = path / 'setup.py'

            if setup_file.exists():
                try:
                    content = setup_file.read_text(encoding='utf-8')

                    if 'install_requires' in content:
                        self.logger.debug("Found install_requires in setup.py")

                except OSError as e:
                    self.logger.warning(f"Error reading setup.py: {e}")

            # If no requirements.txt, parse README for PyTorch
            if not found_req:
                readme_path = path / 'README.md'

                if readme_path.exists():
                    try:
                        readme = readme_path.read_text(encoding='utf-8').lower()

                        if 'pytorch' in readme or 'torchvision' in readme:
                            self.logger.info(
                                "✓ README mentions PyTorch, adding torch and torchvision to dependencies")
                            
                            if 'torch' not in dependencies:
                                dependencies.append('torch')

                            if 'torchvision' not in dependencies:
                                dependencies.append('torchvision')

                    except OSError as e:
                        self.logger.warning(f"Error reading README.md: {e}")

        return dependencies

    def _read_readme(self, path: Path) -> Optional[str]:
        """Read README file if available."""
        readme_names = ['README.md', 'README.txt', 'README', 'readme.md']

        for name in readme_names:
            readme_path = path / name

            if readme_path.exists():
                try:
                    return readme_path.read_text(encoding='utf-8')
                
                except Exception as e:
                    logger.warning(f"Error reading {name}: {e}")

        return None

    # ============================================================================
    # PART 2: ENVIRONMENT SETUP & VALIDATION
    # ============================================================================

    def validate_data_integrity(self, codebase_path: Path, validation_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Validate dataset files before running experiments.

        Args:
            codebase_path: Path to codebase
            validation_config: Optional dict with validation rules from YAML config

        Returns:
            Dict with validation results
        """
        results = {
            'valid': True,
            'warnings': [],
            'file_stats': {}
        }

        # If no validation config provided, skip validation
        if not validation_config:
            return results

        data_dir = codebase_path / validation_config.get('data_dir', 'data')
        
        if not data_dir.exists():
            results['valid'] = False
            results['warnings'].append(f"Data directory not found: {data_dir}")

            return results

        # Get required files from config
        required_files = validation_config.get('required_files', [])
        
        for file_config in required_files:
            filename = file_config['filename']
            min_lines = file_config.get('min_lines', 0)
            description = file_config.get('description', filename)
            filepath = data_dir / filename

            if not filepath.exists():
                results['warnings'].append(
                    f"Missing {description}: {filename}")
                continue

            try:
                line_count = sum(1 for _ in open(
                    filepath, 'r', encoding='utf-8'))
                
                file_size = filepath.stat().st_size

                results['file_stats'][filename] = {
                    'lines': line_count,
                    'size_mb': file_size / (1024 * 1024),
                    'exists': True
                }

                if min_lines > 0 and line_count < min_lines:
                    results['warnings'].append(
                        f"⚠️  {filename} has only {line_count} lines "
                        f"(expected >{min_lines})"
                    )
                else:
                    logger.info(
                        f"✓ {filename}: {line_count} lines, {file_size/(1024*1024):.1f}MB")

            except Exception as e:
                results['warnings'].append(f"Error reading {filename}: {e}")
                results['file_stats'][filename] = {'error': str(e)}

        if results['warnings']:
            logger.warning(
                f"Data validation found {len(results['warnings'])} issues")
        else:
            logger.info("✓ Data validation passed")

        return results

    def setup_environment(self, codebase_path: Path, dependencies: List[str]) -> bool:
        """
        Set up the environment for running experiments.

        Args:
            codebase_path: Path to the codebase
            dependencies: List of dependencies to install

        Returns:
            True if setup successful
        """
        logger.info(f"Setting up environment for {codebase_path}")

        # Check if virtual environment exists
        venv_path = codebase_path / 'venv'
        venv_exists = venv_path.exists()
        requirements_path = codebase_path / 'requirements.txt'

        # Check if venv is already set up and dependencies installed
        venv_ready = False

        if venv_exists:
            python_executable, _, _ = _get_venv_paths(venv_path)

            # Check if python executable is actually accessible (not a broken symlink)
            if not python_executable.exists():
                logger.warning(f"Virtual environment exists but python executable is broken. Recreating venv...")
                shutil.rmtree(venv_path)
                venv_exists = False

            elif requirements_path.exists():
                logger.info("Installing all dependencies from requirements.txt in venv...")

                try:
                    result = subprocess.run(
                        [str(python_executable), '-m', 'pip', 'install', '-r', str(requirements_path)],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=1800
                    )
                    logger.info("✓ Installed all requirements from requirements.txt")
                    venv_ready = True

                except subprocess.CalledProcessError as e:
                    logger.error(f"✗ Failed to install requirements.txt: {e.stderr}")
                    return False
                
                except subprocess.TimeoutExpired:
                    logger.error(f"✗ Timeout installing requirements.txt after 30 minutes")
                    return False

        if not venv_exists:
            logger.info("Creating virtual environment...")

            # Try python3.10, then python3.11, then error if neither is found
            python_versions = ["python3.10", "python3.11"]
            python_cmd = None

            for py in python_versions:
                try:
                    result = subprocess.run([py, '--version'], capture_output=True, text=True)

                    if result.returncode == 0:
                        python_cmd = py
                        break

                except FileNotFoundError:
                    continue

            if not python_cmd:
                logger.error("Python 3.10 or 3.11 is required but not found in PATH. Please install one of these versions.")
                return False
            
            try:
                subprocess.run(
                    [python_cmd, '-m', 'venv', str(venv_path)],
                    check=True,
                    capture_output=True
                )

            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to create virtual environment: {e}")
                return False
            
        # Environment setup complete

        # Install dependencies if not already installed
        if dependencies and not venv_ready:
            python_executable, _, _ = _get_venv_paths(venv_path)

            logger.info(f"Installing {len(dependencies)} dependencies...")
            logger.info("⏳ This may take a few minutes depending on package sizes...")
            logger.info(f"   (Timeout: 30 minutes)")

            for dep in dependencies:
                logger.info(f"→ Installing: {dep}")
                try:
                    result = subprocess.run(
                        [str(python_executable), '-m', 'pip', 'install', dep],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=1800  # 30 minute timeout
                    )
                    logger.info(f"✓ Installed: {dep}")

                except subprocess.CalledProcessError as e:
                    logger.error(f"✗ Failed to install {dep}: {e.stderr}")
                    return False
                
                except subprocess.TimeoutExpired:
                    logger.error(f"✗ Timeout installing {dep} after 30 minutes")
                    return False
                
            logger.info("✓ All dependencies installed successfully")

        # Always install the repo as a package if setup.py or pyproject.toml is present
        python_executable, _, _ = _get_venv_paths(venv_path)
        setup_py = codebase_path / 'setup.py'
        pyproject = codebase_path / 'pyproject.toml'

        if setup_py.exists() or pyproject.exists():
            logger.info("Installing repo as a package in its venv (pip install -e .)")
            try:
                result = subprocess.run(
                    [str(python_executable), '-m', 'pip', 'install', '-e', str(codebase_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=600
                )

                logger.info("✓ Installed repo as editable package")

            except subprocess.CalledProcessError as e:
                logger.error(f"✗ Failed to install repo as package: {e.stderr}")
                return False
            
            except subprocess.TimeoutExpired:
                logger.error(f"✗ Timeout installing repo as package after 10 minutes")
                return False


    # ============================================================================
    # PART 3: EXPERIMENT EXECUTION
    # ============================================================================

    def run_experiment(self, config: ExperimentConfig) -> ExperimentResult:
        """
        Run a single experiment with the given configuration.

        Args:
            config: Experiment configuration

        Returns:
            ExperimentResult with outputs and status
        """

        self.logger.info(f"[run_experiment] Starting experiment: {config.script_path}")
        self.logger.info(f"[run_experiment] Command: {config.script_path}")
        self.logger.info(f"[run_experiment] Args: {config.args}")
        self.logger.info(f"[run_experiment] Working directory: {config.working_dir if config.working_dir else config.script_path.parent}")
        self.logger.info(f"[run_experiment] Environment variables: {config.env_vars}")

        start_time = time.time()
        start_time_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f"[run_experiment] Start time: {start_time_str}")

        # Ensure script_path is absolute
        # If script_path is relative, resolve it relative to working_dir, not current working directory
        script_path = config.script_path

        if not script_path.is_absolute():
            # Resolve relative to working_dir first
            working_dir = Path(config.working_dir) if config.working_dir else Path.cwd()

            if not working_dir.is_absolute():
                # If working_dir is also relative, resolve it first
                working_dir = working_dir.resolve()

            script_path = working_dir / script_path

        script_path = script_path.resolve()

        # Robust venv detection: prefer repo venvs (venv or .venv), fallback to workspace .venv, then system python
        def find_python_in_venvs(base_dirs):
            venv_names = ('venv', '.venv')

            for base_dir in base_dirs:
                for venv_name in venv_names:
                    venv_path = base_dir / venv_name

                    if platform.system() == 'Windows':
                        py = venv_path / 'Scripts' / 'python.exe'

                    else:
                        py = venv_path / 'bin' / 'python'

                    if py.exists() and os.access(py, os.X_OK):
                        return str(py)
                    
            return None

        workspace_root = Path(__file__).parent.parent
        workspace_venv_python = workspace_root / '.venv' / 'bin' / 'python'

        python_cmd = None

        # If running in papers/codebases (formerly cloned_repos), prefer venvs in repo root and working dir
        codebases_dir = workspace_root / 'papers' / 'codebases'

        if str(config.working_dir).startswith(str(codebases_dir)):
            repo_root = Path(config.working_dir)

            # Try working dir and its parent (repo root)
            python_cmd = find_python_in_venvs([repo_root, repo_root.parent])

            if python_cmd:
                self.logger.info(f"[run_experiment] Using repo venv Python: {python_cmd}")

            elif workspace_venv_python.exists():
                python_cmd = str(workspace_venv_python)
                self.logger.info(f"[run_experiment] Fallback to workspace .venv Python: {python_cmd}")

            else:
                python_cmd = _get_python_executable()
                self.logger.info(f"[run_experiment] Fallback to system Python: {python_cmd}")

        else:
            # For non-cloned_repos, try venvs in working dir, then workspace venv, then system
            python_cmd = find_python_in_venvs([Path(config.working_dir)])

            if python_cmd:
                self.logger.info(f"[run_experiment] Using venv Python: {python_cmd}")

            elif workspace_venv_python.exists():
                python_cmd = str(workspace_venv_python)
                self.logger.info(f"[run_experiment] Fallback to workspace .venv Python: {python_cmd}")

            else:
                python_cmd = _get_python_executable()
                self.logger.info(f"[run_experiment] Fallback to system Python: {python_cmd}")

        # Convert to absolute path if needed, but DON'T resolve symlinks for venv Python
        # (venv wrappers are symlinks that set up PYTHONPATH correctly)
        if python_cmd and not os.path.isabs(python_cmd):
            python_cmd = Path(python_cmd).absolute().as_posix()

        # Detect if this is a test script (pytest)
        is_test_script = (
            'tests' in str(script_path.parent)
            or script_path.name.startswith('test_')
            or script_path.parent.name.startswith('test')
        )

        # Detect if this is a shell script
        is_shell_script = script_path.suffix == '.sh'

        # Prepare environment variables
        env = {**os.environ, **config.env_vars}

        # Force single-threaded execution in subprocesses
        env["OMP_NUM_THREADS"] = "1"
        env["MKL_NUM_THREADS"] = "1"
        env["TF_NUM_INTEROP_THREADS"] = "1"
        env["TF_NUM_INTRAOP_THREADS"] = "1"

        # Set working directory to script's parent
        working_dir = config.working_dir if config.working_dir else script_path.parent

        try:
            # Fix missing config file by substituting known local config names
            if config.args:
                try:
                    if '--config' in config.args:
                        idx = config.args.index('--config')
                        if idx + 1 < len(config.args):
                            cfg_name = config.args[idx + 1]
                            cfg_path = Path(working_dir) / cfg_name

                            if not cfg_path.exists():
                                # Try common alternatives in this codebase
                                alternatives = ['config_local_all.yaml', 'config_local.yaml', 'config.yaml']

                                for alt in alternatives:
                                    alt_path = Path(working_dir) / alt

                                    if alt_path.exists():
                                        self.logger.info(f"[run_experiment] Substituting missing config '{cfg_name}' with '{alt}'")
                                        config.args[idx + 1] = alt
                                        break
                except Exception:
                    pass

            if is_test_script:
                # Run with pytest and capture output (use -v for verbose test names)
                pytest_cmd = [python_cmd, '-m', 'pytest', str(script_path), '--maxfail=100', '--disable-warnings', '-v', '--tb=short']
                self.logger.info(f"[run_experiment] Running pytest: {' '.join(pytest_cmd)}")

                proc = subprocess.Popen(
                    pytest_cmd,
                    cwd=str(working_dir),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

            elif is_shell_script:
                venv_python = python_cmd if python_cmd else 'python3'
                cmd = ['bash', str(script_path)] + config.args
                self.logger.info(f"[run_experiment] Running shell script: {' '.join(cmd)}")

                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(working_dir),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1
                    )
                    self.logger.info(f"[run_experiment] Shell script process started successfully.")

                except Exception as e:
                    self.logger.error(f"[run_experiment] Failed to start shell script: {e}")
                    raise

            else:
                cmd = [python_cmd, str(script_path)] + config.args
                self.logger.info(f"[run_experiment] Running subprocess: {' '.join(cmd)}")

                proc = subprocess.Popen(
                    cmd,
                    cwd=str(working_dir),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

            last_log_time = start_time

            poll_interval = 10  # seconds
            log_interval = 300  # 5 minutes

            stdout_lines = []
            stderr_lines = []

            def stream_output(pipe, lines, is_stderr=False):
                for line in iter(pipe.readline, ''):
                    lines.append(line)

                    if is_stderr:
                        self.logger.info(f"[STDERR] {line.rstrip()}")

                    else:
                        self.logger.info(f"[STDOUT] {line.rstrip()}")

                pipe.close()

            stdout_thread = threading.Thread(target=stream_output, args=(proc.stdout, stdout_lines, False))
            stderr_thread = threading.Thread(target=stream_output, args=(proc.stderr, stderr_lines, True))

            stdout_thread.start()
            stderr_thread.start()

            while proc.poll() is None:
                now = time.time()

                if now - last_log_time >= log_interval:
                    elapsed = int((now - start_time) // 60)
                    self.logger.info(f"[run_experiment] Experiment still running after {elapsed} minutes...")
                    last_log_time = now

                time.sleep(poll_interval)

            stdout_thread.join()
            stderr_thread.join()

            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)

            duration = time.time() - start_time

            end_time_str = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')

            self.logger.info(f"[run_experiment] End time: {end_time_str}")
            self.logger.info(f"[run_experiment] Duration: {duration:.2f} seconds")

            # Always collect outputs from files
            outputs = self._collect_outputs(working_dir)

            # Parse stdout for metrics (accuracy, f1, etc.)
            metrics = {}
            
            # Apply YAML config extractors if provided
            if config.metrics_config and config.metrics_config.get('extractors'):
                logger.info(f"[run_experiment] Applying {len(config.metrics_config['extractors'])} config extractors to stdout")

                for extractor in config.metrics_config['extractors']:
                    pattern = extractor.get('pattern')
                    name = extractor.get('name')
                    transform = extractor.get('transform')
                    
                    if not pattern or not name:
                        continue
                    
                    # Search through all stdout lines
                    for line in stdout_lines + stderr_lines:
                        match = re.search(pattern, line, re.IGNORECASE)

                        if match:
                            try:
                                value = match.group(1)
                                
                                # Apply transformations
                                if transform == 'percent_to_decimal':
                                    value = float(value) / 100.0

                                elif '.' in value or 'e' in value.lower():
                                    value = float(value)

                                else:
                                    value = int(value)
                                
                                metrics[name] = value
                                logger.info(f"[run_experiment] Extracted {name} = {value} via config extractor")

                                break  # Take first match

                            except Exception as e:
                                logger.warning(f"[run_experiment] Failed to extract {name}: {e}")
            
            # Fallback to hardcoded patterns for backwards compatibility
            metric_patterns = [
                # Pattern for "Metric: value" or "Metric = value" format
                r"(accuracy|f1|f1[-_ ]score|precision|recall|bleu|rouge|auc|mrr|specificity|sensitivity|mae|mse|rmse|r2|loss|score)[\s:=]+([0-9\.eE+-]+)",
                r"(accuracy|f1|f1[-_ ]score|precision|recall|bleu|rouge|auc|mrr|specificity|sensitivity|mae|mse|rmse|r2|loss|score)\s*=\s*([0-9\.eE+-]+)",

                # Pattern for sklearn-style output: "Accuracy: 0.9298" with capital first letter
                r"(Accuracy|Precision|Recall|F1\s+Score):\s+([0-9\.eE+-]+)",

                # Pattern for model-prefixed metrics: "KNN Accuracy: 0.9667" or "SVM Precision (macro): 0.9524"
                r"(KNN|SVM|RF|LR)\s+(Accuracy|Precision|Recall|F1\s+Score)(?:\s+\(macro\))?:\s+([0-9\.eE+-]+)",
            ]

            model_names = {'KNN', 'SVM', 'RF', 'LR'}

            for line in stdout_lines + stderr_lines:
                for pat in metric_patterns:
                    m = re.search(pat, line, re.IGNORECASE)

                    if m:
                        # Handle model-prefixed metrics (3 groups)
                        if len(m.groups()) == 3 and m.group(1).upper() in model_names:
                            model = m.group(1).lower()
                            metric = m.group(2).lower().translate(str.maketrans(' -', '__'))

                            key = f"{model}_{metric}"

                            try:
                                val = float(m.group(3))
                                metrics[key] = val

                            except Exception:
                                continue

                        else:
                            # Standard metric (2 groups)
                            key = m.group(1).lower().translate(str.maketrans(' -', '__'))

                            try:
                                val = float(m.group(2))
                                metrics[key] = val

                            except Exception:
                                continue

            # Merge metrics from output files if present
            metrics_set = set(metrics)

            for out in outputs.values():
                if isinstance(out, dict):
                    for k, v in out.items():

                        if isinstance(v, (int, float)) and k not in metrics_set:
                            metrics[k] = v

                        elif isinstance(v, dict):
                            for kk, vv in v.items():
                                if isinstance(vv, (int, float)) and kk not in metrics_set:
                                    metrics[kk] = vv

            # If this was a pytest run, also parse test results
            if is_test_script:
                passed = failed = errors = skipped = 0

                test_details = []

                for line in stdout_lines + stderr_lines:
                    m = re.search(r'(\d+)\s+passed', line)

                    if m:
                        passed += int(m.group(1))
                    m = re.search(r'(\d+)\s+failed', line)

                    if m:
                        failed += int(m.group(1))
                    m = re.search(r'(\d+)\s+error', line)

                    if m:
                        errors += int(m.group(1))
                    m = re.search(r'(\d+)\s+skipped', line)

                    if m:
                        skipped += int(m.group(1))

                    # Extract test names and outcomes
                    # Pattern for verbose pytest: "test_file.py::TestClass::test_name PASSED"
                    test_match = re.search(r'::(test_\w+)\s+(PASSED|FAILED|SKIPPED|ERROR)', line)

                    if test_match:
                        test_details.append({
                            'test_name': test_match.group(1),
                            'outcome': test_match.group(2).upper()
                        })

                metrics['tests_passed'] = passed
                metrics['tests_failed'] = failed
                metrics['tests_errored'] = errors
                metrics['tests_skipped'] = skipped
                metrics['success'] = (failed == 0 and errors == 0)
                metrics['duration'] = duration

                if test_details:
                    metrics['test_details'] = test_details
                    outputs['test_details'] = test_details
                    self.logger.info(f"[run_experiment] Captured {len(test_details)} test outcomes for per-example metrics")

            # Write all found metrics to complete_results.json (merge with existing if present)
            try:
                results_path = working_dir / 'complete_results.json'

                existing_metrics = {}

                if results_path.exists():
                    try:
                        with open(str(results_path), 'r') as f:
                            existing_metrics = json.load(f)
                            
                        self.logger.info(f"[run_experiment] Merging with existing complete_results.json ({len(existing_metrics)} existing metrics)")
                    
                    except Exception as e:
                        self.logger.warning(f"[run_experiment] Could not read existing complete_results.json: {e}")
                
                # Smart merge: preserve existing experiment metrics, only update test-related fields
                merged_metrics = existing_metrics.copy()
                
                # Test-related fields that can be updated
                test_fields = {'tests_passed', 'tests_failed', 'tests_errored', 'tests_skipped', 
                              'success', 'test_details', 'duration'}
                
                # Performance metric fields (accuracy, precision, etc.) should always be merged
                performance_fields = {'accuracy', 'precision', 'recall', 'f1_score', 'f1', 
                                    'auc', 'bleu', 'rouge', 'mrr', 'mae', 'mse', 'rmse', 'r2'}
                
                # If this run produced test results, update only test fields + performance metrics
                is_test_run = any(k in metrics for k in {'tests_passed', 'tests_failed', 'test_details'})
                
                if is_test_run:
                    # Update test-related fields and performance metrics, preserve all other metrics
                    preserved_count = 0

                    for key, value in metrics.items():
                        if key in test_fields or key in performance_fields:
                            merged_metrics[key] = value

                        else:
                            preserved_count += 1

                    preserved_metric_count = sum(1 for k in existing_metrics if k not in test_fields and k not in performance_fields)

                    self.logger.info(f"[run_experiment] Updated test results, preserved {preserved_metric_count} experiment metrics")
                else:
                    # Regular experiment run - merge all metrics (new takes precedence)
                    merged_metrics.update(metrics)
                
                with open(str(results_path), 'w') as f:
                    json.dump(merged_metrics, f, indent=2)

                outputs['complete_results.json'] = merged_metrics
                self.logger.info(f"[run_experiment] Wrote complete_results.json with {len(merged_metrics)} total fields")

            except Exception as e:
                self.logger.error(f"[run_experiment] Failed to write complete_results.json: {e}")

            # Log full stdout and stderr for debugging
            if proc.returncode != 0:
                self.logger.error(f"Experiment failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")

                # Auto-retry if dataset error detected
                if 'Dataset not found or corrupted' in stderr and 'download=False' in stderr:
                    self.logger.warning("[run_experiment] Detected missing dataset error. Retrying with download=True...")

                    # Try to patch args if possible
                    # If script supports --download, add it
                    if '--download' not in config.args:
                        patched_args = config.args + ['--download']

                        cmd2 = [python_cmd, str(script_path)] + patched_args
                        self.logger.info(f"[run_experiment] Retrying subprocess: {' '.join(cmd2)}")

                        proc2 = subprocess.Popen(
                            cmd2,
                            cwd=str(working_dir),
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )

                        last_log_time2 = time.time()

                        while True:
                            retcode2 = proc2.poll()
                            now2 = time.time()

                            if retcode2 is not None:
                                break

                            if now2 - last_log_time2 >= log_interval:
                                elapsed2 = int((now2 - start_time) // 60)
                                self.logger.info(f"[run_experiment] Experiment retry still running after {elapsed2} minutes...")
                                last_log_time2 = now2

                            time.sleep(poll_interval)

                        stdout2, stderr2 = proc2.communicate()
                        duration2 = time.time() - start_time
                        self.logger.info(f"[run_experiment] Retry duration: {duration2:.2f} seconds")
                        outputs2 = self._collect_outputs(working_dir)

                        if proc2.returncode != 0:
                            self.logger.error(f"Experiment retry failed.\nSTDOUT:\n{stdout2}\nSTDERR:\n{stderr2}")

                        else:
                            self.logger.info(f"[run_experiment] Experiment retry completed successfully.\nSTDOUT:\n{stdout2}")
                            
                        return ExperimentResult(
                            success=(proc2.returncode == 0),
                            stdout=stdout2,
                            stderr=stderr2,
                            return_code=proc2.returncode,
                            duration=duration2,
                            outputs=outputs2
                        )
            else:
                self.logger.info(f"[run_experiment] Experiment completed successfully.\nSTDOUT:\n{stdout}")

            return ExperimentResult(
                success=(proc.returncode == 0),
                stdout=stdout,
                stderr=stderr,
                return_code=proc.returncode,
                duration=duration,
                outputs=outputs
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            self.logger.error(f"Experiment timed out after {config.timeout} seconds")

            return ExperimentResult(
                success=False,
                stdout="",
                stderr=f"Timeout after {config.timeout} seconds",
                return_code=-1,
                duration=duration
            )
        
        except Exception as e:
            duration = time.time() - start_time
            tb = traceback.format_exc()
            self.logger.error(f"Experiment failed with error: {e}\n{tb}")

            return ExperimentResult(
                success=False,
                stdout="",
                stderr=tb,
                return_code=-1,
                duration=duration
            )
