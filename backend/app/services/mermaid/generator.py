
from typing import List
from backend.app.services.inference import Diagram, Node, Edge
from loguru import logger
import re

class MermaidGenerator:
    @staticmethod
    def _sanitize_id(id_str: str) -> str:
        """Sanitizes node IDs to be Mermaid-safe (alphanumeric)."""
        return re.sub(r'[^a-zA-Z0-9]', '_', id_str)

    @staticmethod
    def _sanitize_label(label: str) -> str:
        """Sanitizes labels for Mermaid compatibility."""
        if not label: 
            return ""
        # Replace brackets/braces that conflict with node shape syntax
        label = label.replace('[', '(').replace(']', ')')
        label = label.replace('{', '(').replace('}', ')')
        # Replace quotes to avoid string literal breaks
        label = label.replace('"', "'")
        # Replace newlines with HTML break tags for Mermaid
        label = label.replace('\n', '<br/>').replace('\r', '')
        # Replace special chars that might confuse HTML/XML parsers
        label = label.replace('&', 'and')
        return label

    @staticmethod
    def _get_node_shape(id_clean: str, label: str, shape: str) -> str:
        """Determines Mermaid shape syntax."""
        label = MermaidGenerator._sanitize_label(label)
        if shape == "diamond" or shape == "decision":
            return f'{id_clean}{{"{label}"}}' # Diamond logic requires {}
        elif shape == "circle":
            return f'{id_clean}(("{label}"))'
        elif shape == "cylinder": # Database
            return f'{id_clean}[("{label}")]'
        elif shape == "parallelogram": # Input/Output
            return f'{id_clean}[/"{label}"/]'
        else: # Default rectangle
            return f'{id_clean}["{label}"]'

    @staticmethod
    def generate_code(diagram: Diagram) -> str:
        """
        Converts a canonical Diagram object into Mermaid code.
        """
        lines = ["flowchart TD"]

        # 1. Add Nodes
        for node in diagram.nodes:
            id_clean = MermaidGenerator._sanitize_id(node.id)
            lines.append(f"    {MermaidGenerator._get_node_shape(id_clean, node.label, node.shape)}")

        # 2. Add Edges
        for edge in diagram.edges:
            src = MermaidGenerator._sanitize_id(edge.source)
            tgt = MermaidGenerator._sanitize_id(edge.target)
            
            arrow = "-->"
            if edge.type == "dotted":
                arrow = "-.->"
            elif edge.type == "thick":
                arrow = "==>"
            
            if edge.label:
                label_clean = MermaidGenerator._sanitize_label(edge.label)
                lines.append(f"    {src} {arrow}|{label_clean}| {tgt}")
            else:
                lines.append(f"    {src} {arrow} {tgt}")

        return "\n".join(lines)
