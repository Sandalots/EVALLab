"""===============================================================================
EVALLAB STAGE 1/4: PAPER PARSING

Extracts text, metadata, and GitHub URLs from research paper PDFs.
Outputs structured content for Stage 2 (Code Retrieval).
===============================================================================
"""

import re
from pathlib import Path
from typing import List, Optional
import PyPDF2
from dataclasses import dataclass


@dataclass
class PaperContent:
    """Structured representation of paper content."""
    title: Optional[str] = None
    abstract: Optional[str] = None
    methodology: Optional[str] = None
    experiments: Optional[str] = None
    results: Optional[str] = None
    github_urls: List[str] = None
    raw_text: str = ""

    def __post_init__(self):
        self.github_urls = self.github_urls or []


class PaperParser:
    """Parse research papers and extract key sections."""

    def __init__(self):
        # Pattern matches URLs possibly split across lines
        self.github_pattern = re.compile(
            r'https?://github\.com(?:/|\s+)[\w\-]+(?:/|\s+)[\w\-\.]+',
            re.IGNORECASE
        )

    def parse_pdf(self, pdf_path: Path) -> PaperContent:
        """
        Parse a PDF file and extract text content.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            PaperContent object with extracted information
        """
        content = PaperContent()

        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                # Extract all text
                content.raw_text = "\n".join(page.extract_text() for page in pdf_reader.pages)

                # Extract GitHub URLs
                content.github_urls = self._extract_github_urls(
                    content.raw_text)

        except Exception as e:
            raise ValueError(f"Error parsing PDF: {e}")

        return content

    def _extract_github_urls(self, text: str) -> List[str]:
        """Extract GitHub repository URLs from text, cleaning trailing reference symbols/punctuation and .N artifacts."""
        # Join lines to handle split URLs
        text_joined = re.sub(r'\s*\n\s*', '', text)
        urls = self.github_pattern.findall(text_joined)
        # Clean up URLs (remove any whitespace)
        urls = [re.sub(r'\s+', '', url) for url in urls]
        cleaned_urls = []
        for url in urls:
            # Remove trailing characters that are not valid in GitHub repo URLs
            # Remove trailing .N, .N., .N], .N), .N}, .N; etc. (where N is one or more digits)
            url = re.sub(r'(\.[0-9]+([\]\)\}}\.,;:!])*)+$', '', url)
            # Remove trailing punctuation
            url = re.sub(r'[\.,;:!\)\]\}]+$', '', url)
            # Remove trailing reference numbers in brackets (e.g., [1], [12])
            url = re.sub(r'\[[0-9]+\]$', '', url)
            cleaned_urls.append(url)
            
        # Remove duplicates while preserving order
        return list(dict.fromkeys(cleaned_urls))
