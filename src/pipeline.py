"""===============================================================================
EVALLAB PIPELINE ORCHESTRATOR (PIPELINES THE 4 STAGES)

Coordinates all 4 stages: Paper Parsing → Code Retrieval → Experiment Execution → Result Evaluation.
===============================================================================
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
import yaml
from dotenv import load_dotenv
import os
import json
import re
import requests

from src.paper_parser import PaperParser, PaperContent
from src.repo_retriever import RepoRetriever
from src.experiment_executor import ExperimentExecutor, CodebaseInfo, ExperimentConfig
from src.result_evaluator import ResultEvaluator

# Custom colored logging formatter
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels and highlights for special content."""
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[92m',       # Green
        'WARNING': '\033[93m',    # Yellow
        'ERROR': '\033[91m',      # Red
        'CRITICAL': '\033[95m',   # Magenta
    }
    RESET = '\033[0m'

    # Color for different parts
    TIME_COLOR = '\033[90m'       # Gray
    NAME_COLOR = '\033[94m'       # Blue
    LEVEL_COLORS = COLORS

    # Highlight colors for special content
    NUMBER_COLOR = '\033[96m'     # Cyan - for numbers
    PATH_COLOR = '\033[93m'       # Yellow - for file paths
    METRIC_COLOR = '\033[95m'     # Magenta - for percentages/metrics
    # Red - for ML metric names (F1, accuracy, etc.)
    ML_METRIC_COLOR = '\033[91m'
    KEYWORD_COLOR = '\033[93m'    # Bright yellow - for special keywords
    # Green - for status words (success, pass, etc.)
    STATUS_COLOR = '\033[92m'

    def colorize_message(self, message, base_color):
        """Add special highlighting to numbers, paths, and metrics in the message."""
        import re

        # Highlight status words in green (success, pass, completed, etc.)
        message = re.sub(
            r'\b(success|pass|passed|completed?|excellent|good|failed?|error)\b',
            f'{self.STATUS_COLOR}\\1{base_color}',
            message,
            flags=re.IGNORECASE
        )

        # Highlight special keywords in bright yellow (ollama, baseline, reproduced, etc.)
        message = re.sub(
            r'\b(ollama|llama3|baseline|reproduced?|reproduction|grade|assessment|success\s+rate|avg\s+deviation|average\s+deviation|mean\s+deviation|avg\s+diff|deviation|difference|diff|metric|method|experiment|stage|pipeline|configuration|granularity|retrieval|downstream|model)\b',
            f'{self.KEYWORD_COLOR}\\1{base_color}',
            message,
            flags=re.IGNORECASE
        )

        # Highlight ML metric names in red (F1, accuracy, recall, precision, etc.)
        message = re.sub(
            r'\b(f1|accuracy|recall|precision|mrr|specificity|sensitivity|auc|roc|mse|mae|rmse|r2|loss|score)[-_\s]?(score|value|rate)?s?\b',
            f'{self.ML_METRIC_COLOR}\\1\\2{base_color}',
            message,
            flags=re.IGNORECASE
        )

        # Highlight percentages and metrics with units (e.g., 94.2%, 0.05, 10.5MB, 2.5s, etc.)
        message = re.sub(
            r'(\d+\.?\d*%|\d+\.\d+(?:MB|GB|KB|s|ms|mins?|hours?)?|\d+(?:MB|GB|KB|s|ms|mins?|hours?))',
            f'{self.METRIC_COLOR}\\1{base_color}',
            message
        )

        # Highlight file paths (anything with / or .py, .txt, .json, etc.)
        message = re.sub(
            r'([/\w\-\.]+/[\w\-\./]+|[\w\-]+\.(py|txt|json|yaml|md|csv|html|pdf))',
            f'{self.PATH_COLOR}\\1{base_color}',
            message
        )

        # Highlight standalone numbers (not already colored by previous rules)
        # Avoid re-coloring numbers that are part of paths or metrics
        message = re.sub(
            r'(?<![/\w\-\.%])\b(\d+)\b(?![/\w\-\.%MGKB])',
            f'{self.NUMBER_COLOR}\\1{base_color}',
            message
        )

        return message

    def format(self, record):
        # Color the timestamp
        timestamp = self.formatTime(record, self.datefmt)
        colored_time = f"{self.TIME_COLOR}{timestamp}{self.RESET}"

        # Color the logger name
        colored_name = f"{self.NAME_COLOR}{record.name}{self.RESET}"

        # Color the level name
        level_color = self.LEVEL_COLORS.get(record.levelname, self.RESET)
        colored_level = f"{level_color}{record.levelname}{self.RESET}"

        # Get base message color
        message_color = self.LEVEL_COLORS.get(record.levelname, self.RESET)

        # Colorize the message with special highlights
        message = record.getMessage()
        colored_message = f"{message_color}{self.colorize_message(message, message_color)}{self.RESET}"

        return f"{colored_time} - {colored_name} - {colored_level} - {colored_message}"


# Only set up a colored console handler here; file handler is set up per-paper in run_EVALLab.py
console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter(datefmt='%Y-%m-%d %H:%M:%S'))
logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler]
)
logger = logging.getLogger(__name__)


class ReproductionAgent:
    def _extract_metrics_from_text(self, text: str) -> dict:
        """Extract numeric metrics (accuracy, f1, etc.) from a text block using regex."""
        import re
        metric_patterns = [
            r"(accuracy|f1|f1[-_ ]score|precision|recall|bleu|rouge|auc|mrr|specificity|sensitivity|mae|mse|rmse|r2|loss|score)[\s:=]+([0-9\.eE+-]+)",
            r"(accuracy|f1|f1[-_ ]score|precision|recall|bleu|rouge|auc|mrr|specificity|sensitivity|mae|mse|rmse|r2|loss|score)\s*=\s*([0-9\.eE+-]+)"
            ]
        
        metrics = {}
        for line in text.splitlines():
            for pat in metric_patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    key = m.group(1).lower().replace(' ', '_').replace('-', '_')
                    try:
                        val = float(m.group(2))
                        metrics[key] = val
                    except Exception:
                        continue
        return metrics
    """Main agent that coordinates paper reproduction workflow with integrated LLM."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the reproduction agent.

        Args:
            config_path: Optional path to config.yaml file
        """
        # Load environment variables
        load_dotenv()

        # Load configuration
        self.config = self._load_config(config_path)

        # Initialize LLM settings (integrated from llm_client)
        self.ollama_base_url = self.config['ollama']['base_url']
        self.ollama_model = self.config['ollama']['model']
        self.ollama_temperature = self.config['ollama']['temperature']
        self.ollama_timeout = self.config['ollama']['timeout']

        # Initialize components (using new 4-stage architecture)
        self.paper_parser = PaperParser()
        self.repo_retriever = RepoRetriever()
        # Extract paper name for per-paper logging
        paper_name = None
        if hasattr(self, 'paper_path') and self.paper_path:
            paper_name = Path(self.paper_path).stem
        elif 'paper' in self.config and self.config['paper']:
            paper_name = Path(self.config['paper']).stem
        self.experiment_executor = ExperimentExecutor(
            config=self.config, paper_name=paper_name)
        self.result_evaluator = ResultEvaluator(
            llm_client=self,  # Pass self as we have integrated LLM methods
            threshold=self.config['evaluation']['threshold']
        )

        # Create output directory
        self.output_dir = Path(self.config['paths']['output_dir'])
        self.output_dir.mkdir(exist_ok=True, parents=True)

    def _load_config(self, config_path: Optional[Path]) -> dict:
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config.yaml'

        if not config_path.exists():
            logger.warning(
                f"Config file not found: {config_path}, using defaults")
            return self._default_config()

        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _load_per_example_results(self, log_csv_path):
        """Load per-example results from a log.csv file (TextAttack format)."""
        import csv
        results = []
        if not Path(log_csv_path).exists():
            logger.warning(f"Per-example log file not found: {log_csv_path}")
            return results
        with open(log_csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(dict(row))
        return results

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            'ollama': {
                'base_url': os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
                'model': os.getenv('OLLAMA_MODEL', 'llama3'),
                'temperature': float(os.getenv('OLLAMA_TEMPERATURE', '0.7')),
                'timeout': int(os.getenv('OLLAMA_TIMEOUT', '120'))
            },
            'logging': {'level': 'INFO'},
            'experiment': {'timeout': 3600, 'max_retries': 2, 'use_venv': True},
            'evaluation': {'threshold': 0.05},
            'paths': {
                'output_dir': './outputs'
            }
        }

    # ============================================================================
    # INTEGRATED OLLAMA LLM CLIENT METHODS
    # ============================================================================

    def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            response = requests.get(
                f"{self.ollama_base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> List[str]:
        """List available models in Ollama."""
        try:
            response = requests.get(
                f"{self.ollama_base_url}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing models: {e}")
            return []

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: Optional[float] = None) -> str:
        """
        Generate a response from the LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt for context
            temperature: Optional temperature override

        Returns:
            Generated text response
        """
        url = f"{self.ollama_base_url}/api/generate"

        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.ollama_temperature
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.ollama_timeout
            )
            response.raise_for_status()

            result = response.json()
            return result.get('response', '').strip()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating response: {e}")
            raise

    def chat(self, messages: List[Dict[str, str]],
             temperature: Optional[float] = None) -> str:
        """
        Chat completion with conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Optional temperature override

        Returns:
            Generated response
        """
        url = f"{self.ollama_base_url}/api/chat"

        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature or self.ollama_temperature
            }
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.ollama_timeout
            )
            response.raise_for_status()

            result = response.json()
            return result.get('message', {}).get('content', '').strip()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error in chat completion: {e}")
            raise

    def extract_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a response and parse it as JSON, robust to LLM output errors and preambles.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            Parsed JSON dictionary
        """
        import re
        response = self.generate(prompt, system_prompt, temperature=0.1)

        # Remove lines that are just '...'
        response = '\n'.join(line for line in response.splitlines() if line.strip() != '...')
        # Remove leading/trailing ellipses
        response = re.sub(r'^\s*\.\.\.+', '', response)
        response = re.sub(r'\.\.\.+\s*$', '', response)

        # Always skip to the first '{' (ignore any preamble)
        first_brace = response.find('{')
        if first_brace != -1:
            response = response[first_brace:]

        # Try to extract JSON from markdown code blocks first
        json_match = re.search(
            r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            response = json_match.group(1)

        # Try to find the first valid JSON object in the response using a stack-based approach
        def extract_first_json_object(text):
            start = text.find('{')
            if start == -1:
                return None
            stack = []
            for i in range(start, len(text)):
                if text[i] == '{':
                    stack.append(i)
                elif text[i] == '}':
                    stack.pop()
                    if not stack:
                        return text[start:i+1]
            return None

        json_candidate = extract_first_json_object(response)
        if json_candidate:
            response = json_candidate


        # Remove lines that are just '...'
        cleaned_response = '\n'.join(line for line in response.splitlines() if line.strip() != '...')
        # Remove inline or trailing ellipsis artifacts (e.g., , ... or ...)
        cleaned_response = re.sub(r',?\s*\.\.\.(,)?', lambda m: ',' if m.group(1) else '', cleaned_response)
        # Clean control characters that break JSON
        cleaned_response = re.sub(r'[\x00-\x1F\x7F]', '', cleaned_response)
        # Strip trailing periods, commas, and whitespace
        cleaned_response = re.sub(r'[\s\.,]+$', '', cleaned_response)

        # Auto-close unbalanced braces if needed (for truncated LLM output)
        open_braces = cleaned_response.count('{')
        close_braces = cleaned_response.count('}')
        if open_braces > close_braces:
            cleaned_response += '}' * (open_braces - close_braces)

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            # Try to repair with python-json5 if available
            try:
                import json5
                logger.warning("Trying to parse with json5 for more tolerant JSON parsing.")
                return json5.loads(cleaned_response)
            except Exception as e2:
                logger.error(f"Failed to parse JSON with both stdlib and json5: {e2}")
                logger.error(f"Full raw EVALLab response:\n{response}")
                logger.debug(f"Cleaned response:\n{cleaned_response}")
                return {}

    # ============================================================================
    # MAIN WORKFLOW METHODS
    # ============================================================================

    def run(self, paper_path: Optional[Path] = None, codebase_source: Optional[str] = None) -> dict:
        """
        Run the complete reproduction workflow.

        Args:
            paper_path: Path to the research paper PDF (if None, searches ./papers/ directory)
            codebase_source: Either GitHub URL or path to local codebase (if None, searches ./papers/codebases/)

        Returns:
            Dictionary with results and evaluation
        """
        logger.info("="*70)
        logger.info("Starting EVALLab...")
        logger.info("="*70)

        # Auto-detect paper if not provided
        if paper_path is None:
            workspace_root = Path(__file__).parent.parent
            papers_dir = workspace_root / "papers"

            if papers_dir.exists():
                pdf_files = list(papers_dir.glob("*.pdf"))
                if pdf_files:
                    paper_path = pdf_files[0]
                    logger.info(f"✓ Auto-detected paper: {paper_path.name}")
                else:
                    logger.error("No PDF files found in ./papers/ directory")
                    return {'error': 'No paper PDF found'}
            else:
                logger.error("./papers/ directory not found")
                return {'error': 'No paper directory found'}

        # Step 1: Check Ollama availability
        if not self.is_available():
            logger.error("Ollama is not running or not accessible!")
            logger.error(
                f"Please start Ollama and ensure it's running at {self.ollama_base_url}")
            return {'error': 'Ollama not available'}

        logger.info(f"✓ Connected to Ollama (model: {self.ollama_model})")

        # Log which paper is being parsed
        logger.info(f"Parsing paper: {paper_path}")

        # Step 2: Parse the paper (Stage 1)
        print("\n" + "="*80)
        print("\033[94m┌" + "─"*78 + "┐\033[0m")
        print("\033[94m│\033[0m" +
              "\033[1;96m STAGE 1/4: PAPER PARSING".center(78) + "\033[94m│\033[0m")
        print("\033[94m├" + "─"*78 + "┤\033[0m")
        print("\033[94m│\033[0m" +
              " 📄 Extracting text, figures, and GitHub URLs from PDF".ljust(78) + "\033[94m│\033[0m")
        print("\033[94m│\033[0m" +
              " 🔍 Parsing paper structure and metadata".ljust(78) + "\033[94m│\033[0m")
        print("\033[94m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        paper_content = self.paper_parser.parse_pdf(paper_path)
        logger.info(
            f"✓ Extracted {len(paper_content.raw_text)} characters from paper")

        if paper_content.github_urls:
            logger.info(
                f"✓ Found {len(paper_content.github_urls)} GitHub URLs in paper")
            for url in paper_content.github_urls:
                logger.info(f"  - {url}")

        # Step 3: Extract key sections using LLM
        print("\n" + "="*80)
        print("\033[93m┌" + "─"*78 + "┐\033[0m")
        print("\033[93m│\033[0m" +
              "\033[1;93m STAGE 1.5/4: EVALLAB SECTION EXTRACTION".center(78) + "\033[93m│\033[0m")
        print("\033[93m├" + "─"*78 + "┤\033[0m")
        print("\033[93m│\033[0m" +
              " 🤖 Using Ollama LLM to extract key sections".ljust(78) + "\033[93m│\033[0m")
        print("\033[93m│\033[0m" +
              " 📝 Identifying: Abstract, Methodology, Experiments, Results".ljust(78) + "\033[93m│\033[0m")
        print("\033[93m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        sections = self._extract_paper_sections(paper_content.raw_text)
        paper_content.abstract = sections.get('abstract', '')
        methodology = sections.get('methodology', '')
        experiments = sections.get('experiments', '')
        results = sections.get('results', '')

        # Ensure all are strings (join lists if needed)
        if isinstance(methodology, list):
            methodology = '\n'.join(str(x) for x in methodology)
        if isinstance(experiments, list):
            experiments = '\n'.join(str(x) for x in experiments)
        if isinstance(results, list):
            results = '\n'.join(str(x) for x in results)
        if isinstance(paper_content.abstract, list):
            paper_content.abstract = '\n'.join(str(x) for x in paper_content.abstract)

        paper_content.methodology = methodology
        paper_content.experiments = experiments
        paper_content.results = results

        logger.info(
            f"✓ Extracted abstract ({len(paper_content.abstract)} chars)")
        logger.debug(f"Abstract extracted: {paper_content.abstract[:500]}{'...' if len(paper_content.abstract) > 500 else ''}")
        if len(paper_content.abstract) < 100:
            logger.warning("Extracted abstract is very short. Extraction may have failed or missed content.")
        logger.info(
            f"✓ Extracted methodology ({len(paper_content.methodology)} chars)")
        logger.debug(f"Methodology extracted: {paper_content.methodology[:500]}{'...' if len(paper_content.methodology) > 500 else ''}")
        if len(paper_content.methodology) < 100:
            logger.warning("Extracted methodology is very short. Extraction may have failed or missed content.")
        logger.info(
            f"✓ Extracted experiments ({len(paper_content.experiments)} chars)")
        logger.debug(f"Experiments extracted: {paper_content.experiments[:500]}{'...' if len(paper_content.experiments) > 500 else ''}")
        if len(paper_content.experiments) < 100:
            logger.warning("Extracted experiments section is very short. Extraction may have failed or missed content.")

        # Step 4: Retrieve codebase (Stage 2 - NEW UNIFIED MODULE)
        print("\n" + "="*80)
        print("\033[92m┌" + "─"*78 + "┐\033[0m")
        print("\033[92m│\033[0m" +
              "\033[1;92m STAGE 2/4: CODE RETRIEVAL".center(78) + "\033[92m│\033[0m")
        print("\033[92m├" + "─"*78 + "┤\033[0m")
        print("\033[92m│\033[0m" +
              " 🔎 Priority: User path → GitHub (paper-specific) → Local dir (fallback)".ljust(78) + "\033[92m│\033[0m")
        print("\033[92m│\033[0m" +
              " 📦 Searching for experiment code and dependencies".ljust(78) + "\033[92m│\033[0m")
        print("\033[92m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        # Convert codebase_source to Path if it's a string
        local_path = Path(codebase_source) if codebase_source else None

        # Pass paper_path context to RepoRetriever for name-based fallbacks
        try:
            self.repo_retriever.paper_path = paper_path
        except Exception:
            pass

        codebase_path = self.repo_retriever.retrieve_code(
            github_urls=paper_content.github_urls,
            local_path=local_path
        )

        if not codebase_path:
            print("\n" + "="*80)
            print("\033[91m┌" + "─"*78 + "┐\033[0m")
            print("\033[91m│\033[0m" +
                "\033[1;91m ❌ NO CODEBASE FOUND".center(78) + "\033[91m│\033[0m")
            print("\033[91m├" + "─"*78 + "┤\033[0m")
            print("\033[91m│\033[0m" +
                " Unable to find experiment code from any source.".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" + " ".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" +
                " 💡 SOLUTION: Manually add codebase to ./papers/codebases/".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" + " ".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" +
                "   Steps:".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" +
                "   1. Create ./papers/codebases/ directory if it doesn't exist".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" +
                "   2. Place your experiment codebase inside it".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" +
                "   3. Run the agent again".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" + " ".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" +
                " Checked:".ljust(78) + "\033[91m│\033[0m")
            if local_path:
                print(
                  "\033[91m│\033[0m" + f"   ✗ User path: {local_path}".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m│\033[0m" +
                "   ✗ Local directory: ./papers/codebases/".ljust(78) + "\033[91m│\033[0m")
            if paper_content.github_urls:
                print("\033[91m│\033[0m" + f"   ✗ GitHub URLs: {len(paper_content.github_urls)} found but failed to clone".ljust(
                  78) + "\033[91m│\033[0m")
            else:
                print(
                    "\033[91m│\033[0m" + "   ✗ GitHub URLs: None found in paper".ljust(78) + "\033[91m│\033[0m")
            print("\033[91m└" + "─"*78 + "┘\033[0m")
            print("="*80 + "\n")
            logger.error("No codebase available!")
            return {'error': 'No codebase available - please add code to ./papers/codebases/'}

        logger.info(f"✓ Codebase retrieved at: {codebase_path}")

        # Step 5: Analyze codebase structure (Stage 3 - UNIFIED ANALYSIS & EXECUTION)
        print("\n" + "="*80)
        print("\033[95m┌" + "─"*78 + "┐\033[0m")
        print("\033[95m│\033[0m" +
              "\033[1;95m STAGE 3/4: EXPERIMENT EXECUTION".center(78) + "\033[95m│\033[0m")
        print("\033[95m├" + "─"*78 + "┤\033[0m")
        print("\033[95m│\033[0m" +
              " 🔬 Analyzing codebase structure and dependencies".ljust(78) + "\033[95m│\033[0m")
        print("\033[95m│\033[0m" +
              " ⚙️  Setting up environment and validating data".ljust(78) + "\033[95m│\033[0m")
        print("\033[95m│\033[0m" +
              " 🚀 Running experiments with reproducible seeds".ljust(78) + "\033[95m│\033[0m")
        print("\033[95m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        codebase_info = self.experiment_executor.analyze_codebase(
            codebase_path)
        logger.info(
            f"✓ Analyzed codebase (language: {codebase_info.language})")
        logger.info(
            f"✓ Found {len(codebase_info.entry_points)} potential entry points")
        logger.info(f"✓ Found {len(codebase_info.dependencies)} dependencies")

        # Validate data integrity before running experiments
        logger.info("\n[Stage 3.5/4] Validating data integrity...")
        validation_results = self.experiment_executor.validate_data_integrity(
            codebase_info.path)

        if not validation_results['valid']:
            logger.warning(
                "⚠️  Data validation failed - experiments may not reproduce correctly")

        if validation_results['file_stats']:
            total_size = sum(s.get('size_mb', 0)
                             for s in validation_results['file_stats'].values())
            logger.info(
                f"✓ Data validation complete - {len(validation_results['file_stats'])} files, {total_size:.1f}MB total")

        # Run experiments
        logger.info("\n[Stage 3.6/4] Running experiments...")
        experiment_results = self._run_experiments_unified(
            paper_content, codebase_info)

        if not experiment_results:
            logger.error("No experiments were run successfully")
            return {'error': 'Experiment execution failed'}

        logger.info(f"✓ Completed {len(experiment_results)} experiments")

        # Step 6: Evaluate results (Stage 4)
        print("\n" + "="*80)
        print("\033[96m┌" + "─"*78 + "┐\033[0m")
        print("\033[96m│\033[0m" +
              "\033[1;96m STAGE 4/4: RESULT EVALUATION".center(78) + "\033[96m│\033[0m")
        print("\033[96m├" + "─"*78 + "┤\033[0m")
        print("\033[96m│\033[0m" +
              " 📊 Comparing reproduced metrics to baseline results".ljust(78) + "\033[96m│\033[0m")
        print("\033[96m│\033[0m" +
              " 📈 Generating visualizations and performance reports".ljust(78) + "\033[96m│\033[0m")
        print("\033[96m│\033[0m" +
              " ✅ Calculating success rate and deviation metrics".ljust(78) + "\033[96m│\033[0m")
        print("\033[96m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        # Load ALL experiment results from all output directories
        experiment_sets = self.result_evaluator.load_all_experiment_results(
            codebase_info.path)

        if not experiment_sets:
            logger.error("No experiment result sets found")
            return {'error': 'No experiment results found'}

        logger.info(f"✓ Loaded {len(experiment_sets)} experiment sets")

        # Extract all metrics from all experiments
        all_reproduced_metrics = self.result_evaluator.extract_all_metrics_from_experiments(
            experiment_sets)
        logger.info(
            f"✓ Extracted {len(all_reproduced_metrics)} total metrics from all experiments")

        # Try to extract baseline from paper AND report.md files
        baseline = self.result_evaluator.extract_baseline_from_paper(
            paper_content.results or paper_content.raw_text,
            codebase_path=codebase_info.path  # Pass codebase path for report.md parsing
        )
        logger.info(f"✓ Extracted {len(baseline.metrics)} baseline metrics")
        logger.info(f"  Source: {baseline.source}")


        # Compare all reproduced metrics to baseline
        comparisons = self.result_evaluator.compare_results(
            baseline, all_reproduced_metrics)
        logger.info(f"✓ Generated {len(comparisons)} metric comparisons")

        # --- Per-example diff integration ---
        import shutil
        # Use consistent directory name from paper_path.stem
        paper_viz_dir = Path('outputs') / 'visualizations' / paper_path.stem
        
        # Establish baseline: use first run as baseline for future comparisons
        baseline_dir = codebase_info.path / 'baseline'
        baseline_log_path = baseline_dir / 'log.csv'
        reproduced_log_source = codebase_info.path / 'log.csv'  # Current run's log.csv
        
        # If no baseline exists, establish current run as baseline
        if not baseline_log_path.exists() and reproduced_log_source.exists():
            logger.info(f"Establishing baseline for {paper_path.stem} from current run")
            baseline_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(reproduced_log_source, baseline_log_path)
            logger.info(f"✓ Baseline established at {baseline_log_path}")
            logger.info("  Future runs will be compared against this baseline")
        
        reproduced_log_path = paper_viz_dir / 'log.csv'
        viz_log_dir = paper_viz_dir
        viz_log_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy reproduced log.csv to viz directory
        if reproduced_log_source.exists() and reproduced_log_source.stat().st_size > 0:
            shutil.copy2(reproduced_log_source, reproduced_log_path)
        
        # Copy baseline log to visualization dir for UI and diffing (optional)
        if baseline_log_path.exists() and baseline_log_path.stat().st_size > 0:
            shutil.copy2(baseline_log_path, viz_log_dir / 'baseline_log.csv')

        # Decide whether to skip per-example comparison (e.g., for decontextualisation paper)
        current_paper_name = str(paper_path.stem).lower() if paper_path else ""
        skip_per_example = "decontextual" in current_paper_name
        if skip_per_example:
            logger.info("Skipping per-example comparison for decontextualisation paper as requested.")

        # Only proceed if both baseline and reproduced per-example logs exist and are non-empty
        if (not skip_per_example) and baseline_log_path.exists() and baseline_log_path.stat().st_size > 0 and reproduced_log_path.exists() and reproduced_log_path.stat().st_size > 0:
            baseline_log = self._load_per_example_results(baseline_log_path)
            reproduced_log = self._load_per_example_results(reproduced_log_path)
            per_example_diffs = self.result_evaluator.compare_per_example_results(baseline_log, reproduced_log)
            logger.info(f"✓ Compared per-example results: {len(per_example_diffs)} mismatches found.")
            
            # Generate diff table
            diff_html = self.result_evaluator.generate_per_example_diff_table(per_example_diffs)
            
            # Generate full tables for baseline and reproduced
            baseline_table = self.result_evaluator.generate_per_example_table(baseline_log, "Baseline Results")
            reproduced_table = self.result_evaluator.generate_per_example_table(reproduced_log, "Reproduced Results")
            
            # Combine into one HTML file
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
                    <h2>Differences Found: {len(per_example_diffs)}</h2>
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
            
            with open(viz_log_dir / 'per_example_diffs.html', 'w', encoding='utf-8') as f:
                f.write(combined_html)
            import csv
            if per_example_diffs:
                with open(viz_log_dir / 'per_example_diffs.csv', 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=per_example_diffs[0].keys())
                    writer.writeheader()
                    writer.writerows(per_example_diffs)
            logger.info(f"✓ Per-example diffs saved to {viz_log_dir / 'per_example_diffs.html'} and .csv")
        else:
            logger.info("Per-example baseline or reproduced log.csv not found or empty; skipping per-example diff.")

        # Generate comprehensive report
        report = self.result_evaluator.generate_report(comparisons)
        logger.info("\n" + report)

        # Generate summary statistics
        print("\n" + "="*80)
        print("\033[93m┌" + "─"*78 + "┐\033[0m")
        print("\033[93m│\033[0m" +
              "\033[1;93m 📊 SUMMARY STATISTICS".center(78) + "\033[93m│\033[0m")
        print("\033[93m├" + "─"*78 + "┤\033[0m")
        print("\033[93m│\033[0m" +
              " 📈 Performance metrics and success rates".ljust(78) + "\033[93m│\033[0m")
        print("\033[93m│\033[0m" +
              " 🎯 Deviation analysis and accuracy scores".ljust(78) + "\033[93m│\033[0m")
        print("\033[93m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        summary_stats = self.result_evaluator.generate_summary_statistics(
            comparisons)
        logger.info(summary_stats)

        # Get LLM analysis of differences
        analysis = ""
        if comparisons:
            print("\n" + "="*80)
            print("\033[94m┌" + "─"*78 + "┐\033[0m")
            print("\033[94m│\033[0m" +
                  "\033[1;94m 🤖 EVALLAB ANALYSIS".center(78) + "\033[94m│\033[0m")
            print("\033[94m├" + "─"*78 + "┤\033[0m")
            print("\033[94m│\033[0m" +
                  " 🧠 AI-powered analysis of result differences".ljust(78) + "\033[94m│\033[0m")
            print("\033[94m│\033[0m" +
                  " 💡 Insights into methodology and experiment variations".ljust(78) + "\033[94m│\033[0m")
            print("\033[94m└" + "─"*78 + "┘\033[0m")
            print("="*80 + "\n")

            # Ensure methodology and experiments are strings for concatenation
            methodology = paper_content.methodology
            experiments = paper_content.experiments
            if isinstance(methodology, list):
                methodology = "\n".join(str(x) for x in methodology)
            if isinstance(experiments, list):
                experiments = "\n".join(str(x) for x in experiments)
            analysis = self.result_evaluator.analyze_differences_with_llm(
                comparisons,
                methodology + "\n" + experiments
            )
            logger.info(analysis)

        # Generate comprehensive conclusions and recommendations
        print("\n" + "="*80)
        print("\033[92m┌" + "─"*78 + "┐\033[0m")
        print("\033[92m│\033[0m" +
              "\033[1;92m 📋 CONCLUSIONS & RECOMMENDATIONS".center(78) + "\033[92m│\033[0m")
        print("\033[92m├" + "─"*78 + "┤\033[0m")
        print("\033[92m│\033[0m" +
              " ✅ Comprehensive analysis of reproduction success".ljust(78) + "\033[92m│\033[0m")
        print("\033[92m│\033[0m" +
              " 🔍 Key findings and improvement recommendations".ljust(78) + "\033[92m│\033[0m")
        print("\033[92m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        conclusions = self.result_evaluator.generate_comprehensive_conclusions(
            comparisons,
            experiment_sets,
            baseline,
            paper_content.methodology + "\n" + paper_content.experiments
        )
        logger.info(conclusions)

        # Generate visualizations
        print("\n" + "="*80)
        print("\033[95m┌" + "─"*78 + "┐\033[0m")
        print("\033[95m│\033[0m" +
              "\033[1;95m 📊 VISUALIZATION GENERATION".center(78) + "\033[95m│\033[0m")
        print("\033[95m├" + "─"*78 + "┤\033[0m")
        print("\033[95m│\033[0m" +
              " 📈 Creating charts: bar, scatter, heatmap, histogram".ljust(78) + "\033[95m│\033[0m")
        print("\033[95m│\033[0m" +
              " 🎨 Generating HTML dashboard and CSV exports".ljust(78) + "\033[95m│\033[0m")
        print("\033[95m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        try:
            # Save visualizations in per-paper subdirectory
            viz_dir = Path('outputs') / 'visualizations' / paper_path.stem
            paper_name = paper_path.stem  # Get filename without extension
            viz_files = self.result_evaluator.generate_visualizations(
                comparisons,
                output_dir=viz_dir,
                paper_name=paper_name,
                codebase_path=codebase_info.path  # Pass codebase path for test_details
            )
            logger.info(f"✓ Generated {len(viz_files)} visualization files")
            logger.info(
                f"📊 View visualizations: {viz_dir / 'visualizations.html'}")

            # Generate top-level dashboard listing all papers
            self.result_evaluator.generate_visualizations_index(
                Path('outputs') / 'visualizations')
        except Exception as e:
            logger.error(f"Failed to generate visualizations: {e}")
            import traceback
            traceback.print_exc()

        # Save results
        self._save_results(paper_path, comparisons, report, summary_stats,
                           analysis, conclusions, experiment_sets)

        print("\n" + "="*80)
        print("\033[92m┌" + "─"*78 + "┐\033[0m")
        print("\033[92m│\033[0m" +
              "\033[1;92m ✅ WORKFLOW COMPLETED SUCCESSFULLY!".center(78) + "\033[92m│\033[0m")
        print("\033[92m├" + "─"*78 + "┤\033[0m")
        print("\033[92m│\033[0m" +
              " 🎉 All 4 stages completed".ljust(78) + "\033[92m│\033[0m")
        print("\033[92m│\033[0m" +
              " 📁 Results saved to outputs/ directory".ljust(78) + "\033[92m│\033[0m")
        print("\033[92m│\033[0m" +
              " 📊 Visualizations available in outputs/visualizations/".ljust(78) + "\033[92m│\033[0m")
        print("\033[92m└" + "─"*78 + "┘\033[0m")
        print("="*80 + "\n")

        return {
            'paper_content': paper_content,
            'codebase_info': codebase_info,
            'experiment_results': experiment_results,
            'baseline_metrics': baseline,
            'comparisons': comparisons,
            'report': report,
            'conclusions': conclusions
        }

    def _extract_paper_sections(self, raw_text: str) -> dict:
        """Use EVALLab to extract key sections from paper."""
        system_prompt = (
            "You are an expert at reading research papers. "
            "Extract the following sections: abstract, methodology, experiments, and results. "
            "Return ONLY valid JSON with these exact keys: 'abstract', 'methodology', 'experiments', 'results'. "
            "Do NOT use a 'sections' array or any other structure. "
            "Each value should be a full, detailed paragraph or set of paragraphs, not a summary. "
            "Do not truncate or omit information. "
            "If a section is long, include as much as possible. "
            "Do not include markdown, explanations, or any text outside the JSON object."
        )
        # Truncate text to fit in context window (increase limit if possible)
        truncated_text = raw_text[:16000]

        user_prompt = (
            "Extract the following sections from this research paper and return as a flat JSON object. "
            "The JSON must have ONLY these keys: 'abstract', 'methodology', 'experiments', 'results'. "
            "Do NOT use a 'sections' array or any other structure. "
            "Each section should be a full, detailed paragraph or set of paragraphs, not a summary. "
            "Do not truncate or omit information. "
            "If a section is long, include as much as possible. "
            "Return ONLY a JSON object (no markdown, no explanation):\n"
            "{\"abstract\": \"text here\", \"methodology\": \"text here\", "
            "\"experiments\": \"text here\", \"results\": \"text here\"}"
        ) + f"\nPaper text:\n{truncated_text}"
        try:
            sections = self.extract_json(user_prompt, system_prompt)
            # Canonical keys and synonyms
            canonical_keys = {
                "abstract": ["abstract"],
                "methodology": [
                    "methodology", "methods", "approach", "system overview", "framework", "implementation", "setup", "procedure",
                    "utilizing", "training", "model training", "attack recipes", "model architecture", "model details", "pipeline", "algorithm", "utilizing textattack to improve nlp models", "model training", "data augmentation", "adversarial training"
                ],
                "experiments": [
                    "experiments", "experiment", "evaluation", "analysis", "study", "case study", "empirical study", "experimentation", "robustness", "evaluating robustness of custom models", "experiment details", "experiment setup", "experiment results"
                ],
                "results": ["results", "findings", "outcomes", "discussion", "conclusion", "summary"]
            }
            def flatten_section(val):
                # Recursively flatten nested dicts/lists to extract all strings
                if isinstance(val, str):
                    return val
                elif isinstance(val, dict):
                    result = []
                    for v in val.values():
                        flat = flatten_section(v)
                        if flat:
                            result.append(flat)
                    return '\n'.join(result)
                elif isinstance(val, list):
                    result = []
                    for v in val:
                        flat = flatten_section(v)
                        if flat:
                            result.append(flat)
                    return '\n'.join(result)
                return ""

            default_sections = {k: "" for k in canonical_keys}
            if isinstance(sections, dict):
                # For each canonical key, look for synonyms and flatten
                for canon, synonyms in canonical_keys.items():
                    found = False
                    for syn in synonyms:
                        for key in sections:
                            if key.lower() == syn:
                                val = flatten_section(sections[key])
                                if val:
                                    default_sections[canon] = val
                                    found = True
                                    break
                        if found:
                            break
            # If all sections are empty, fallback
            if all(not v.strip() for v in default_sections.values()):
                logger.warning("LLM returned empty or invalid sections, falling back to regex extraction.")
                return self._simple_section_extraction(raw_text)
            # If any section is missing, merge in regex fallback for that section
            fallback_sections = self._simple_section_extraction(raw_text)
            for k in default_sections:
                if not default_sections[k].strip() and fallback_sections.get(k, "").strip():
                    logger.info(f"Merging fallback content for missing section: {k}")
                    default_sections[k] = fallback_sections[k]
            return default_sections
        except Exception as e:
            logger.error(f"Failed to extract sections with LLM: {e}")
            logger.debug(f"Attempting simple text extraction as fallback...")
            return self._simple_section_extraction(raw_text)

    def _simple_section_extraction(self, text: str) -> dict:
        """Regex-based section extraction supporting numbered and named headers."""
        import re
        sections = {"abstract": "", "methodology": "", "experiments": "", "results": ""}

        # Canonical mapping and keyword heuristics (compatible with decontextualisation logic)
        section_map = {
            'abstract': 'abstract',
            'introduction': None,  # skip
            'background': None,
            'related work': None,
            'system overview': 'methodology',
            'framework': 'methodology',
            'methodology': 'methodology',
            'methods': 'methodology',
            'approach': 'methodology',
            'implementation': 'methodology',
            'setup': 'methodology',
            'procedure': 'methodology',
            'utilizing': 'methodology',
            'training': 'methodology',
            'model training': 'methodology',
            'experiments': 'experiments',
            'experiment': 'experiments',
            'evaluation': 'experiments',
            'analysis': 'experiments',
            'study': 'experiments',
            'case study': 'experiments',
            'empirical study': 'experiments',
            'experimentation': 'experiments',
            'results': 'results',
            'findings': 'results',
            'outcomes': 'results',
            'discussion': 'results',
            'conclusion': 'results',
            'summary': 'results',
        }

        # Heuristic keyword lists for fuzzy matching
        methodology_keywords = [
            'method', 'approach', 'framework', 'system overview', 'implementation', 'setup', 'procedure', 'utiliz', 'train', 'model training'
        ]
        experiments_keywords = [
            'experiment', 'evaluation', 'analysis', 'study', 'case study', 'empirical', 'experimentation', 'robustness'
        ]
        results_keywords = [
            'result', 'finding', 'outcome', 'discussion', 'conclusion', 'summary'
        ]

        # Regex for numbered or named section headers (robust to e.g. '4.1 Model Training', '4 Utilizing ...')
        header_pattern = re.compile(r'^(\d+(?:\.\d+)*[\.)]?\s+)?([A-Z][A-Za-z0-9 \-/]+)$', re.MULTILINE)

        # Find all section headers and their positions
        matches = list(header_pattern.finditer(text))
        if not matches:
            # fallback: try to find abstract only
            abstract_match = re.search(r'(?i)abstract[:\s\n]+(.*?)(?=\n\n|\n[A-Z])', text, re.DOTALL)
            if abstract_match:
                sections['abstract'] = abstract_match.group(1).strip()[:2000]
            else:
                # fallback: take first 1000 chars from top of document as abstract
                sections['abstract'] = text[:1000].strip()
            return sections

        # Build a list of (header, start, end)
        section_spans = []
        for i, match in enumerate(matches):
            header_text = match.group(2).strip()
            start = match.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(text)
            section_spans.append((header_text, start, end))

        # Assign content to canonical sections using both direct mapping and keyword heuristics
        for header_text, start, end in section_spans:
            header_lower = header_text.lower()
            canonical = section_map.get(header_lower)
            content = text[start:end].strip()
            if canonical:
                sections[canonical] += content + '\n'
            else:
                # Fuzzy keyword mapping for non-exact headers
                if header_lower == 'abstract':
                    sections['abstract'] = content[:2000]
                    continue
                # Methodology
                if any(kw in header_lower for kw in methodology_keywords):
                    sections['methodology'] += content + '\n'
                    continue
                # Experiments
                if any(kw in header_lower for kw in experiments_keywords):
                    sections['experiments'] += content + '\n'
                    continue
                # Results
                if any(kw in header_lower for kw in results_keywords):
                    sections['results'] += content + '\n'

        # Truncate to reasonable length (more for methodology/experiments)
        for k in sections:
            if k in ("methodology", "experiments"):
                sections[k] = sections[k][:8000]
            else:
                sections[k] = sections[k][:4000]
        return sections

        for key, value in data.items():
            current_key = f"{prefix}/{key}" if prefix else key

            if isinstance(value, dict):
                # Check if this dict contains metrics
                if 'metrics' in value:
                    # Extract metrics from this level
                    metric_dict = value['metrics']
                    for metric_name, metric_value in metric_dict.items():
                        if isinstance(metric_value, dict):
                            # Handle metrics with multiple thresholds (e.g., recall@1, recall@5)
                            for threshold, val in metric_value.items():
                                if isinstance(val, (int, float)):
                                    metrics[f"{metric_name}@{threshold}"] = float(
                                        val)
                        elif isinstance(metric_value, (int, float)):
                            metrics[metric_name] = float(metric_value)
                else:
                    # Recurse into nested dicts
                    nested = self._extract_metrics_from_nested_dict(
                        value, current_key)
                    metrics.update(nested)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                # Direct numeric value
                metrics[current_key] = float(value)

        return metrics

    def _run_experiments_unified(self, paper_content: PaperContent,
                                 codebase_info: CodebaseInfo) -> list:
        """Run experiments using the unified experiment executor (Stage 3)."""
        # Set up environment
        logger.info("Setting up experiment environment...")
        setup_success = self.experiment_executor.setup_environment(
            codebase_info.path,
            codebase_info.dependencies
        )

        if not setup_success:
            logger.warning(
                "Environment setup had issues, proceeding anyway...")

        # Check for README instructions
        priority_scripts = []
        if codebase_info.readme_content:
            # Look for python commands in README
            python_cmds = re.findall(r'python[3]?\s+([\w_/\.]+\.py)(?:\s+(.*))?',
                                     codebase_info.readme_content, re.IGNORECASE)
            for script_name, args in python_cmds:
                script_path = codebase_info.path / script_name
                if script_path.exists():
                    logger.info(
                        f"Found priority script from README: {script_name}")
                    priority_scripts.append(
                        (script_path, args.strip().split() if args else []))

        results = []


        # Special handling: if this is an AIX360 codebase, run the RBM metrics script
        if 'aix360' in str(codebase_info.path).lower():
            rbm_metrics_script = codebase_info.path / 'run_rbm_metrics.py'
            if rbm_metrics_script.exists():
                logger.info(f"Running AIX360 RBM metrics script: {rbm_metrics_script}")
                config = ExperimentConfig(
                    script_path=rbm_metrics_script,
                    args=[],
                    env_vars={},
                    working_dir=codebase_info.path,
                    timeout=self.config['experiment']['timeout']
                )
                result = self.experiment_executor.run_experiment(config)
                results.append(result)
                if result.success:
                    logger.info(f"  ✓ Success (duration: {result.duration:.2f}s)")
                else:
                    logger.warning(f"  ✗ Failed: {result.stderr[:200]}")
        
        # Special handling: if this is a textattack codebase, run the smaller IMDB LSTM training script
        if 'textattack' in str(codebase_info.path).lower():
            # Prefer attack script for faster metric extraction
            attack_script = codebase_info.path / 'examples' / 'attack' / 'attack_roberta_sst2_textfooler.sh'
            if attack_script.exists():
                logger.info(f"Running textattack attack script: {attack_script}")
                config = ExperimentConfig(
                    script_path=attack_script,
                    args=[],
                    env_vars={},
                    working_dir=codebase_info.path,
                    timeout=self.config['experiment']['timeout']
                )
                result = self.experiment_executor.run_experiment(config)
                results.append(result)
                if result.success:
                    logger.info(f"  ✓ Success (duration: {result.duration:.2f}s)")
                else:
                    logger.warning(f"  ✗ Failed: {result.stderr[:200]}")
            else:
                # Fallback to train script if attack script is missing
                train_script = codebase_info.path / 'examples' / 'train' / 'train_lstm_imdb_sentiment_classification.sh'
                if train_script.exists():
                    logger.info(f"Running textattack train script: {train_script}")
                    config = ExperimentConfig(
                        script_path=train_script,
                        args=[],
                        env_vars={},
                        working_dir=codebase_info.path,
                        timeout=self.config['experiment']['timeout']
                    )
                    result = self.experiment_executor.run_experiment(config)
                    results.append(result)
                    if result.success:
                        logger.info(f"  ✓ Success (duration: {result.duration:.2f}s)")
                    else:
                        logger.warning(f"  ✗ Failed: {result.stderr[:200]}")

        # Run priority scripts from README first
        for script_path, args in priority_scripts[:2]:  # Limit to 2
            logger.info(
                f"Running priority script: {script_path.name} {' '.join(args)}")

            config = ExperimentConfig(
                script_path=script_path,
                args=args,
                env_vars={},
                working_dir=codebase_info.path,
                timeout=self.config['experiment']['timeout']
            )

            result = self.experiment_executor.run_experiment(config)
            results.append(result)

            if result.success:
                logger.info(f"  ✓ Success (duration: {result.duration:.2f}s)")
            else:
                logger.warning(f"  ✗ Failed: {result.stderr[:200]}")

        # If no priority scripts, use entry points
        if not results:
            for entry_point in codebase_info.entry_points[:3]:  # Limit to 3
                logger.info(f"Running: {entry_point.name}")

                config = ExperimentConfig(
                    script_path=entry_point,
                    args=[],
                    env_vars={},
                    working_dir=codebase_info.path,
                    timeout=self.config['experiment']['timeout']
                )

                result = self.experiment_executor.run_experiment(config)
                results.append(result)

                if result.success:
                    logger.info(
                        f"  ✓ Success (duration: {result.duration:.2f}s)")
                else:
                    logger.warning(f"  ✗ Failed: {result.stderr[:200]}")

        return [r for r in results if r.success]

    def extract_and_store_paper_metrics(self, paper_content: PaperContent, output_dir: Path):
        """Extract metrics from the paper's results section and save as ground truth for comparison."""
        metrics = {}
        if paper_content.results:
            metrics = self._extract_metrics_from_text(paper_content.results)
        # Optionally, also try from experiments or methodology if results is empty
        if not metrics and paper_content.experiments:
            metrics = self._extract_metrics_from_text(paper_content.experiments)
        if metrics:
            with open(output_dir / 'paper_metrics.json', 'w') as f:
                json.dump(metrics, f, indent=2)
            logger.info(f"Extracted paper metrics: {metrics}")
        else:
            logger.warning("No paper metrics found in results section.")

    def _save_results(self, paper_path: Path, comparisons: list,
                      report: str, summary_stats: str, analysis: str,
                      conclusions: str, experiment_sets: list):
        """Save comprehensive results with full execution log to output directory."""

        # Save results and log in per-paper visualizations directory
        viz_dir = Path('outputs') / 'visualizations' / paper_path.stem
        viz_dir.mkdir(parents=True, exist_ok=True)
        output_file = viz_dir / f"{paper_path.stem}_results.txt"
        log_file = viz_dir / 'agent_execution.log'

        with open(output_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("="*100 + "\n")
            f.write(
                "EVALLab: RESEARCH PAPER REPRODUCTION AGENT - COMPLETE EXECUTION LOG\n")
            f.write("="*100 + "\n\n")

            f.write(f"Paper: {paper_path.name}\n")
            f.write(f"Experiment Sets Analyzed: {len(experiment_sets)}\n")
            f.write(f"Total Metric Comparisons: {len(comparisons)}\n")
            f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n" + "="*100 + "\n\n")

            # Section 1: Full Execution Log
            f.write("╔" + "═"*98 + "╗\n")
            f.write("║" + " SECTION 1: COMPLETE EXECUTION LOG ".center(98) + "║\n")
            f.write("╚" + "═"*98 + "╝\n\n")

            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as log:
                    f.write(log.read())
            else:
                f.write("[Log file not found]\n")

            f.write("\n" + "="*100 + "\n\n")

            # Section 2: Detailed Results
            f.write("╔" + "═"*98 + "╗\n")
            f.write(
                "║" + " SECTION 2: REPRODUCTION RESULTS EVALUATION ".center(98) + "║\n")
            f.write("╚" + "═"*98 + "╝\n\n")
            f.write(report + "\n\n")

            # Section 3: Summary Statistics
            f.write("╔" + "═"*98 + "╗\n")
            f.write("║" + " SECTION 3: SUMMARY STATISTICS ".center(98) + "║\n")
            f.write("╚" + "═"*98 + "╝\n\n")
            f.write(summary_stats + "\n\n")

            # Section 4: LLM Analysis
            if analysis:
                f.write("╔" + "═"*98 + "╗\n")
                f.write("║" + " SECTION 4: EVALLAB ANALYSIS ".center(98) + "║\n")
                f.write("╚" + "═"*98 + "╝\n\n")
                f.write(analysis + "\n\n")

            # Section 5: Conclusions
            if conclusions:
                f.write("╔" + "═"*98 + "╗\n")
                f.write(
                    "║" + " SECTION 5: CONCLUSIONS & RECOMMENDATIONS ".center(98) + "║\n")
                f.write("╚" + "═"*98 + "╝\n\n")
                f.write(conclusions + "\n\n")

            # Footer
            f.write("="*100 + "\n")
            f.write("END OF REPORT\n")
            f.write("="*100 + "\n")

        logger.info(f"✓ Results saved to: {output_file}")
        logger.info(f"✓ Execution log saved to: {log_file}")


def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Local Research Paper Reproduction Agent - Auto-detects paper and code from workspace'
    )
    parser.add_argument(
        'paper_path',
        nargs='?',  # Make optional
        type=Path,
        help='Path to research paper PDF (default: auto-detect from ./papers/)'
    )
    parser.add_argument(
        '--codebase',
        type=str,
        help='GitHub URL or local path to codebase (default: auto-detect from ./papers/codebases/)'
    )
    parser.add_argument(
        '--config',
        type=Path,
        help='Path to config.yaml file'
    )

    args = parser.parse_args()

    # Validate paper path if provided
    if args.paper_path and not args.paper_path.exists():
        print(f"Error: Paper file not found: {args.paper_path}")
        sys.exit(1)

    # Create and run agent
    agent = ReproductionAgent(config_path=args.config)
    results = agent.run(args.paper_path, args.codebase)

    if 'error' in results:
        print(f"Error: {results['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
