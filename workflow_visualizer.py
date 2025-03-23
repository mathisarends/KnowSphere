# File: visualize_graph.py
import asyncio
from agents.graph_processor import DraftLangGraph

async def visualize_graph():
    """
    Visualisiert den LangGraph als Mermaid-Diagramm oder PNG.
    """
    # LangGraph-Prozessor initialisieren
    processor = DraftLangGraph(model_name="gpt-4o-mini")
    
    processor.compiled_graph.get_graph().print_ascii()

if __name__ == "__main__":
    asyncio.run(visualize_graph())