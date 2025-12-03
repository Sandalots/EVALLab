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

# Initialize LLM client
agent = ReproductionAgent(paper_path=Path('papers/decontextualisation.pdf'))

# Generate config with proper naming
codebase_path = Path('papers/codebases/decontextualization/code')
config = llm_generate_repo_config(codebase_path, agent)

if config:
    # Override name to match paper/repo instead of subdirectory
    config.name = 'decontextualization'
    config.path_pattern = 'decontextualization'
    save_repo_config(config, Path('configs/repos'))
    print('✓ Config file created at configs/repos/decontextualization.yaml')
else:
    print('✗ Failed to generate config file')
    sys.exit(1)
"
fi