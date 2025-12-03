set -e

# Determine script and repo root directories
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

# Check if papers/codebases/decontextualization directory exists
if [ ! -d "papers/codebases/decontextualization" ]; then

  # Check if user is linux or mac and has the curl command, download supplementary material
  if [[ "$OSTYPE" == "linux-gnu"* || "$OSTYPE" == "darwin"* ]]; then

    # Check if user has the curl command
    if command -v curl &> /dev/null; then
      echo "Downloading Decontextualization codebase..."

      # Make the codebases dir if it doesn't exist yet
      mkdir -p papers/codebases/

      # Download the zipped codebase to the codebases dir
      curl -L -o papers/codebases/supplementary_material.zip "https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material"

      # Unzip the codebase
      unzip papers/codebases/supplementary_material.zip -d papers/codebases/

      # Remove the zip file
      rm papers/codebases/supplementary_material.zip

      # Remove __MACOSX directory if it exists
      if [ -d "papers/codebases/__MACOSX" ]; then
        rm -rf papers/codebases/__MACOSX
      fi

      # Rename supplementary_material to decontextualization if it exists
      if [ -d "papers/codebases/supplementary_material" ]; then
        mv papers/codebases/supplementary_material papers/codebases/decontextualization
      fi

      echo "Decontextualization codebase downloaded and extracted to papers/codebases/decontextualization."
    else
      echo "Please install curl to download the Decontextualization codebase automatically."
      echo "Alternatively, manually download the codebase from https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material and place it in papers/codebases/decontextualization"
      exit 1
    fi
  else
    echo "Please manually download the Decontextualization codebase from https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material and place it in papers/codebases/decontextualization"
    exit 1
  fi
else
  echo "Decontextualization codebase found."
fi

# Generate config file using LLM if it doesn't exist
if [ ! -f "configs/repos/decontextualization.yaml" ]; then
  echo "Generating config file for decontextualization codebase..."
  python3 -c "
import sys
sys.path.insert(0, '.')
from pathlib import Path
from src.helper.repo_config import llm_generate_repo_config, save_repo_config
from src.pipeline import ReproductionAgent

# Initialize agent with default config
agent = ReproductionAgent()

# Generate config with proper naming
codebase_path = Path('papers/codebases/decontextualization/code')
config = llm_generate_repo_config(
    llm_client=agent,
    codebase_path=codebase_path
)

if config:
    # Override name to match paper/repo instead of subdirectory
    config.name = 'decontextualization'
    config.path_pattern = 'code'
    # Ensure experiment script and outputs align with paper expectations
    try:
        # Force main script path to root-level main_local_all_new.py
        for exp in config.experiments:
            if 'path' in exp:
                exp['path'] = 'main_local_all_new.py'
        # Set outputs to authors' full baseline paths
        if not config.outputs:
            config.outputs = {}
        config.outputs['results_file'] = 'outputs_all_methods_full/complete_results.json'
        config.outputs['report_file'] = 'outputs_all_methods_full/report.md'

        # Ensure baseline matches code.yaml behavior
        if not config.baseline:
          config.baseline = {}
        # Do not save baseline during run; compare against authors' results
        config.baseline['save_baseline'] = False
        # Use the same baseline file name as in code.yaml
        config.baseline['baseline_file'] = 'complete_results.json'
        
        # Ensure metric extractors use normalized names (lowercase with underscores)
        if config.metrics and 'extractors' in config.metrics:
            for extractor in config.metrics['extractors']:
                # Normalize extractor names: lowercase, @ -> _at_
                if 'name' in extractor:
                    extractor['name'] = extractor['name'].lower().replace('@', '_at_')
    except Exception as e:
        print(f'Warning: could not adjust experiment path/outputs: {e}')
    
    # Save config (output_path=None uses default location)
    save_repo_config(config, output_path=None)
    print('✓ Config file created at configs/repos/decontextualization.yaml')
else:
    print('✗ Failed to generate config file')
    sys.exit(1)
"
fi