#!/usr/bin/env python3
"""
Interactive Interface for TaxoAdapt
Allows users to configure dimensions and datasets, then run the taxonomy generation
"""
import os
import sys
import argparse
from pathlib import Path
from config_manager import DimensionConfig, load_biology_preset


def interactive_menu():
    """Interactive menu for dimension configuration"""
    print("\n" + "="*80)
    print("🔬 TAXOADAPT - Taxonomy Generation Framework")
    print("="*80)
    
    config = None
    
    while True:
        print("\n📋 MAIN MENU:")
        print("1. Start with NLP preset (default)")
        print("2. Start with Biology preset")
        print("3. Load from config file")
        print("4. Create custom configuration")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == '1':
            config = DimensionConfig()
            print("✅ NLP preset loaded")
            break
        elif choice == '2':
            config = load_biology_preset()
            print("✅ Biology preset loaded")
            break
        elif choice == '3':
            config_path = input("Enter config file path: ").strip()
            if os.path.exists(config_path):
                config = DimensionConfig(config_path=config_path)
                print(f"✅ Config loaded from {config_path}")
                break
            else:
                print("❌ File not found. Try again.")
        elif choice == '4':
            config = create_custom_config()
            break
        elif choice == '5':
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid option. Please try again.")
    
    # Display current config
    config.display_config()
    
    # Edit dimensions if needed
    while True:
        print("\n🔧 DIMENSION EDITING:")
        print("1. Add dimension")
        print("2. Remove dimension")
        print("3. Edit dimension")
        print("4. Continue to dataset selection")
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == '1':
            add_dimension_interactive(config)
        elif choice == '2':
            remove_dimension_interactive(config)
        elif choice == '3':
            edit_dimension_interactive(config)
        elif choice == '4':
            break
        else:
            print("Invalid option. Please try again.")
    
    # Dataset selection
    dataset_name = select_dataset()
    
    # Save configuration option
    save_opt = input("\n💾 Save this configuration for future use? (y/n): ").strip().lower()
    if save_opt == 'y':
        save_path = input("Enter save path (e.g., configs/my_config.yaml): ").strip()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        config.save_config(save_path)
    
    # Execution parameters
    print("\n⚙️  EXECUTION PARAMETERS:")
    topic = input("Enter topic (default: natural language processing): ").strip() or "natural language processing"
    max_depth = input("Enter max depth (default: 2): ").strip() or "2"
    init_levels = input("Enter init levels (default: 1): ").strip() or "1"
    max_density = input("Enter max density (default: 40): ").strip() or "40"
    llm = input("Enter LLM type (gpt/vllm, default: gpt): ").strip() or "gpt"
    
    # API key for GPT
    openai_api_key = None
    huggingface_token = None
    
    if llm == 'gpt':
        openai_api_key = input("Enter OpenAI API key (press Enter to use OPENAI_API_KEY env variable): ").strip() or None
    elif llm == 'vllm':
        huggingface_token = input("Enter HuggingFace token (press Enter to use HUGGINGFACE_TOKEN env variable): ").strip() or None
    
    return {
        'config': config,
        'dataset': dataset_name,
        'topic': topic,
        'max_depth': int(max_depth),
        'init_levels': int(init_levels),
        'max_density': int(max_density),
        'llm': llm,
        'openai_api_key': openai_api_key,
        'huggingface_token': huggingface_token
    }


def create_custom_config():
    """Create custom dimension configuration from scratch"""
    config = DimensionConfig(config_path=None)
    config.dimensions = {}
    
    print("\n📝 CREATE CUSTOM CONFIGURATION")
    print("Enter dimensions one by one. Type 'done' when finished.\n")
    
    while True:
        dim_name = input("Dimension name (or 'done'): ").strip()
        if dim_name.lower() == 'done':
            break
        
        definition = input(f"Definition for {dim_name}: ").strip()
        node_definition = input(f"Node definition for {dim_name}: ").strip()
        
        config.add_dimension(dim_name, definition, node_definition)
        print(f"✅ Added dimension: {dim_name}\n")
    
    return config


def add_dimension_interactive(config: DimensionConfig):
    """Interactive dimension addition"""
    dim_name = input("\nEnter dimension name: ").strip()
    definition = input("Enter definition: ").strip()
    node_definition = input("Enter node definition: ").strip()
    
    config.add_dimension(dim_name, definition, node_definition)
    print(f"✅ Added dimension: {dim_name}")
    config.display_config()


def remove_dimension_interactive(config: DimensionConfig):
    """Interactive dimension removal"""
    print("\nCurrent dimensions:", ', '.join(config.get_dimension_list()))
    dim_name = input("Enter dimension name to remove: ").strip()
    
    try:
        config.remove_dimension(dim_name)
        print(f"✅ Removed dimension: {dim_name}")
        config.display_config()
    except Exception as e:
        print(f"❌ Error: {e}")


def edit_dimension_interactive(config: DimensionConfig):
    """Interactive dimension editing"""
    print("\nCurrent dimensions:", ', '.join(config.get_dimension_list()))
    dim_name = input("Enter dimension name to edit: ").strip()
    
    if dim_name not in config.dimensions:
        print(f"❌ Dimension '{dim_name}' not found")
        return
    
    print(f"\nCurrent definition: {config.dimensions[dim_name]['definition']}")
    new_def = input("New definition (press Enter to keep current): ").strip()
    
    print(f"\nCurrent node definition: {config.dimensions[dim_name]['node_definition']}")
    new_node_def = input("New node definition (press Enter to keep current): ").strip()
    
    config.update_dimension(
        dim_name,
        definition=new_def if new_def else None,
        node_definition=new_node_def if new_node_def else None
    )
    print(f"✅ Updated dimension: {dim_name}")
    config.display_config()


def select_dataset():
    """Dataset selection menu"""
    print("\n📊 DATASET SELECTION:")
    datasets = [
        'emnlp_2024',
        'emnlp_2022',
        'cvpr_2024',
        'cvpr_2020',
        'iclr_2024',
        'iclr_2021',
        'icra_2024',
        'icra_2020'
    ]
    
    for i, ds in enumerate(datasets, 1):
        print(f"{i}. {ds}")
    print(f"{len(datasets) + 1}. Custom dataset name")
    
    choice = input(f"\nSelect dataset (1-{len(datasets) + 1}): ").strip()
    
    try:
        choice_idx = int(choice) - 1
        if 0 <= choice_idx < len(datasets):
            return datasets[choice_idx]
        elif choice_idx == len(datasets):
            return input("Enter custom dataset name: ").strip()
    except:
        pass
    
    print("Invalid choice, using default: emnlp_2024")
    return 'emnlp_2024'


def update_prompts_file(config: DimensionConfig):
    """Update prompts.py with new dimension definitions"""
    import importlib.util
    
    # Read current prompts.py
    prompts_path = Path(__file__).parent / 'prompts.py'
    with open(prompts_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Generate new definitions
    dim_defs = config.get_dimension_definitions()
    node_dim_defs = config.get_node_dimension_definitions()
    
    # Format dimension_definitions
    dim_def_str = "dimension_definitions = {\n"
    for dim, definition in dim_defs.items():
        dim_def_str += f"    '{dim}': \"\"\"{definition}\"\"\",\n"
    dim_def_str += "    }"
    
    # Format node_dimension_definitions
    node_dim_def_str = "node_dimension_definitions = {\n"
    for dim, definition in node_dim_defs.items():
        node_dim_def_str += f"    '{dim}': \"\"\"{definition}\"\"\",\n"
    node_dim_def_str += "}"
    
    # Find and replace dimension_definitions
    import re
    
    # Replace dimension_definitions (active one, not commented)
    pattern = r'dimension_definitions = \{[^}]*\}'
    content = re.sub(pattern, dim_def_str, content, count=1)
    
    # Replace node_dimension_definitions (active one)
    pattern = r'node_dimension_definitions = \{[^}]*\}'
    matches = list(re.finditer(pattern, content))
    if matches:
        # Replace the first uncommented one
        for match in matches:
            start = match.start()
            # Check if it's not commented (check preceding lines)
            lines_before = content[:start].split('\n')
            is_commented = False
            for line in reversed(lines_before[-10:]):  # Check last 10 lines
                if line.strip().startswith('#'):
                    is_commented = True
                elif line.strip():
                    break
            
            if not is_commented:
                content = content[:start] + node_dim_def_str + content[match.end():]
                break
    
    # Replace TypeClsSchema
    schema_code = config.generate_type_cls_schema_code()
    pattern = r'class TypeClsSchema\(BaseModel\):.*?(?=\n\n|\nclass |\n#)'
    content = re.sub(pattern, schema_code.rstrip(), content, flags=re.DOTALL, count=1)
    
    # Replace type_cls_system_instruction
    sys_instruction = config.generate_type_cls_system_instruction()
    pattern = r'type_cls_system_instruction = """[^"]*"""'
    content = re.sub(pattern, f'type_cls_system_instruction = """{sys_instruction}"""', content, count=1)
    
    # Write back
    with open(prompts_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ Updated {prompts_path}")


def run_taxoadapt(params):
    """Execute main.py with configured parameters"""
    from main import main
    import argparse
    
    # Update prompts.py first
    print("\n🔄 Updating prompts.py with new dimension configuration...")
    update_prompts_file(params['config'])
    
    # Prepare arguments
    args = argparse.Namespace()
    args.topic = params['topic']
    args.dataset = params['dataset']
    args.llm = params['llm']
    args.max_depth = params['max_depth']
    args.init_levels = params['init_levels']
    args.max_density = params['max_density']
    args.openai_api_key = params.get('openai_api_key', None)
    args.huggingface_token = params.get('huggingface_token', None)
    args.dimensions = params['config'].get_dimension_list()
    args.data_dir = f"datasets/{args.dataset.lower().replace(' ', '_')}"
    args.internal = f"{args.dataset}.txt"
    
    print("\n🚀 Starting TaxoAdapt with following configuration:")
    print(f"   Topic: {args.topic}")
    print(f"   Dataset: {args.dataset}")
    print(f"   Dimensions: {', '.join(args.dimensions)}")
    print(f"   Max Depth: {args.max_depth}")
    print(f"   Max Density: {args.max_density}")
    print(f"   LLM: {args.llm}")
    if args.openai_api_key:
        print(f"   OpenAI API Key: {'*' * 20} (provided)")
    if args.huggingface_token:
        print(f"   HuggingFace Token: {'*' * 20} (provided)")
    print("\n" + "="*80 + "\n")
    
    # Run main
    main(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='TaxoAdapt Interactive Interface')
    parser.add_argument('--batch', type=str, help='Path to batch config file for non-interactive mode')
    parser.add_argument('--config', type=str, help='Path to dimension config file')
    parser.add_argument('--dataset', type=str, help='Dataset name')
    parser.add_argument('--topic', type=str, help='Topic name')
    
    args = parser.parse_args()
    
    if args.batch:
        # Batch mode - load from config file
        print(f"Running in batch mode with config: {args.batch}")
        # TODO: Implement batch mode
    else:
        # Interactive mode
        params = interactive_menu()
        
        # Confirm before running
        confirm = input("\n▶️  Run TaxoAdapt now? (y/n): ").strip().lower()
        if confirm == 'y':
            run_taxoadapt(params)
        else:
            print("Cancelled. Configuration saved if requested.")
