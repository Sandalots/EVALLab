"""===============================================================================
EVALLAB STAGE 2/4: CODE RETRIEVAL

Locates experiment codebase via: user path → GitHub (paper-specific) → local directory (fallback).
Outputs local codebase path for Stage 3 (Experiment Execution).
===============================================================================
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class RepoRetriever:
    """Retrieve code repositories from various sources."""

    def __init__(self, workspace_root: Path = None, llm_client=None, paper_path: Path = None):
        """
        Initialize repository retriever.

        Args:
            workspace_root: Root directory of the workspace (defaults to current dir)
            llm_client: Optional LLM client for semantic codebase matching
            paper_path: Path to the paper being analyzed (for LLM context)
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.paper_source_dir = self.workspace_root / "papers" / "codebases"
        self.llm_client = llm_client
        self.paper_path = paper_path

    def retrieve_code(self, github_urls: List[str] = None,
                      local_path: Path = None) -> Optional[Path]:
        """
        Retrieve code from available sources with the following priority:
        1. User-provided path/URL (--code argument) - local path OR GitHub URL
        2. GitHub URLs from the paper (paper-specific)
        3. Local papers/codebases directory (fallback/default)

        Args:
            github_urls: List of GitHub repository URLs found in paper
            local_path: Optional user-provided local codebase path OR GitHub URL string

        Returns:
            Path to the retrieved codebase, or None if not found
        """
        # Priority 1: User-provided path/URL (explicit override)
        if local_path:
            # Check if it's a GitHub URL (passed as string converted to Path)
            local_path_str = str(local_path)
            if 'github.com' in local_path_str or local_path_str.startswith('http'):
                logger.info(f"User provided GitHub URL: {local_path_str}")
                # Normalize URL format (fix common issues like missing slashes)
                normalized_url = self._normalize_github_url(local_path_str)
                cloned_path = self._clone_github_repo(normalized_url)
                if cloned_path:
                    logger.info(f"✓ Using user-provided GitHub repository")
                    return cloned_path
                # Clone failed - prompt user for manual clone
                logger.error(
                    f"❌ Failed to clone user-provided repository: {normalized_url}")
                logger.error(f"")
                logger.error(f"🛠️  MANUAL CLONE REQUIRED:")
                logger.error(f"   Please run this command manually:")
                logger.error(
                    f"   git clone {normalized_url} {self.workspace_root}/papers/codebases/{normalized_url.split('/')[-1].replace('.git', '')}")
                logger.error(f"")
                logger.error(
                    f"   Then re-run EVALLab with: --code {self.workspace_root}/papers/codebases/{normalized_url.split('/')[-1].replace('.git', '')}")
                return None
            # Check if it's a local path
            elif local_path.exists():
                # Try to find code subdirectory using LLM if available
                if self.llm_client:
                    code_dir = self._llm_find_code_directory(local_path)
                    if code_dir and code_dir != local_path:
                        logger.info(f"✓ LLM identified code directory: {code_dir}")
                        return code_dir
                
                # Heuristic fallback: check for common 'code' subdirectory
                code_subdir = local_path / 'code'
                if code_subdir.is_dir() and self._looks_like_code_dir(code_subdir):
                    logger.info(f"✓ Using 'code' subdirectory: {code_subdir}")
                    return code_subdir
                
                logger.info(f"✓ Using user-provided codebase: {local_path}")
                return local_path
            else:
                logger.error(
                    f"❌ User-provided path does not exist: {local_path}")
                return None

        # Priority 2: Clone from GitHub (paper-specific code)
        if github_urls:
            logger.info(f"Found {len(github_urls)} GitHub URL(s) in paper")
            for url in github_urls:
                logger.info(f"  - {url}")

            cloned_path = self._clone_github_repo(github_urls[0])
            if cloned_path:
                logger.info(f"✓ Using paper-specific GitHub repository")
                return cloned_path

        # Priority 3: Check papers/codebases directory (fallback)
        # Try LLM-based semantic matching if available
        if self.llm_client and self.paper_path:
            logger.info("Attempting LLM-based semantic codebase matching...")
            matched_code = self._llm_match_codebase()
            if matched_code:
                logger.info(f"✓ Using LLM-matched local codebase: {matched_code}")
                return matched_code
        
        # Fallback: Try to find any local code without LLM
        local_code = self._find_local_code()
        if local_code:
            logger.info(f"✓ Using local codebase (heuristic fallback): {local_code}")
            return local_code
        
        # Otherwise, fail gracefully
        logger.error("❌ No codebase found! Checked:")
        logger.error(f"  - User-provided path: {local_path}")
        logger.error(f"  - GitHub URLs: {github_urls}")
        logger.error(f"  - Local directory: {self.paper_source_dir}")
        if not self.llm_client:
            logger.error("  ℹ️  LLM semantic matching unavailable (no llm_client)")
        logger.error(
            "🛑 Please specify a codebase using the --code argument or ensure the paper contains a valid GitHub repository link.")
        return None

    def _find_local_code(self) -> Optional[Path]:
        """
        Find code in the local papers/codebases directory.
        Looks for supplementary_material/code or similar structures.

        Returns:
            Path to code directory if found
        """
        if not self.paper_source_dir.exists():
            return None


        # Check common code directory structures
        if not self.paper_source_dir.exists():
            return None
        
        # First try LLM-based directory discovery if available
        if self.llm_client:
            for subdir in self.paper_source_dir.iterdir():
                if subdir.is_dir():
                    llm_code_dir = self._llm_find_code_directory(subdir)
                    if llm_code_dir:
                        return llm_code_dir
        
        # Heuristic fallback: check common patterns
        candidates = [
            self.paper_source_dir / "code",
            self.paper_source_dir / "supplementary_material" / "code",
            self.paper_source_dir / "supplementary_material",
        ]
        
        # Add all subdirectories as candidates
        if self.paper_source_dir.exists():
            candidates.extend([d for d in self.paper_source_dir.iterdir() if d.is_dir()])

        for candidate in candidates:
            if candidate.exists() and self._looks_like_code_dir(candidate):
                return candidate

        return None

    def _looks_like_code_dir(self, path: Path) -> bool:
        """
        Check if a directory looks like it contains code.

        Args:
            path: Directory to check

        Returns:
            True if directory appears to contain code
        """
        if not path.is_dir():
            return False

        # Check for common code indicators
        code_indicators = [
            '*.py',      # Python
            '*.js',      # JavaScript
            '*.java',    # Java
            '*.cpp',     # C++
            '*.c',       # C
            '*.go',      # Go
            '*.rs',      # Rust
            'requirements.txt',
            'package.json',
            'setup.py',
            'Makefile',
            'README.md'
        ]

        for indicator in code_indicators:
            if any(path.glob(indicator)) or any(path.rglob(indicator)):
                return True

        return False

    def _normalize_github_url(self, url: str) -> str:
        """
        Normalize GitHub URL to proper format.

        Args:
            url: GitHub URL (may be malformed)

        Returns:
            Properly formatted GitHub URL
        """
        url = url.strip()

        # Fix common issues
        # https:/github.com -> https://github.com
        if url.startswith('https:/github.com') and not url.startswith('https://github.com'):
            url = url.replace('https:/github.com', 'https://github.com')

        # http:// -> https://
        if url.startswith('http://github.com'):
            url = url.replace('http://github.com', 'https://github.com')

        # Ensure https:// prefix
        if url.startswith('github.com'):
            url = 'https://' + url

        return url

    def _clone_github_repo(self, github_url: str) -> Optional[Path]:
        """
        Clone a GitHub repository to local workspace.

        Args:
            github_url: GitHub repository URL

        Returns:
            Path to cloned repository, or None if clone failed
        """
        try:
            # Extract repo name from URL
            repo_name = github_url.rstrip('/').split('/')[-1]
            if repo_name.endswith('.git'):
                repo_name = repo_name[:-4]

            clone_dir = self.workspace_root / "papers" / "codebases" / repo_name

            # Skip if already cloned and looks valid
            if clone_dir.exists() and self._looks_like_code_dir(clone_dir):
                logger.info(f"✓ Repository already exists: {clone_dir}")
                logger.info(
                    f"   Skipping clone (delete directory to re-clone)")
                return clone_dir
            elif clone_dir.exists():
                # Directory exists but is empty/invalid - remove and re-clone
                logger.warning(
                    f"Found invalid clone directory, removing: {clone_dir}")
                import shutil
                shutil.rmtree(clone_dir)
                logger.info(f"Re-cloning repository...")

            # Create parent directory
            clone_dir.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"Cloning repository from {github_url}...")
            result = subprocess.run(
                ['git', 'clone', github_url, str(clone_dir)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                logger.info(f"✓ Successfully cloned to: {clone_dir}")
                return clone_dir
            else:
                error_msg = result.stderr.strip()
                logger.error(f"Git clone failed with error:")
                logger.error(f"  {error_msg}")

                # Provide helpful hints based on error type
                if 'Repository not found' in error_msg or '404' in error_msg:
                    logger.error(f"")
                    logger.error(f"❓ Repository may not exist or is private.")
                    logger.error(f"   Check URL: {github_url}")
                elif 'Could not resolve hostname' in error_msg:
                    logger.error(f"")
                    logger.error(f"🌐 Network/DNS issue. Check:")
                    logger.error(f"   1. Internet connection")
                    logger.error(f"   2. URL format: {github_url}")
                elif 'Permission denied' in error_msg or 'Authentication' in error_msg:
                    logger.error(f"")
                    logger.error(f"🔐 Authentication required. Try:")
                    logger.error(f"   1. Check if repository is public")
                    logger.error(f"   2. Configure SSH keys or use HTTPS")

                return None

        except subprocess.TimeoutExpired:
            logger.error("Repository clone timed out after 5 minutes")
            return None
        except Exception as e:
            logger.error(f"Error cloning repository: {e}")
            return None

    def _llm_match_codebase(self) -> Optional[Path]:
        """Use LLM to semantically match paper to available local codebases."""
        import json
        
        if not self.paper_source_dir.exists():
            return None
        
        available_codebases = [d for d in self.paper_source_dir.iterdir() if d.is_dir()]
        if not available_codebases:
            return None
        
        # Read paper title and extract initial context
        paper_title = self.paper_path.stem.replace('_', ' ').replace('-', ' ')
        
        # Gather codebase information
        codebase_info = []
        for path in available_codebases[:10]:  # Limit to prevent token overflow
            readme = self._read_codebase_readme(path)
            codebase_info.append({
                'name': path.name,
                'readme_excerpt': readme[:400] if readme else "No README found"
            })
        
        prompt = f"""Given a research paper titled: \"{paper_title}\"

And these available codebases:
{json.dumps(codebase_info, indent=2)}

Which codebase is most likely the implementation for this paper?
Consider semantic similarity, matching research topics, and method names.
If none match well, respond with null.

Respond ONLY with valid JSON: {{\"best_match\": \"codebase_name or null\", \"confidence\": 0.0-1.0, \"reasoning\": \"brief explanation\"}}"""

        try:
            result = self.llm_client.extract_json(prompt)
            confidence = result.get('confidence', 0)
            best_match = result.get('best_match')
            
            if best_match and confidence > 0.5:
                matched_path = self.paper_source_dir / best_match
                if matched_path.exists():
                    logger.info(f"LLM matched codebase: {best_match} (confidence: {confidence:.2f})")
                    logger.debug(f"Reasoning: {result.get('reasoning', 'N/A')}")
                    return matched_path
            else:
                logger.debug(f"LLM found no confident match (confidence: {confidence:.2f})")
        except Exception as e:
            logger.warning(f"LLM codebase matching failed: {e}")
        
        return None
    
    def _llm_find_code_directory(self, base_path: Path) -> Optional[Path]:
        """Use LLM to identify the main code directory, with heuristics to prefer entry points."""
        import json
        
        if not base_path.is_dir():
            return None
        
        # First try heuristic: look for directories with main/run scripts
        candidates = []
        for item in base_path.rglob("*.py"):
            if any(name in item.name.lower() for name in ['main', 'run', 'train', 'experiment']):
                candidates.append(item.parent)
        
        # Score candidates by how many entry point scripts they have
        if candidates:
            from collections import Counter
            candidate_scores = Counter(candidates)
            best_candidate = candidate_scores.most_common(1)[0][0]
            # Prefer the candidate with most entry points, but not nested src dirs if parent has scripts
            if any(script in [f.name for f in best_candidate.iterdir() if f.is_file()] 
                   for script in ['main.py', 'run.py', 'train.py', 'experiment.py']):
                logger.debug(f"Heuristic found code directory with entry points: {best_candidate.relative_to(base_path)}")
                return best_candidate
        
        # Fallback to LLM if heuristics fail
        dir_tree = self._get_directory_tree(base_path, max_depth=2)
        
        # List Python files to help LLM decide
        python_files = []
        for py_file in base_path.rglob("*.py"):
            rel_path = py_file.relative_to(base_path)
            if len(rel_path.parts) <= 2:  # Only show files up to 2 levels deep
                python_files.append(str(rel_path))
        
        py_files_info = "\n".join(python_files[:15]) if python_files else "No Python files found"
        
        prompt = f"""Given this directory structure:
{dir_tree}

Python files found:
{py_files_info}

Identify the subdirectory that contains the MAIN EXECUTABLE scripts (like main.py, run.py, train.py).
Do NOT choose nested 'src' or 'utils' directories if the parent has executable scripts.
Prefer directories with files like: main.py, run.py, train.py, experiment.py
If the root is already the code directory, respond with \".\"

Respond ONLY with valid JSON: {{\"code_dir\": \"relative/path or .\", \"confidence\": 0.0-1.0, \"reasoning\": \"brief explanation\"}}"""

        try:
            result = self.llm_client.extract_json(prompt)
            confidence = result.get('confidence', 0)
            code_dir = result.get('code_dir', '').strip()
            
            if code_dir and confidence > 0.6:  # Increased threshold
                if code_dir == '.':
                    logger.debug(f"LLM identified root as code directory (confidence: {confidence:.2f})")
                    return base_path
                code_path = base_path / code_dir
                if code_path.exists():
                    logger.debug(f"LLM identified code directory: {code_dir} (confidence: {confidence:.2f})")
                    logger.debug(f"  Reasoning: {result.get('reasoning', 'N/A')}")
                    return code_path
        except Exception as e:
            logger.debug(f"LLM directory discovery failed: {e}")
        
        # Final fallback: return base_path if it has Python files
        if python_files:
            logger.debug(f"Fallback: using base directory with {len(python_files)} Python files")
            return base_path
        
        return None
    
    def _read_codebase_readme(self, path: Path) -> Optional[str]:
        """Read README file from a codebase directory."""
        readme_names = ['README.md', 'README.txt', 'README', 'readme.md', 'Readme.md']
        for name in readme_names:
            readme_path = path / name
            if readme_path.exists():
                try:
                    return readme_path.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
        return None
    
    def _get_directory_tree(self, path: Path, max_depth: int = 2, current_depth: int = 0, prefix: str = "") -> str:
        """Generate a simple directory tree string for LLM analysis."""
        if current_depth >= max_depth:
            return ""
        
        lines = []
        try:
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            for item in items[:15]:  # Limit items per directory
                if item.name.startswith('.'):
                    continue
                if item.is_dir():
                    lines.append(f"{prefix}├── {item.name}/")
                    if current_depth < max_depth - 1:
                        lines.append(self._get_directory_tree(item, max_depth, current_depth + 1, prefix + "│   "))
                else:
                    # Show file extension
                    lines.append(f"{prefix}├── {item.name}")
        except PermissionError:
            lines.append(f"{prefix}├── [Permission Denied]")
        
        return "\n".join(filter(None, lines))
    
    def _llm_parse_readme_commands(self, readme_path: Path, codebase_path: Path) -> Optional[Dict[str, Any]]:
        """
        Use LLM to parse README and extract experiment run commands.
        
        Args:
            readme_path: Path to README file
            codebase_path: Root path of the codebase
            
        Returns:
            Dictionary with extracted commands and metadata, or None if parsing fails
        """
        if not self.llm_client or not readme_path.exists():
            return None
        
        try:
            readme_content = readme_path.read_text(encoding='utf-8', errors='ignore')
            
            # Get directory structure for context
            dir_tree = self._get_directory_tree(codebase_path, max_depth=3)
            
            prompt = f"""You are analyzing a research paper's codebase README to extract information about how to run experiments.

README Content:
```
{readme_content[:4000]}  # Limit to avoid token overflow
```

Directory Structure:
```
{dir_tree}
```

Extract the following information and return as JSON:
1. main_script: The primary Python script to run the main experiment (just filename, e.g., "main.py")
2. main_args: List of command-line arguments for the main script (e.g., ["--config", "config.yaml"])
3. dependencies: List of pip package requirements mentioned
4. setup_commands: Any setup/installation commands needed before running
5. description: Brief description of what the main experiment does

Return ONLY valid JSON in this exact format:
{{
  "main_script": "main.py",
  "main_args": ["--arg1", "value1"],
  "dependencies": ["package1>=1.0", "package2"],
  "setup_commands": ["pip install -r requirements.txt"],
  "description": "Description of the experiment"
}}

If information is not found, use empty lists [] or empty string "". Return ONLY the JSON object."""

            response = self.llm_client.query_llm(prompt)
            if not response:
                return None
            
            # Extract JSON from response
            result = self._extract_json(response)
            if result and isinstance(result, dict):
                logger.info(f"✓ LLM parsed README commands from {readme_path.name}")
                logger.debug(f"  Extracted: {result.get('main_script', 'N/A')}")
                return result
            
        except Exception as e:
            logger.warning(f"Failed to parse README with LLM: {e}")
        
        return None

    def get_codebase_info(self, code_path: Path) -> dict:
        """
        Get basic information about the retrieved codebase.

        Args:
            code_path: Path to codebase

        Returns:
            Dictionary with codebase metadata
        """
        info = {
            'path': code_path,
            'exists': code_path.exists(),
            'is_git_repo': (code_path / '.git').exists(),
            'has_python': bool(list(code_path.glob('*.py'))),
            'has_requirements': (code_path / 'requirements.txt').exists(),
            'has_setup': (code_path / 'setup.py').exists(),
        }

        # Count files by extension
        extensions = {}
        for file in code_path.rglob('*'):
            if file.is_file() and not any(p.startswith('.') for p in file.parts):
                ext = file.suffix
                extensions[ext] = extensions.get(ext, 0) + 1

        info['file_counts'] = extensions

        return info
    
    def parse_readme_commands(self, codebase_path: Path) -> Optional[Dict[str, Any]]:
        """
        Parse README file to extract experiment run commands using LLM.
        
        Args:
            codebase_path: Path to the codebase root
            
        Returns:
            Dictionary with extracted commands or None if not available
        """
        readme_names = ['README.md', 'README.txt', 'README', 'readme.md', 'Readme.md', 'ReadMe.md']
        for name in readme_names:
            readme_path = codebase_path / name
            if readme_path.exists():
                return self._llm_parse_readme_commands(readme_path, codebase_path)
        
        logger.debug(f"No README found in {codebase_path}")
        return None
