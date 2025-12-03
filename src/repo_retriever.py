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

    def __init__(self, workspace_root: Path = None):
        """
        Initialize repository retriever.

        Args:
            workspace_root: Root directory of the workspace (defaults to current dir)
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.paper_source_dir = self.workspace_root / "papers" / "codebases"

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
                # If supplementary_material or decontextualization, prefer 'code' subdir if present
                if local_path.name in ['supplementary_material', 'decontextualization']:
                    code_dir = local_path / 'code'
                    if code_dir.is_dir():
                        logger.info(
                            f"✓ Using 'code' directory in {local_path.name}: {code_dir}")
                        return code_dir
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
        # Only fallback to Decontextualisation codebase if the paper is Decontextualisation
        paper_name = None
        if hasattr(self, 'paper_path') and self.paper_path:
            paper_name = self.paper_path.stem.lower()
        if paper_name and ('decontextualisation' in paper_name or 'decontextualization' in paper_name):
            local_code = self._find_local_code()
            if local_code:
                logger.info(f"✓ Using local codebase (fallback): {local_code}")
                return local_code
        # Otherwise, do not fallback, prompt for codebase or fail gracefully
        logger.error("❌ No codebase found! Checked:")
        logger.error(f"  - User-provided path: {local_path}")
        logger.error(f"  - GitHub URLs: {github_urls}")
        logger.error(f"  - Local directory: {self.paper_source_dir}")
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


        # Check common structures for both supplementary_material and decontextualization
        candidates = [
            self.paper_source_dir / "supplementary_material" / "code",
            self.paper_source_dir / "supplementary_material",
            self.paper_source_dir / "decontextualization" / "code",
            self.paper_source_dir / "decontextualization",
            self.paper_source_dir / "code",
            self.paper_source_dir
        ]

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
