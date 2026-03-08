"""
Configuration Manager for TaxoAdapt
Manages dimension definitions and generates corresponding prompts and schemas
"""
import json
import yaml
from typing import Dict, List
from pathlib import Path


class DimensionConfig:
    """Handles dimension configuration and prompt generation"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize with a config file or use defaults
        
        Args:
            config_path: Path to YAML config file
        """
        self.config_path = config_path
        self.dimensions = {}
        
        if config_path and Path(config_path).exists():
            self.load_config(config_path)
        else:
            self._load_default_nlp_config()
    
    def _load_default_nlp_config(self):
        """Load default NLP dimension configuration"""
        self.dimensions = {
            'tasks': {
                'definition': 'Task: we assume that all papers are associated with a specific task(s). Always output "Task" as one of the paper types unless you are absolutely sure the paper does not address any task.',
                'node_definition': 'Defines and categorizes research efforts aimed at solving specific problems or objectives within a given field, such as classification, prediction, or optimization.'
            },
            'methodologies': {
                'definition': 'Methodology: a paper that introduces, explains, or refines a method or approach, providing theoretical foundations, implementation details, and empirical evaluations to advance the state-of-the-art or solve specific problems.',
                'node_definition': 'Types of techniques, models, or approaches used to address various challenges, including algorithmic innovations, frameworks, and optimization strategies.'
            },
            'datasets': {
                'definition': 'Datasets: introduces a new dataset, detailing its creation, structure, and intended use, while providing analysis or benchmarks to demonstrate its relevance and utility. It focuses on advancing research by addressing gaps in existing datasets/performance of SOTA models or enabling new applications in the field.',
                'node_definition': 'Types of methods to structure data collections used in research, including ways to curate or analyze datasets, detailing their properties, intended use, and role in advancing the field.'
            },
            'evaluation_methods': {
                'definition': 'Evaluation Methods: a paper that assesses the performance, limitations, or biases of models, methods, or datasets using systematic experiments or analyses. It focuses on benchmarking, comparative studies, or proposing new evaluation metrics or frameworks to provide insights and improve understanding in the field.',
                'node_definition': 'Types of methods for assessing the performance of models, datasets, or techniques, including new metrics, benchmarking techniques, or comparative performance studies.'
            },
            'real_world_domains': {
                'definition': 'Real-World Domains: demonstrates the use of techniques to solve specific, real-world problems or address specific domain challenges. It focuses on practical implementation, impact, and insights gained from applying methods in various contexts. Examples include: product recommendation systems, medical record summarization, etc.',
                'node_definition': 'Types of practical or industry-specific domains in which techniques and methodologies can be applied, exploring implementation, impact, and challenges of real-world problems.'
            }
        }
    
    def load_config(self, config_path: str):
        """Load configuration from YAML file"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        self.dimensions = config.get('dimensions', {})
    
    def save_config(self, output_path: str):
        """Save current configuration to YAML file"""
        config = {'dimensions': self.dimensions}
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        print(f"Configuration saved to: {output_path}")
    
    def get_dimension_definitions(self) -> Dict[str, str]:
        """Get dimension_definitions dict for prompts.py"""
        return {
            dim: config['definition']
            for dim, config in self.dimensions.items()
        }
    
    def get_node_dimension_definitions(self) -> Dict[str, str]:
        """Get node_dimension_definitions dict for prompts.py"""
        return {
            dim: config['node_definition']
            for dim, config in self.dimensions.items()
        }
    
    def get_dimension_list(self) -> List[str]:
        """Get list of dimension names"""
        return list(self.dimensions.keys())
    
    def add_dimension(self, name: str, definition: str, node_definition: str):
        """Add a new dimension"""
        self.dimensions[name] = {
            'definition': definition,
            'node_definition': node_definition
        }
    
    def remove_dimension(self, name: str):
        """Remove a dimension"""
        if name in self.dimensions:
            del self.dimensions[name]
    
    def update_dimension(self, name: str, definition: str = None, node_definition: str = None):
        """Update an existing dimension"""
        if name not in self.dimensions:
            raise ValueError(f"Dimension '{name}' does not exist")
        
        if definition:
            self.dimensions[name]['definition'] = definition
        if node_definition:
            self.dimensions[name]['node_definition'] = node_definition
    
    def generate_type_cls_system_instruction(self) -> str:
        """Generate system instruction for type classification"""
        instruction = """You are a helpful multi-label classification assistant which helps me label papers based on their paper type. They may be more than one.

Paper types (type:definition):

"""
        for i, (dim, config) in enumerate(self.dimensions.items(), 1):
            instruction += f"{i}. {config['definition']}\n"
        
        return instruction.strip()
    
    def generate_type_cls_schema_code(self) -> str:
        """Generate Pydantic schema class code for TypeClsSchema"""
        code = "class TypeClsSchema(BaseModel):\n"
        for dim in self.dimensions.keys():
            code += f"  {dim}: bool\n"
        return code
    
    def generate_type_cls_main_prompt_json(self) -> str:
        """Generate JSON format string for type classification prompt"""
        json_format = "{\n"
        for dim in self.dimensions.keys():
            json_format += f'  "{dim}": <return True if the paper is relevant to {dim}, False otherwise>,\n'
        json_format = json_format.rstrip(',\n') + "\n}"
        return json_format
    
    def display_config(self):
        """Display current configuration"""
        print("\n" + "="*80)
        print("CURRENT DIMENSION CONFIGURATION")
        print("="*80)
        for dim, config in self.dimensions.items():
            print(f"\n📌 {dim.upper()}")
            print(f"   Definition: {config['definition'][:100]}...")
            print(f"   Node Definition: {config['node_definition'][:100]}...")
        print("\n" + "="*80)


def load_biology_preset() -> DimensionConfig:
    """Load biology domain preset configuration"""
    config = DimensionConfig(config_path=None)
    config.dimensions = {
        'experimental_methods': {
            'definition': 'Experimental Methods: a paper that introduces, explains, or significantly refines experimental techniques, protocols, laboratory methods, or biological assays, providing detailed descriptions and validations to improve accuracy, reproducibility, or insight in biological research.',
            'node_definition': 'Types of experimental techniques, protocols, laboratory procedures, or biological assays introduced or significantly refined, detailing their design, validation, and implementation to improve accuracy, reproducibility, or effectiveness in biological research.'
        },
        'datasets': {
            'definition': 'Datasets: a paper that introduces new biological datasets (e.g., genomic sequences, imaging data, ecological observations), detailing their generation, structure, annotation, and intended use, and provides initial analyses or benchmarks demonstrating their value in addressing gaps or enabling new biological insights.',
            'node_definition': 'Types of biological datasets introduced (e.g., genomic, proteomic, imaging, ecological data), describing their creation, structure, annotation, and intended use, accompanied by initial analyses or benchmarks demonstrating their utility in enabling novel insights or addressing research gaps.'
        },
        'theoretical_advances': {
            'definition': 'Theoretical Advances: a paper that proposes new biological theories, models, frameworks, or conceptual insights, supported by rigorous analysis, modeling, or experimental validation, aimed at improving fundamental understanding of biological systems.',
            'node_definition': 'Types of new biological theories, conceptual frameworks, or models proposed, supported by rigorous analytical, mathematical, or empirical validation, aimed at enhancing fundamental understanding of biological systems or phenomena.'
        },
        'applications': {
            'definition': 'Applications: a paper which demonstrates practical use of biological knowledge or techniques to address real-world problems in domains such as biomedicine (therapies, diagnostics, drug development), agriculture (crop improvement, pest control), or conservation (species protection, ecosystem management), focusing on practical impact and applied outcomes.',
            'node_definition': 'Types of practical applications of biological research or techniques in domains such as biomedicine (therapeutics, diagnostics), agriculture (crop improvement, pest management), or conservation biology (species protection, ecosystem management), emphasizing real-world impact, feasibility, and applied outcomes.'
        },
        'evaluation_methods': {
            'definition': 'Evaluation Methods: a paper which systematically evaluates biological techniques, datasets, or computational methods, using benchmarking, comparative analyses, or novel evaluation metrics, to provide deeper insights into their effectiveness, limitations, or biases, thereby enhancing understanding and guiding future research.',
            'node_definition': 'Types of systematic approaches for evaluating biological methods, datasets, or computational techniques through benchmarking, comparative analysis, or novel performance metrics, aimed at identifying strengths, weaknesses, biases, or effectiveness, thus informing and guiding future research directions.'
        }
    }
    return config


if __name__ == "__main__":
    # Example usage
    config = DimensionConfig()
    config.display_config()
    
    print("\n\nGenerated dimension_definitions:")
    print(json.dumps(config.get_dimension_definitions(), indent=2))
    
    print("\n\nGenerated Type Classification System Instruction:")
    print(config.generate_type_cls_system_instruction())
