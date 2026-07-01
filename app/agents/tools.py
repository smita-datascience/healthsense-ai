"""Retriever tool for HealthSense AI — keyword search over the knowledge base.

This is 'naive RAG': simple keyword matching over text sections. It proves the
retrieve -> ground loop. The upgrade path (embeddings + vector DB) swaps only
the search logic inside `search`, not the tool interface.
"""
from pathlib import Path

from crewai.tools import tool

# Load the knowledge base once, split into sections by their "# Heading".
_KB_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "health_facts.md"
_RAW = _KB_PATH.read_text(encoding="utf-8")
_SECTIONS = [s.strip() for s in _RAW.split("# ") if s.strip()]


@tool("search_health_knowledge")
def search_health_knowledge(query: str) -> str:
    """Search the health knowledge base for information relevant to the query.
    Returns the most relevant section(s) of vetted health facts.
    """
    q_words = set(query.lower().split())
    scored = []
    for section in _SECTIONS:
        words = set(section.lower().split())
        overlap = len(q_words & words)  # how many query words appear in section
        if overlap > 0:
            scored.append((overlap, section))
    if not scored:
        return "No relevant information found in the knowledge base."
    # Return the top 2 best-matching sections.
    scored.sort(reverse=True, key=lambda x: x[0])
    return "\n\n".join(f"# {sec}" for _, sec in scored[:2])