import uuid
import yaml
from typing import List, Dict
from core.models import Idea
from core.content_dna import load_content_dna

class DraftGenerator:
    def generate(self, idea: Idea, structure_name: str, count: int = 1) -> List[str]:
        raise NotImplementedError

class TemplateDraftGenerator(DraftGenerator):
    """
    A deterministic template-based generation engine for Phase 3.
    This does NOT use an external LLM, and explicitly serves as a replaceable component.
    """
    def __init__(self, structures_filepath: str = "config/editorial_structures.yaml"):
        self.dna = load_content_dna()
        with open(structures_filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            self.structures = data.get("structures", {})

    def generate(self, idea: Idea, structure_name: str, count: int = 1) -> List[str]:
        structure = self.structures.get(structure_name)
        if not structure:
            return [f"Failed to generate: Structure '{structure_name}' not found."]
            
        variants = []
        for i in range(count):
            # Deterministic variation by slightly altering the template presentation
            lines = []
            
            # Simple pseudo-generation logic merging the raw idea with the structure steps
            lines.append(f"Idea: {idea.raw_text.strip()}")
            lines.append("")
            
            for step in structure["steps"]:
                if i == 0:
                    lines.append(f"- {step}")
                elif i == 1:
                    lines.append(f"> {step}")
                else:
                    lines.append(f"[{step}]")
                    
            if i % 2 == 1 and self.dna.preferred_vocabulary:
                lines.append(f"\n({self.dna.preferred_vocabulary[0]})")
                
            variants.append("\n".join(lines)[:265]) # basic chop just for safety, character limits will block it otherwise
            
        return variants
