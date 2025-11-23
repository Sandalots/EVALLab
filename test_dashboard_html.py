from pathlib import Path
import pandas as pd
from src.helper.dashboard import generate_visualization_index_html

def test_dashboard_html():
    # Dummy files dict and DataFrame
    files = {}
    df = pd.DataFrame()
    paper_name = "Test Paper"
    output_dir = Path("outputs/visualizations/test_paper")
    html = generate_visualization_index_html(files, df, paper_name, output_dir)
    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html
    print("HTML generation test passed.")

if __name__ == "__main__":
    test_dashboard_html()
