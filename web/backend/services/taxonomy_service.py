"""
Taxonomy loading, generation, and management service.
Wraps existing config_manager.py and web_interface.py taxonomy generation logic.
"""
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Add project root to path so we can import existing modules
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config_manager import DimensionConfig


class TaxonomyService:
    """Service for taxonomy configuration and file generation."""

    def __init__(self):
        self._config: Optional[DimensionConfig] = None
        self._topic: str = ""

    @property
    def config(self) -> Optional[DimensionConfig]:
        return self._config

    @property
    def dimensions(self) -> Dict:
        if self._config:
            return self._config.dimensions
        return {}

    def load_yaml(self, yaml_content: str) -> Dict:
        """Load dimensions from YAML string content."""
        raw = yaml.safe_load(yaml_content)
        self._config = DimensionConfig(config_path=None)
        self._config.dimensions = raw.get("dimensions", {})
        return self._config.dimensions

    def load_yaml_file(self, filepath: Path) -> Dict:
        """Load dimensions from a YAML file."""
        self._config = DimensionConfig(config_path=str(filepath))
        return self._config.dimensions

    def set_topic(self, topic: str):
        self._topic = topic

    def get_dimensions_list(self) -> List[str]:
        return list(self.dimensions.keys())

    def update_dimension(self, name: str, definition: str, node_definition: str):
        if self._config is None:
            self._config = DimensionConfig(config_path=None)
            self._config.dimensions = {}
        self._config.dimensions[name] = {
            "definition": definition,
            "node_definition": node_definition,
        }

    def remove_dimension(self, name: str):
        if self._config and name in self._config.dimensions:
            del self._config.dimensions[name]

    def generate_yaml_from_excel(self, df: pd.DataFrame) -> str:
        """Generate YAML config from a Dimension Excel file.

        Expected columns: Level1_Dimension_Name, Level1_Dimension_Definitions,
                         Level1_Node_Dimension_Definitions
        """
        dimensions = {}
        for _, row in df.iterrows():
            name = str(row.get("Level1_Dimension_Name", "")).strip()
            definition = str(row.get("Level1_Dimension_Definitions", "")).strip()
            node_def = str(row.get("Level1_Node_Dimension_Definitions", "")).strip()
            if name and definition:
                # Sanitize name: replace spaces with underscores
                safe_name = name.replace(" ", "_")
                dimensions[safe_name] = {
                    "definition": definition,
                    "node_definition": node_def or definition,
                }

        yaml_data = {"dimensions": dimensions}
        return yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True)

    def generate_initial_taxo_files(
        self,
        df: pd.DataFrame,
        level_cols: List[str],
        output_dir: Path,
        topic: str = "technology",
    ) -> Dict[str, str]:
        """Generate initial_taxo_*.txt files from hierarchical Excel data.

        Returns {filename: content} dict.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files = {}

        # Group by Level1 (each Level1 becomes a dimension)
        if "Level1" not in df.columns:
            return {}

        level1_values = df["Level1"].dropna().unique()

        for dim_value in level1_values:
            dim_name = str(dim_value).strip().replace(" ", "_")
            dim_df = df[df["Level1"] == dim_value]

            # Build taxonomy text
            lines = []
            root_label = topic.replace(" ", "_").lower()
            lines.append(f"Label: {root_label}")
            lines.append(f"Dimension: {dim_name}")
            lines.append(f"Description: Root topic for {topic}")
            lines.append("---")

            # Add Level1 as first child
            dim_desc = ""
            desc_col = "Level1_Description" if "Level1_Description" in df.columns else None
            if desc_col:
                descs = dim_df[desc_col].dropna().unique()
                dim_desc = str(descs[0]) if len(descs) > 0 else ""

            lines.append(f"  Label: {dim_name.lower()}")
            lines.append(f"  Dimension: {dim_name}")
            lines.append(f"  Description: {dim_desc or dim_name}")
            lines.append("  ---")

            # Add Level2+ children
            if "Level2" in level_cols:
                l2_values = dim_df["Level2"].dropna().unique()
                for l2 in l2_values:
                    l2_name = str(l2).strip().replace(" ", "_").lower()
                    l2_desc = ""
                    if "Level2_Description" in df.columns:
                        l2_rows = dim_df[dim_df["Level2"] == l2]
                        l2_descs = l2_rows["Level2_Description"].dropna()
                        l2_desc = str(l2_descs.iloc[0]) if len(l2_descs) > 0 else ""

                    lines.append(f"    Label: {l2_name}")
                    lines.append(f"    Dimension: {dim_name}")
                    lines.append(f"    Description: {l2_desc or l2_name}")
                    lines.append("    ---")

                    # Level3
                    if "Level3" in level_cols:
                        l2_rows = dim_df[dim_df["Level2"] == l2]
                        l3_values = l2_rows["Level3"].dropna().unique()
                        for l3 in l3_values:
                            l3_name = str(l3).strip().replace(" ", "_").lower()
                            l3_desc = ""
                            if "Level3_Description" in df.columns:
                                l3_rows = l2_rows[l2_rows["Level3"] == l3]
                                l3_descs = l3_rows["Level3_Description"].dropna()
                                l3_desc = str(l3_descs.iloc[0]) if len(l3_descs) > 0 else ""

                            lines.append(f"      Label: {l3_name}")
                            lines.append(f"      Dimension: {dim_name}")
                            lines.append(f"      Description: {l3_desc or l3_name}")
                            lines.append("      ---")

            content = "\n".join(lines) + "\n"
            filename = f"initial_taxo_{dim_name}.txt"
            filepath = output_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            generated_files[filename] = content

        return generated_files

    def to_yaml_string(self) -> str:
        """Serialize current config to YAML string."""
        if not self._config:
            return ""
        return yaml.dump(
            {"dimensions": self._config.dimensions},
            default_flow_style=False,
            allow_unicode=True,
        )

    def save_yaml(self, output_path: Path):
        """Save current config to a YAML file."""
        if self._config:
            self._config.save_config(str(output_path))


# Global singleton
_taxonomy_service = TaxonomyService()


def get_taxonomy_service() -> TaxonomyService:
    return _taxonomy_service
