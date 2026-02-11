
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from loguru import logger
from backend.app.core.errors import GraphBuildFailure

# --- Canonical Schema ---
class Node(BaseModel):
    id: str
    label: str
    shape: str = "rectangle" # rectangle, diamond, circle, cylinder, etc.
    bbox: Optional[List[int]] = None # [x, y, w, h]

class Edge(BaseModel):
    source: str # using from/to as reserved words might catch us, so source/target
    target: str
    label: Optional[str] = None
    type: str = "arrow" # arrow, line, dotted

class Diagram(BaseModel):
    type: str = "flowchart"
    nodes: List[Node]
    edges: List[Edge]

# --- Inference Engine ---

class InferenceEngine:
    def __init__(self):
        pass

    def build_graph(self, vision_data: Dict[str, Any], ocr_data: List[Dict[str, Any]]) -> Diagram:
        """
        Combines Vision Output and OCR Data to build a canonical graph.
        Ensures topological validity (unique IDs, valid edges).
        """
        try:
            logger.info("Building graph from vision data...")
            
            id_map = {} # Maps original_id -> normalized_id
            nodes = []
            
            # 1. Process Nodes
            raw_nodes = vision_data.get("nodes", [])
            for i, n_data in enumerate(raw_nodes):
                original_id = str(n_data.get("id", f"gen_{i}"))
                
                # Deduplicate based on ID
                if original_id in id_map:
                    continue
                    
                # Generate safe, unique internal ID
                new_id = f"node_{i}"
                id_map[original_id] = new_id
                
                # Sanitize label (basic cleanup before Mermaid generator handles the rest)
                label = str(n_data.get("label", "Node"))
                
                nodes.append(Node(
                    id=new_id,
                    label=label,
                    shape=n_data.get("shape", "rectangle"),
                    bbox=n_data.get("bbox")
                ))

            # 2. Process Edges
            edges = []
            raw_edges = vision_data.get("edges", [])
            seen_edges = set()

            for e_data in raw_edges:
                src_orig = str(e_data.get("from"))
                tgt_orig = str(e_data.get("to"))
                
                # Resolve to new IDs
                src_new = id_map.get(src_orig)
                tgt_new = id_map.get(tgt_orig)
                
                # VALIDATION: Drop edges where nodes don't exist
                if not src_new or not tgt_new:
                    logger.warning(f"Skipping edge {src_orig} -> {tgt_orig}: node not found.")
                    continue
                
                # Prevent self-loops if they aren't meaningful (Mermaid handles them, but safer to check)
                # if src_new == tgt_new: continue 

                # Deduplicate edges
                edge_key = (src_new, tgt_new)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)

                edges.append(Edge(
                    source=src_new,
                    target=tgt_new,
                    label=e_data.get("label"),
                    type=e_data.get("type", "arrow")
                ))
            
            logger.info(f"Graph built with {len(nodes)} nodes and {len(edges)} edges.")
            
            return Diagram(
                type=vision_data.get("diagram_type", "flowchart"),
                nodes=nodes,
                edges=edges
            )

        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise GraphBuildFailure(str(e))
