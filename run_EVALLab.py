"""===============================================================================
EVALLAB ENTRYPOINT: RUNS THE EVALLAB PIPELINE

This script is the main entrypoint for EVALLab. It parses command-line arguments,
initializes the agent's pipeline, and orchestrates the full research paper reproduction workflow, from retrieving and reading the paper, codebase, running experiments and returning evaulative results and benchmarks back to the EVALLab end-user.
===============================================================================
"""

from src.pipeline import ReproductionAgent, ColoredFormatter
import sys
import time
import tracemalloc
import argparse
from pathlib import Path
import json
import traceback
import logging


# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def setup_logging(output_dir):
    log_file = Path(output_dir) / 'agent_execution.log'

    # Remove all handlers associated with the root logger object.
    root_logger = logging.getLogger()

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(logging.INFO)

    # File handler (plain)
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # Console handler (color)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter(datefmt='%Y-%m-%d %H:%M:%S'))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# entrypoint for EVALLab
def main():
    parser = argparse.ArgumentParser(description="EVALLab: Automated Research Reproduction Agent")
    parser.add_argument('--paper', type=str, help='Path to the research paper PDF')
    parser.add_argument('--code', type=str, help='Path or URL to the codebase')

    args = parser.parse_args()

    start_time = time.time()
    tracemalloc.start()

    # Banner and intro
    print("\n" + "=" * 100)
    print("\033[1;93mEVALLab: Automated Research Reproduction Agent\033[0m".center(100))
    print("=" * 100 + "\n")

    # ... (rest of main function body)
    # NOTE: avoid parsing args twice (can cause subtle issues)

    # Clear screen for fresh output (optional)
    print("\n" * 2)

    # Main EVALLab Header
    print("=" * 100)
    print("\033[1;96m" + "█" * 100 + "\033[0m")
    print("\033[1;96m█" + " " * 98 + "█\033[0m")
    print("\033[1;96m█" + "🔬 EVALLab: Research Paper Reproduction Agent".center(98) + "█\033[0m")
    print("\033[1;96m█" + " " * 98 + "█\033[0m")
    print("\033[1;96m" + "█" * 100 + "\033[0m")
    print("=" * 100)

    # Show command-line usage if arguments provided
    if args.paper or args.code:
        print("\n\033[1;93m📋 Command-Line Mode:\033[0m")

        if args.paper:
            print(f"  Paper: {args.paper}")

        if args.code:
            print(f"  Code: {args.code}")
        print()

    # Main EVALLab Header
    print("=" * 100)
    print("\033[1;96m" + "█" * 100 + "\033[0m")
    print("\033[1;96m█" + " " * 98 + "█\033[0m")
    print("\033[1;96m█" + "🔬 EVALLab: Research Paper Reproduction Agent".center(98) + "█\033[0m")
    print("\033[1;96m█" + " " * 98 + "█\033[0m")
    print("\033[1;96m" + "█" * 100 + "\033[0m")
    print("=" * 100)

    # What is EVALLab?
    print("\n\033[1;93m┌" + "─" * 98 + "┐\033[0mp")
    print("\033[1;93m│\033[0m" + "\033[1;97m WHAT IS EVALLAB?\033[0m".center(98) + "\033[1;93m│\033[0m")
    print("\033[1;93m├" + "─" * 98 + "┤\033[0m")
    print("\033[1;93m│\033[0m" + " An autonomous AI agent that reproduces computational experiments from research papers.".ljust(98) + "\033[1;93m│\033[0m")
    print("\033[1;93m│\033[0m" + " It parses PDFs, retrieves code, runs experiments, and validates results against baselines.".ljust(98) + "\033[1;93m│\033[0m")
    print("\033[1;93m│\033[0m" + " ".ljust(98) + "\033[1;93m│\033[0m")
    print("\033[1;93m│\033[0m" + " 🎯 Goal: Verify reproducibility of published research with 94.2% accuracy".ljust(98) + "\033[1;93m│\033[0m")
    print("\033[1;93m└" + "─" * 98 + "┘\033[0m")

    # 4-Stage Pipeline Overview
    print("\n\033[1;92m┌" + "─" * 98 + "┐\033[0m")
    print("\033[1;92m│\033[0m" + "\033[1;97m 4-STAGE REPRODUCTION PIPELINE\033[0m".center(98) + "\033[1;92m│\033[0m")
    print("\033[1;92m├" + "─" * 98 + "┤\033[0m")
    print("\033[1;92m│\033[0m" + " ".ljust(98) + "\033[1;92m│\033[0m")
    print("\033[1;92m│\033[0m" + "   \033[1;94m[1] PAPER PARSING\033[0m       → Extracts text, (Abstract, methodology, experiment, figures) from the input Research Paper".ljust(98) + "\033[1;92m│\033[0m")
    print("\033[1;92m│\033[0m" + "   \033[1;94m[2] CODE RETRIEVAL\033[0m      → Find code (local → GitHub) with smart detection".ljust(98) + "\033[1;92m│\033[0m")
    print("\033[1;92m│\033[0m" + "   \033[1;94m[3] EXPERIMENT RUN\033[0m      → Analyze codebase, setup environment, execute experiments".ljust(98) + "\033[1;92m│\033[0m")
    print("\033[1;92m│\033[0m" + "   \033[1;94m[4] RESULT EVALUATION\033[0m   → Compare metrics, generate visualizations & reports".ljust(98) + "\033[1;92m│\033[0m")
    print("\033[1;92m│\033[0m" + " ".ljust(98) + "\033[1;92m│\033[0m")
    print("\033[1;92m└" + "─" * 98 + "┘\033[0m")

    # What You Get
    print("\n\033[1;95m┌" + "─" * 98 + "┐\033[0m")
    print("\033[1;95m│\033[0m" + "\033[1;97m OUTPUT & DELIVERABLES\033[0m".center(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m├" + "─" * 98 + "┤\033[0m")
    print("\033[1;95m│\033[0m" + " ".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + "   📋 Complete Execution Log  → Full CLI output with all stages and colored metrics".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + "   📊 Summary Statistics      → Success rate, deviation metrics, performance grades".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + "   🤖 EVALLab Analysis            → AI-powered insights into result differences".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + "   📋 Conclusions             → Comprehensive findings and improvement recommendations".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + "   📈 Visualizations          → 7+ charts (bar, scatter, heatmap, histogram, tables)".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + "   🌐 HTML Dashboard          → Interactive results browser with embedded images".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + "   📁 CSV Exports             → Raw data for custom analysis".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m│\033[0m" + " ".ljust(98) + "\033[1;95m│\033[0m")
    print("\033[1;95m└" + "─" * 98 + "┘\033[0m")

    # Next Steps Section
    print("\n\033[1;96m┌" + "─" * 98 + "┐\033[0m")
    print("\033[1;96m│\033[0m" + "\033[1;97m NEXT STEPS AFTER COMPLETION\033[0m".center(98) + "\033[1;96m│\033[0m")
    print("\033[1;96m├" + "─" * 98 + "┤\033[0m")
    print("\033[1;96m│\033[0m" + " ".ljust(98) + "\033[1;96m│\033[0m")

    print("\033[1;96m│\033[0m" + "   1. Review outputs/[paper_name]_results.txt for complete execution log".ljust(98) + "\033[1;96m│\033[0m")
    print("\033[1;96m│\033[0m" + "   2. Open outputs/visualizations/visualizations.html in browser".ljust(98) + "\033[1;96m│\033[0m")
    print("\033[1;96m│\033[0m" + "   3. Analyze outputs/visualizations/detailed_comparison.csv for raw metrics".ljust(98) + "\033[1;96m│\033[0m")
    print("\033[1;96m│\033[0m" + "   4. Read EVALLab insights and recommendations in the results file".ljust(98) + "\033[1;96m│\033[0m")
    print("\033[1;96m│\033[0m" + "   5. Check outputs/agent_execution.log for detailed agent activity".ljust(98) + "\033[1;96m│\033[0m")
    print("\033[1;96m│\033[0m" + " ".ljust(98) + "\033[1;96m│\033[0m")
    print("\033[1;96m└" + "─" * 98 + "┘\033[0m")

    print("\n" + "=" * 100)
    print("\033[1;92m▶ Starting Pre-Flight Checks...\033[0m")
    print("=" * 100 + "\n")

    # Resolve paper path
    workspace_root = Path(__file__).parent
    paper_dir = workspace_root / "papers"
    paper_source_dir = workspace_root / paper_dir / "codebases"

    paper_path = None
    if args.paper:
        # User specified a paper
        paper_path = Path(args.paper)

        if not paper_path.exists():
            print(f"❌ Paper not found: {args.paper}")
            return 1
        
        if not paper_path.suffix == '.pdf':
            print(f"❌ Not a PDF file: {args.paper}")
            return 1
    else:
        # Auto-detect: Look for any PDF in papers/ directory
        if paper_dir.exists():
            pdf_files = list(paper_dir.glob("*.pdf"))

            if pdf_files:
                # Sort alphabetically for consistent behavior
                pdf_files.sort()

                paper_path = pdf_files[0]
                print(f"✓ Auto-detected paper: {paper_path.name}")

                if len(pdf_files) > 1:
                    print(f"  ℹ️  Found {len(pdf_files)} PDFs, using first alphabetically")
                    print(f"  ℹ️  Use --paper <filename> to specify a different paper")

                    paper_path = pdf_files[0]
                    print(f"✓ Auto-detected paper: {paper_path.name}")

                else:
                    print(f"❌ No PDF files found in ./papers/")
                    print("   Please add your research paper PDF to ./papers/")

                    return 1
                
            else:
                print(f"❌ ./papers/ directory not found!")
                print("   Please create it and add your research paper PDF")

                return 1

    print(f"\n📄 Paper: {paper_path.name}")

    # Resolve codebase source
    codebase_source = None

    if args.code:
        codebase_source = args.code

        if args.code.startswith('http'):
            print(f"📦 Code source: {args.code} (GitHub)")

        else:
            code_path = Path(args.code)

            if not code_path.exists():
                print(f"❌ Code path not found: {args.code}")

                return 1
            
            print(f"📦 Code source: {args.code} (local)")

    else:
        print(
            f"📦 Code source: auto-detect (papers/codebases/ or GitHub URLs from papers)")

    print("\n📍 Checking workspace structure...")

    if not paper_dir.exists():
        print(f"❌ ./papers/ directory not found!")
        print("   Please create it and add your research paper PDF")

        return 1

    # Check for any code in papers/codebases directory
    if not paper_source_dir.exists():
        print(f"⚠️  ./papers/codebases/ directory not found!")
        print("   📁 The agent will search for GitHub URLs in the paper.")
        print("   💡 Or create ./papers/codebases/ and place codebase there manually.")

    else:
        # Check if there are any subdirectories or Python files
        has_code = any(paper_source_dir.iterdir())

        if has_code:
            subdirs = [d.name for d in paper_source_dir.iterdir()
                       if d.is_dir()]
            
            if subdirs:
                print(f"✓ Found code directory: {paper_source_dir}")
                print(f"   Subdirectories: {', '.join(subdirs[:3])}{' ...' if len(subdirs) > 3 else ''}")

            else:
                print(f"✓ Found files in: {paper_source_dir}")

        else:
            print(f"⚠️  ./papers/codebases/ exists but is empty!")
            print("   📁 The agent will search for GitHub URLs in the paper.")
            print("   💡 Or place your codebase in ./papers/codebases/ manually.")

    # Check Ollama
    print("\n🔍 Checking Ollama...")
    # Create a temporary agent just to check Ollama
    temp_agent = ReproductionAgent()

    if not temp_agent.is_available():
        print("❌ Ollama is not running!")
        print("\n   Please start Ollama in another terminal:")
        print("   $ ollama serve")
        print("\n   And ensure you have a model installed:")
        print("   $ ollama pull llama3")

        return 1

    models = temp_agent.list_models()
    if not models:
        print("❌ No Ollama models found!")
        print("\n   Please pull a model:")
        print("   $ ollama pull llama3")

        return 1

    print(f"✓ Ollama is running (models: {', '.join(models[:3])})")

    # Set up output directory for this paper
    paper_name_for_log = paper_path.stem if paper_path else None

    if paper_name_for_log:
        paper_stem = paper_name_for_log.lower().replace(' ', '_')
        output_dir = Path('outputs/visualizations') / paper_stem

        output_dir.mkdir(parents=True, exist_ok=True)

    else:
        output_dir = Path('outputs/visualizations/unknown_paper')

        output_dir.mkdir(parents=True, exist_ok=True)

    setup_logging(output_dir)

    # Run agent
    print("\n" + "=" * 100)
    print("\033[1;92m🚀 LAUNCHING 4-STAGE REPRODUCTION WORKFLOW...\033[0m")
    print("=" * 100 + "\n")

    try:
        agent = ReproductionAgent()

        # Start runtime and memory tracking
        results = agent.run(paper_path=paper_path, codebase_source=codebase_source)

        # Stop runtime and memory tracking
        end_time = time.time()
        runtime_seconds = end_time - start_time
        
        current, peak = tracemalloc.get_traced_memory()

        tracemalloc.stop()
        peak_mb = peak / (1024 * 1024)


        # Save runtime and memory info for HTML report AFTER visualizations are generated
        resource_path = output_dir / 'resource_usage.json'

        with open(resource_path, 'w') as f:
            json.dump({'runtime_seconds': runtime_seconds, 'peak_memory_mb': peak_mb}, f)

        # Regenerate the per-paper HTML so it picks up the new resource_usage.json
        # Harden this block so minor dashboard issues don't flip success to failure.
        try:
            from src.result_evaluator import ResultEvaluator
            result_evaluator = ResultEvaluator()

            # Find the files generated in the output_dir
            import pandas as pd

            # Try to load the detailed_comparison.csv for the DataFrame
            detailed_csv = output_dir / 'detailed_comparison.csv'

            if detailed_csv.exists():
                df = pd.read_csv(detailed_csv)

                # Try to infer the paper name from the directory
                paper_name = output_dir.name

                # Map expected keys to files
                file_map = {
                    'overall_performance': output_dir / 'overall_performance.png',
                    'performance_by_configuration': output_dir / 'performance_by_configuration.png',
                    'baseline_vs_reproduced': output_dir / 'baseline_vs_reproduced.png',
                    'deviation_distribution': output_dir / 'deviation_distribution.png',
                    'heatmap_granularity_tasktype': output_dir / 'heatmap_granularity_tasktype.png',
                    'summary_statistics': output_dir / 'summary_statistics.png',
                    'detailed_csv': output_dir / 'detailed_comparison.csv',
                    'per_example_diffs': output_dir / 'per_example_diffs.html',
                    'per_example_metrics': output_dir / 'per_example_metrics.html',
                    'visualizations_html': output_dir / 'visualizations.html',
                    'resource_usage': output_dir / 'resource_usage.json',
                    'agent_log': output_dir / 'agent_execution.log',
                    'results_txt': next((f for f in output_dir.glob('*_results.txt')), None),
                }

                # Remove any missing files
                files = {k: v for k, v in file_map.items() if v and v.exists()}

                # Regenerate the per-paper HTML using the helper.dashboard function
                from src.helper.dashboard import generate_visualization_index_html

                html_content = generate_visualization_index_html(files, df, paper_name, output_dir)
                html_path = output_dir / 'visualizations.html'

                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

            # Regenerate the top-level dashboard as well
            result_evaluator.generate_visualizations_index(output_dir.parent)

        except Exception as regen_exc:
            print(f"⚠️  Warning: Post-run HTML regeneration failed: {regen_exc}")
            # Do not return failure here; main pipeline already completed successfully.

        if 'error' in results:
            print(f"\n❌ Error: {results['error']}")

            return 1

        # Final Success Banner
        print("\n" + "=" * 100)
        print("\033[1;92m" + "█" * 100 + "\033[0m")
        print("\033[1;92m█" + " " * 98 + "█\033[0m")
        print("\033[1;92m█" + "✅ REPRODUCTION WORKFLOW COMPLETED SUCCESSFULLY!".center(98) + "█\033[0m")
        print("\033[1;92m█" + " " * 98 + "█\033[0m")
        print("\033[1;92m" + "█" * 100 + "\033[0m")
        print("=" * 100)

        print("\n\033[1;96m📊 Results Summary:\033[0m")
        print(f"  • All outputs saved to: \033[1;93m{output_dir}/\033[0m")
        print(f"  • \033[1;97mRaw EVALLab agent log:\033[0m \033[1;93m{output_dir}/agent_execution.log\033[0m")
        print(f"  • Visualizations: \033[1;93m{output_dir}/visualizations.html\033[0m")
        print(f"  • CSV data: \033[1;93m{output_dir}/detailed_comparison.csv\033[0m\n")
        print(f"  • Total runtime: {runtime_seconds:.2f} seconds")
        print(f"  • Peak memory usage: {peak_mb:.2f} MB")

        print(f"\n\033[1;92m✨ Open the HTML dashboard ({output_dir}/visualizations.html) in your browser to explore results!\033[0m\n")

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")

        return 1
    
    except Exception as e:
        print(f"\n❌ Error: {e}") 
        traceback.print_exc()
        
        return 1

# run the main method if called directly by name
if __name__ == '__main__':
    sys.exit(main())