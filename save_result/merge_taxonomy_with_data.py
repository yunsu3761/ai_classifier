#!/usr/bin/env python
"""
Merge taxonomy classification results with original dataset
"""
import json
import pandas as pd
from pathlib import Path
from collections import defaultdict
import sys
import argparse
import os
import re
sys.path.insert(0, str(Path(__file__).parent))
from config_utils import get_dimensions, get_dimension_names_korean

def _load_converted_user_topic(main_dir: Path):
    """Find user_config.json and return normalized user_topic (spaces and '-' -> '_').
    Falls back to default topic if not found.
    """
    default = 'cost_effective_low_carbon_steelmaking_technologies'
    # try environment-based employee id
    env_keys = ['EMPLOYEE_ID', 'EMPLOYEE', 'USER', 'USERNAME']
    candidates = []
    for k in env_keys:
        emp = os.environ.get(k)
        if emp:
            p = main_dir / "user_data" / emp / "configs" / "user_config.json"
            if p.exists():
                candidates.append(p)
                break
    # if not found by env, pick first user_config.json under user_data
    if not candidates:
        candidates = list(main_dir.glob("user_data/*/configs/user_config.json"))
    if not candidates:
        return default
    cfg_path = candidates[0]
    try:
        with open(cfg_path, 'r', encoding='utf-8') as fh:
            cfg = json.load(fh)
    except Exception:
        return default
    user_topic = cfg.get('user_topic') or cfg.get('topic') or ''
    if not user_topic:
        return default
    conv = user_topic.strip().replace(' ', '_').replace('-', '_')
    conv = re.sub(r'_+', '_', conv)
    return conv

def extract_paper_classifications(taxonomy_node, dimension, path="", classifications=None, user_topic_prefix=None, korean_names=None):
    """Recursively extract paper IDs and their classifications from taxonomy tree
    - user_topic_prefix: converted user_topic (spaces/'-' -> '_')
    - korean_names: dict mapping english dim -> korean name
    """
    if classifications is None:
        classifications = defaultdict(list)
    if korean_names is None:
        korean_names = get_dimension_names_korean()
    
    current_label = taxonomy_node.get('label', '')
    level = taxonomy_node.get('level', 0)
    
    # If this is the root of the taxonomy for this dimension (level 0),
    # use only the dimension name (no korean translation in path)
    if level == 0:
        current_path = dimension
    else:
        current_path = f"{path}/{current_label}" if path else current_label
    
    # If the tree still contains the original user_topic prefix, replace it
    if user_topic_prefix:
        if current_path.startswith(f'{user_topic_prefix}/'):
            current_path = current_path.replace(f'{user_topic_prefix}/', f'{dimension}/', 1)
        elif current_path == user_topic_prefix:
            current_path = dimension
    
    # Get papers at this node
    paper_ids = taxonomy_node.get('paper_ids', [])
    for paper_id in paper_ids:
        classifications[paper_id].append({
            'dimension': dimension,
            'dimension_korean': korean_names.get(dimension, dimension),
            'path': current_path,
            'label': current_label,
            'level': level
        })
    
    # Recursively process children, pass current_path so descendants build correct full path
    children = taxonomy_node.get('children', {})
    if isinstance(children, dict):
        for child_label, child_node in children.items():
            extract_paper_classifications(child_node, dimension, current_path, classifications, user_topic_prefix, korean_names)
    elif isinstance(children, list):
        for child_node in children:
            extract_paper_classifications(child_node, dimension, current_path, classifications, user_topic_prefix, korean_names)
    
    return classifications

def load_taxonomy_files(data_dir):
    """Load all taxonomy JSON files by scanning directory directly"""
    data_dir = Path(data_dir)
    all_classifications = defaultdict(list)
    
    # Load korean name map and user topic prefix once
    main_dir = Path(__file__).parent.parent
    user_topic_prefix = _load_converted_user_topic(main_dir)
    korean_names = get_dimension_names_korean()

    # Scan for all final_taxo_*.json files directly (do not rely on config dimension names)
    json_files = sorted(data_dir.glob("final_taxo_*.json"))
    if not json_files:
        print(f"Warning: No final_taxo_*.json files found in {data_dir}")
        return all_classifications

    for json_file in json_files:
        # Extract dimension name from filename: final_taxo_{dim}.json
        dim = json_file.stem[len("final_taxo_"):]
        print(f"Loading {json_file.name}  (dimension: {dim})...")
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                taxonomy = json.load(f)
        except Exception as e:
            print(f"  - Error reading {json_file.name}: {e}")
            continue

        # Extract classifications (pass user_topic_prefix and korean_names)
        dim_classifications = extract_paper_classifications(taxonomy, dim, "", None, user_topic_prefix, korean_names)

        # Merge into all_classifications
        for paper_id, labels in dim_classifications.items():
            all_classifications[paper_id].extend(labels)

        print(f"  - Found classifications for {len(dim_classifications)} papers")

    return all_classifications

def merge_with_original_data(excel_path, classifications):
    """Merge classifications with original Excel data"""
    print(f"\nLoading original data from {excel_path.name}...")
    df = pd.read_excel(excel_path)
    print(f"  - Loaded {len(df)} papers")

    # Derive dimensions from actual classifications (not from config)
    actual_dims = sorted({cls['dimension'] for labels in classifications.values() for cls in labels})
    korean_names = get_dimension_names_korean()

    # Add classification columns
    df['classified'] = False
    for dim in actual_dims:
        korean_name = korean_names.get(dim, dim)
        df[f'{korean_name}'] = ''  # 컬럼명을 한글명으로만 사용
    df['all_labels'] = ''

    # determine converted user topic prefix once
    main_dir = Path(__file__).parent.parent
    user_topic_prefix = _load_converted_user_topic(main_dir)

    # Merge classifications
    classified_count = 0
    for idx, row in df.iterrows():
        paper_id = idx  # paper_id = row index (0-based)

        if paper_id in classifications:
            df.at[idx, 'classified'] = True
            classified_count += 1

            # Group by dimension and get deepest classification only
            dim_paths = defaultdict(list)
            all_labels = []

            for cls in classifications[paper_id]:
                dim = cls['dimension']
                korean_dim = cls.get('dimension_korean', dim)
                path = cls['path']
                label = cls['label']
                level = cls.get('level', 0)

                # Classifications already processed by extract_paper_classifications
                # but add safety net for any remaining user_topic_prefix
                if path.startswith(f'{user_topic_prefix}/'):
                    path = path.replace(f'{user_topic_prefix}/', f'{dim}/', 1)
                elif path == user_topic_prefix:
                    path = f"{dim}/{korean_dim}"

                dim_paths[dim].append((path, level))
                all_labels.append(f"{korean_dim}:{label}")

            # For each dimension, keep only the deepest level classification
            for dim, path_level_pairs in dim_paths.items():
                korean_name = korean_names.get(dim, dim)
                if korean_name in df.columns:
                    # Get the path with maximum level (deepest classification)
                    deepest_path, max_level = max(path_level_pairs, key=lambda x: x[1])
                    # For level 0, just use dimension name (no duplication)
                    if max_level == 0:
                        df.at[idx, korean_name] = dim
                    else:
                        df.at[idx, korean_name] = deepest_path

            # Fill all_labels column
            df.at[idx, 'all_labels'] = ' | '.join(all_labels)

    print(f"  - Merged classifications for {classified_count} papers")
    print(f"  - Unclassified: {len(df) - classified_count} papers")

    return df

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Merge taxonomy classification results with original dataset')
    parser.add_argument('excel_file', help='Path to the input Excel file')
    parser.add_argument('--data-dir', default='./datasets/posco', 
                       help='Directory containing taxonomy JSON files (default: ./datasets/posco)')
    parser.add_argument('--output-excel', help='Output Excel file path (default: auto-generated)')
    parser.add_argument('--output-csv', help='Output CSV file path (default: auto-generated)')
    
    args = parser.parse_args()
    
    # Setup paths
    data_dir = Path(args.data_dir)
    excel_path = Path(args.excel_file)
    
    if not excel_path.exists():
        print(f"Error: Excel file not found: {excel_path}")
        return
    
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        return
    
    # Generate output paths if not specified (save in main directory)
    main_dir = Path(__file__).parent.parent  # go_taxoadapt main directory
    
    if args.output_excel:
        output_path = Path(args.output_excel)
    else:
        output_path = main_dir / f'{excel_path.stem}_battery_taxonomy.xlsx'
    
    if args.output_csv:
        output_csv_path = Path(args.output_csv)
    else:
        output_csv_path = main_dir / f'{excel_path.stem}_battery_taxonomy.csv'
    
    print("=" * 60)
    print("Electrical Steel Taxonomy Merge Tool")
    print("=" * 60)
    
    # Load taxonomy classifications
    classifications = load_taxonomy_files(data_dir)
    print(f"\nTotal papers with classifications: {len(classifications)}")
    
    # Load and merge with original data
    df_merged = merge_with_original_data(excel_path, classifications)
    
    # Save results
    print(f"\nSaving results...")
    
    # Save Excel with auto-adjusted column widths 
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df_merged.to_excel(writer, index=False, sheet_name='Sheet1')
        
        # Auto-adjust column widths
        worksheet = writer.sheets['Sheet1']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"  ✓ Excel saved: {output_path.name}")
    
    df_merged.to_csv(output_csv_path, index=False, encoding='utf-8')
    print(f"  ✓ CSV saved: {output_csv_path.name}")
    
    # Print statistics
    print("\n" + "=" * 60)
    print("Statistics")
    print("=" * 60)
    print(f"Total papers: {len(df_merged)}")
    print(f"Classified papers: {df_merged['classified'].sum()}")
    print(f"Unclassified papers: {(~df_merged['classified']).sum()}")
    print()
    
    # Derive dimensions from actual classifications for main() CLI usage
    dimensions = sorted({cls['dimension'] for labels in classifications.values() for cls in labels})
    korean_names = get_dimension_names_korean()
    for dim in dimensions:
        korean_name = korean_names.get(dim, dim)
        col_name = korean_name  # 한글명만 사용
        count = (df_merged[col_name] != '').sum()
        print(f"{korean_name:<30s} ({dim:<30s}): {count:5d} papers")
    
    print("\n" + "=" * 60)
    print("✓ Merge completed!")
    print("=" * 60)
    print(f"\nOutput files:")
    print(f"  - {output_path}")
    print(f"  - {output_csv_path}")

if __name__ == "__main__":
    main()
