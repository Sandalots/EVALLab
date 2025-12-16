# EVALLab

A local LLM-powered agent that reproduces research paper experiments using Ollama3. Features a clean 4-stage architecture with 94.2% metric reproduction accuracy currently on the target input 'Decontextualization' Research Paper.

## Architecture

The agent uses the following **4-stage pipeline**:

1. **Stage 1: Paper Parser** - Extracts text, (Abstract, methodology, experiment, figures) from the input Research Paper
2. **Stage 2: Repo Retriever** - Finds codebase (local → GitHub priority)
3. **Stage 3: Experiment Executor** - Analyses Paper codebase + runs experiments from context of first 2 stages
4. **Stage 4: Result Evaluator** - Compares results + generates visualizations from baseline paper authors results, returns plots, HTML Visualisation dashboard, csv and log data, as-well as full command line logging.

## Quick Start

1. **Install and start Ollama with llama3:**

   ```bash
   ollama serve
   ollama pull llama3
   ```

2. **Set up Python environment:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Place paper code in the correct directory:**
   - Put the `supplementary_material` directory inside `papers/codebases/`
   - Final structure: `papers/codebases/supplementary_material/`

4. **Run the agent:**

   ```bash
   # Run with auto-detection (default paper and codebase)
   python3 run_EVALLab.py

   # Run with a specific paper PDF
   python3 run_EVALLab.py papers/YourPaper.pdf

   # Run with a specific paper and local codebase directory
   python3 run_EVALLab.py papers/YourPaper.pdf --code ./papers/codebases/your_code_dir

   # If no GitHub repo is found in the paper, the agent will use the provided local codebase path
   # or fallback to papers/codebases/ if available.
   ```