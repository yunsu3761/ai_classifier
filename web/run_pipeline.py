"""
End-to-end pipeline script:
1. Load YAML config from specified path
2. Parse yaml Excel for dimension definitions  
3. Parse patent Excel -> internal.txt
4. Generate initial_taxo files
5. Run classification

Usage:
    python web/run_pipeline.py
"""
import sys
import os
import io
import json
import shutil
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import yaml

# --- Configuration ---
YAML_EXCEL = r"C:\Users\POSCORTECH\Desktop\ys\taxoadapt\260223_web구동_input\260223_경제적 저탄소_고유인PM_yaml.xlsx"
PATENT_EXCEL = r"C:\Users\POSCORTECH\Desktop\ys\taxoadapt\260223_web구동_input\260223_경제적 저탄소_고유인PM_특허리스트.xlsx"
YAML_CONFIG = r"D:\TAXOADAPT\user_data\yuingo_2019\configs\generated_config.yaml"

DATASET_FOLDER = "web_custom_data"
DATA_DIR = PROJECT_ROOT / "datasets" / DATASET_FOLDER
TOPIC = "Low_Carbon_Ironmaking"

# --- Step 0: Setup ---
print("=" * 60)
print("TaxoAdapt E2E Pipeline")
print("=" * 60)

DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Step 1: Load YAML config ---
print("\n[Step 1] Loading YAML config...")
with open(YAML_CONFIG, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

dimensions = config.get("dimensions", {})
dim_names = list(dimensions.keys())
print(f"  -> {len(dim_names)} dimensions found:")
for d in dim_names:
    print(f"    - {d}")

# Copy YAML to dataset folder
yaml_copy = DATA_DIR / "generated_config.yaml"
shutil.copy2(YAML_CONFIG, yaml_copy)
print(f"  -> Config copied to: {yaml_copy}")

# --- Step 2: Check YAML Excel ---
print("\n[Step 2] Checking YAML Excel...")
try:
    df_yaml = pd.read_excel(YAML_EXCEL)
    print(f"  -> Columns: {list(df_yaml.columns)}")
    print(f"  -> Rows: {len(df_yaml)}")
except Exception as e:
    print(f"  -> Note: yaml Excel read issue (non-critical): {e}")
    df_yaml = None

# --- Step 3: Parse Patent Excel -> internal.txt ---
print("\n[Step 3] Parsing patent Excel...")
print(f"  -> Reading: {PATENT_EXCEL}")

# Check if internal.txt already exists from previous run
internal_path = DATA_DIR / "internal.txt"
if internal_path.exists():
    line_count = sum(1 for _ in open(internal_path, "r", encoding="utf-8") if _.strip())
    print(f"  -> internal.txt already exists with {line_count} documents")
    print(f"  -> Skipping Excel parsing (delete internal.txt to re-parse)")
    total_docs = line_count
else:
    try:
        df_cols = pd.read_excel(PATENT_EXCEL, nrows=0)
        columns = [str(c).strip() for c in df_cols.columns]
        print(f"  -> {len(columns)} columns detected")
        
        from web.backend.services.excel_parser import auto_detect_columns
        
        # Read full data
        print("  -> Reading full dataset (71MB, please wait)...")
        df_patent = pd.read_excel(PATENT_EXCEL)
        df_patent.columns = [str(c).strip() for c in df_patent.columns]
        print(f"  -> Loaded {len(df_patent)} rows")
        
        mapping = auto_detect_columns(df_patent)
        print(f"  -> Auto-detected: title={mapping.title_col}, abstract={mapping.abstract_col}, id={mapping.patent_id_col}")
        
        from web.backend.services.text_composer import convert_patent_excel_to_txt
        result = convert_patent_excel_to_txt(df_patent, mapping, DATA_DIR)
        print(f"  -> {result['message']}")
        total_docs = result['count']
        
    except Exception as e:
        import traceback
        print(f"  -> ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

# Show sample
with open(internal_path, 'r', encoding='utf-8') as f:
    first_line = f.readline()
sample = json.loads(first_line)
print(f"  -> Sample: {sample['Patent_ID']} | {sample['Title'][:60]}...")

# --- Step 4: Generate initial_taxo files ---
print("\n[Step 4] Generating initial_taxo files...")

for dim_name, dim_config in dimensions.items():
    taxo_file = DATA_DIR / f"initial_taxo_{dim_name}.txt"
    content = f"{dim_name}\n\t{dim_config.get('definition', dim_name)[:200]}\n"
    with open(taxo_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  -> Created: initial_taxo_{dim_name}.txt")

# --- Step 5: Check dimension name compatibility ---
print("\n[Step 5] Checking dimension name compatibility...")

from prompts import dimension_definitions as existing_defs

# Build a mapping for dimension name mismatches 
# YAML has: Blast_Furnace_Stabilization_and_High_Efficiency_Operation_Technologies
# prompts.py has: Blast_Furnace_Stabilization_and_High-Efficiency_Operation_Technologies
dim_name_map = {}  # yaml_name -> prompts_name
dim_defs = {}

for dim in dim_names:
    if dim in existing_defs:
        dim_name_map[dim] = dim
        dim_defs[dim] = existing_defs[dim]
    else:
        # Try fuzzy match (replace hyphens/underscores)
        normalized = dim.replace("-", "_").replace("__", "_")
        found = False
        for existing_key in existing_defs:
            if existing_key.replace("-", "_").replace("__", "_") == normalized:
                dim_name_map[dim] = existing_key
                dim_defs[dim] = existing_defs[existing_key]
                print(f"  -> Mapped: {dim} -> {existing_key} (prompts.py)")
                found = True
                break
        if not found:
            # Use the definition from YAML config directly
            dim_defs[dim] = dimensions[dim].get('definition', dim)
            dim_name_map[dim] = dim
            print(f"  -> Using YAML definition for: {dim}")

print(f"  -> All {len(dim_defs)} dimensions resolved")

# --- Step 6: Prepare classification ---
print("\n[Step 6] Preparing classification...")

try:
    from main2 import construct_dataset
    from model_definitions import initializeLLM, load_all_api_keys
    import argparse
    
    args = argparse.Namespace(
        llm='gpt',
        topic=TOPIC,
        dataset=DATASET_FOLDER,
        data_dir=str(DATA_DIR),
        max_depth=2,
        max_density=40,
        init_levels=1,
        test_samples=5,  # Test with 5 documents first
        dimensions=dim_names,
        resume=False,
        client={},
    )
    
    api_keys = load_all_api_keys()
    print(f"  -> API keys available: {len(api_keys)}")
    
    if not api_keys:
        print("  ERROR: No API keys found! Set OPENAI_API_KEY in .env")
        sys.exit(1)
    
    # Initialize LLM
    print("  -> Initializing LLM...")
    args = initializeLLM(args)
    model_name = os.environ.get('OPENAI_MODEL', 'unknown')
    print(f"  -> Model: {model_name}")
    
    # Load dataset
    print("\n[Step 7] Loading dataset...")
    internal_collection, total_count = construct_dataset(args)
    print(f"  -> Loaded {total_count} documents for classification")
    
    if total_count == 0:
        print("  ERROR: No documents loaded!")
        sys.exit(1)

    # Type classification
    print("\n[Step 8] Running type classification...")
    from prompts import generate_type_cls_system_instruction, type_cls_main_prompt
    from model_definitions import constructPrompt, promptLLM
    from utils import clean_json_string
    
    type_cls_instruction = generate_type_cls_system_instruction(dim_defs, TOPIC)
    
    paper_list = list(internal_collection.values())
    print(f"  -> Classifying {len(paper_list)} papers...")
    
    type_prompts = []
    for paper in paper_list:
        prompt = constructPrompt(
            args,
            type_cls_instruction,
            type_cls_main_prompt(paper, dim_defs, TOPIC),
        )
        type_prompts.append(prompt)
    
    print(f"  -> Sending {len(type_prompts)} prompts to LLM...")
    type_outputs = promptLLM(args, type_prompts, max_new_tokens=3000)
    
    # Parse results
    classification_results = []
    for i, (paper, output) in enumerate(zip(paper_list, type_outputs)):
        try:
            cleaned = clean_json_string(output) if "```" in output else output.strip()
            result = json.loads(cleaned)
            matched_dims = []
            for dim in dim_names:
                val = result.get(dim, result.get(dim.lower(), False))
                if val is True or str(val).lower() == 'true':
                    matched_dims.append(dim)
            classification_results.append({
                "paper_id": paper.id,
                "title": paper.title[:80],
                "dimensions": matched_dims,
            })
            dims_str = ", ".join(matched_dims) if matched_dims else "(none)"
            print(f"  Paper {i+1}: {paper.title[:50]}... -> {dims_str}")
        except Exception as e:
            print(f"  Paper {i+1}: Parse error: {e}")
            print(f"    Raw: {str(output)[:200]}")
    
    # Save results
    results_path = DATA_DIR / "type_classification_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(classification_results, f, ensure_ascii=False, indent=2)
    print(f"\n  -> Results saved to: {results_path}")
    
    print("\n" + "=" * 60)
    print("Pipeline completed successfully!")
    print(f"  Documents classified: {len(classification_results)}")
    print(f"  Results: {results_path}")
    print("=" * 60)

except Exception as e:
    import traceback
    print(f"\n[Error] {e}")
    traceback.print_exc()
