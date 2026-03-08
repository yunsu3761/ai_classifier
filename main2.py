import os
import sys

# Fix Unicode encoding issues on Windows
if sys.platform.startswith('win'):
    # Set console to UTF-8 encoding
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

# Set environment variables to fix torch DLL loading issues on Windows
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKLDNN_VERBOSE'] = '0'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'

import json
import shutil
from collections import deque
from contextlib import redirect_stdout
import argparse
from tqdm import tqdm
import multiprocessing
import copy
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# For CPU-only mode, no special multiprocessing setup needed
if __name__ == "__main__":
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set

from model_definitions import initializeLLM, promptLLM, constructPrompt
from model_definitions import load_all_api_keys, create_openai_client
from prompts import multi_dim_prompt, NodeListSchema, generate_type_cls_system_instruction, type_cls_main_prompt, TypeClsSchema, dimension_definitions as prompt_dimension_definitions
from taxonomy import Node, DAG


from expansion import expandNodeWidth, expandNodeDepth
from paper import Paper
from utils import clean_json_string


def save_step4_full_checkpoint(checkpoint_path, roots, id2node, label2node, visited, queue, internal_collection, last_info=None):
    """Save full Step 4 state including taxonomy structure, paper assignments, and queue.
    This allows proper resumption after a crash."""
    # Save taxonomy structure for each dimension
    taxonomy_state = {}
    for dim, root in roots.items():
        taxonomy_state[dim] = root.to_dict()
    
    # Save paper assignments: which papers are assigned to which nodes
    paper_assignments = {}
    for node_id, node in id2node.items():
        if len(node.papers) > 0:
            paper_assignments[str(node_id)] = list(node.papers.keys())
    
    # Save paper labels
    paper_labels = {}
    for p_id, paper in internal_collection.items():
        if hasattr(paper, 'labels') and paper.labels:
            paper_labels[str(p_id)] = paper.labels
    
    # Save queue as list of (node_id) for reconstruction
    queue_node_ids = [node.id for node in queue]
    
    checkpoint_data = {
        'visited': list(visited),
        'queue_node_ids': queue_node_ids,
        'taxonomy_state': taxonomy_state,
        'paper_assignments': paper_assignments,
        'paper_labels': paper_labels,
    }
    if last_info:
        checkpoint_data.update(last_info)
    
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    print(f"[CHECKPOINT] Saved full Step4 state: {len(visited)} visited, {len(queue_node_ids)} in queue")


def load_step4_full_checkpoint(checkpoint_path, args, internal_collection):
    """Load full Step 4 state and reconstruct taxonomy, paper assignments, and queue."""
    with open(checkpoint_path, 'r', encoding='utf-8') as f:
        checkpoint_data = json.load(f)
    
    visited = set(checkpoint_data.get('visited', []))
    
    # Check if this is a full checkpoint (has taxonomy_state) or old-style
    if 'taxonomy_state' not in checkpoint_data:
        print("[CHECKPOINT] Old-style checkpoint detected, cannot fully resume. Starting fresh Step4.")
        return None
    
    # Reconstruct taxonomy from saved state
    roots = {}
    id2node = {}
    label2node = {}
    
    for dim, root_dict in checkpoint_data['taxonomy_state'].items():
        root = Node.from_dict(root_dict, id2node, label2node)
        roots[dim] = root
        mod_topic = args.topic.replace(' ', '_').lower()
        label2node[mod_topic + f"_{dim}"] = root
    
    # Restore paper assignments
    paper_assignments = checkpoint_data.get('paper_assignments', {})
    for node_id_str, paper_ids in paper_assignments.items():
        node_id = int(node_id_str)
        if node_id in id2node:
            node = id2node[node_id]
            for p_id in paper_ids:
                if p_id in internal_collection:
                    node.papers[p_id] = internal_collection[p_id]
    
    # Restore paper labels
    paper_labels = checkpoint_data.get('paper_labels', {})
    for p_id_str, labels in paper_labels.items():
        p_id = int(p_id_str)
        if p_id in internal_collection:
            internal_collection[p_id].labels = labels
    
    # Reconstruct queue from saved node IDs
    queue_node_ids = checkpoint_data.get('queue_node_ids', [])
    queue = deque()
    for nid in queue_node_ids:
        if nid in id2node:
            queue.append(id2node[nid])
    
    print(f"[CHECKPOINT] Restored: {len(id2node)} nodes, {len(visited)} visited, {len(queue)} in queue")
    return {
        'roots': roots,
        'id2node': id2node,
        'label2node': label2node,
        'visited': visited,
        'queue': queue,
    }


def create_dim_args(args, api_key=None):
    """Create a copy of args with its own OpenAI client for thread-safe parallel use."""
    dim_args = argparse.Namespace(**vars(args))
    dim_args.client = {}
    if api_key:
        dim_args.client['gpt'] = create_openai_client(api_key)
    else:
        # Reuse the existing client (single-key mode)
        dim_args.client = args.client
    return dim_args


def load_taxonomy_from_final_json(json_path, dimension, internal_collection, id_counter_start=0):
    """Load taxonomy from final_taxo_*.json file (display() format) for resume.
    
    The final_taxo JSON format (from display()) differs from the from_dict format:
    - children is a list (not dict keyed by label)
    - no 'id' field
    - no 'dimension' field
    - has 'paper_ids' and 'example_papers' fields
    
    Returns: root, id2node, label2node, id_counter
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    id2node = {}
    label2node = {}
    id_counter = [id_counter_start]  # mutable for nested function
    
    def convert_node(node_data, parent=None):
        label = node_data.get('label', '')
        mod_label = label.replace(' ', '_').lower()
        
        node = Node(
            id=id_counter[0],
            label=mod_label,
            dimension=dimension,
            description=node_data.get('description', ''),
            source=node_data.get('source', 'Initial'),
        )
        id2node[id_counter[0]] = node
        label2node[f"{mod_label}_{dimension}"] = node
        id_counter[0] += 1
        
        if parent:
            node.parents.append(parent)
            node.level = parent.level + 1
            parent.children[mod_label] = node
        
        # Restore papers
        paper_ids = node_data.get('paper_ids', [])
        for p_id in paper_ids:
            if p_id in internal_collection:
                node.papers[p_id] = internal_collection[p_id]
        
        # Process children (list format from display())
        children_data = node_data.get('children', [])
        if isinstance(children_data, list):
            for child_data in children_data:
                if isinstance(child_data, dict) and 'label' in child_data:
                    convert_node(child_data, parent=node)
        elif isinstance(children_data, dict):
            for child_label, child_data in children_data.items():
                convert_node(child_data, parent=node)
        
        return node
    
    root = convert_node(data)
    return root, id2node, label2node, id_counter[0]


def get_max_depth_of_tree(root):
    """Get the maximum depth achieved in the taxonomy tree."""
    max_depth = root.level
    queue = deque([root])
    while queue:
        node = queue.popleft()
        max_depth = max(max_depth, node.level)
        for child in node.children.values():
            queue.append(child)
    return max_depth


def find_nodes_needing_expansion(root, max_depth, max_density):
    """Find nodes that need further expansion (for resume).
    
    A node needs expansion if:
    - It's a leaf node (no children) AND level < max_depth AND papers > max_density
    - It has children but some children are leaves that need depth expansion
    
    Returns: set of visited node ids, deque of nodes to process
    """
    visited = set()
    needs_expansion = deque()
    
    # BFS to find all nodes
    queue = deque([root])
    while queue:
        node = queue.popleft()
        if node.id in visited:
            continue
        
        if len(node.children) > 0:
            # Node has children -> mark as visited (already processed)
            visited.add(node.id)
            for child in node.children.values():
                queue.append(child)
                # Check if child is a leaf that needs expansion
                if len(child.children) == 0 and child.level < max_depth and len(child.papers) > max_density:
                    needs_expansion.append(child)
        else:
            # Leaf node - check if it needs expansion
            if node.level < max_depth and len(node.papers) > max_density:
                needs_expansion.append(node)
    
    return visited, needs_expansion


def find_unexpanded_nodes(root, max_depth, max_density, label2node, dim, visited):
    """Find nodes that still need expansion (have enough papers but no children at depth < max_depth).
    
    Returns list of nodes that need:
    1. Depth expansion: no children, below max_depth, papers > max_density
    2. Width/classify: has children but not yet visited
    """
    needs_expansion = []
    stack = [root]
    seen = set()
    
    while stack:
        node = stack.pop()
        if node.id in seen:
            continue
        seen.add(node.id)
        
        # Get paper count for this node
        node_key = node.label + f"_{dim}"
        if node_key in label2node:
            paper_count = len(label2node[node_key].papers)
        else:
            paper_count = len(node.papers)
        
        # Case 1: Node has NO children, has papers, and is below max_depth → needs depth expansion
        if len(node.children) == 0 and node.level < max_depth and paper_count > max_density:
            needs_expansion.append(node)
            print(f"  [find_unexpanded] DEPTH needed: {node.label} (level={node.level}, papers={paper_count})")
        
        # Case 2: Node has children but hasn't been visited → needs classify + width
        elif len(node.children) > 0 and node.id not in visited:
            if node.level < max_depth:
                needs_expansion.append(node)
                print(f"  [find_unexpanded] CLASSIFY+WIDTH needed: {node.label} (level={node.level}, papers={paper_count}, children={len(node.children)})")
            # Also check children
            for child in node.children.values():
                stack.append(child)
        
        # Case 3: Node has children, already visited → just traverse children
        elif len(node.children) > 0:
            for child in node.children.values():
                stack.append(child)
    
    return needs_expansion


def step4_process_single_dimension(dim, dim_args, root, dim_id2node, dim_label2node, 
                                    internal_collection, data_dir):
    """Process width/depth expansion for a single dimension (thread worker).
    
    Each dimension has its own:
    - dim_args: with separate OpenAI client (separate API key)
    - dim_id2node / dim_label2node: dimension-scoped node maps
    - root: the root Node for this dimension
    
    Returns dict with updated state for this dimension.
    """
    dim_checkpoint = f'{data_dir}/step4_checkpoint_{dim}.json'
    
    # === 1. Try to restore from checkpoint ===
    visited = set()
    queue = deque()
    
    if os.path.exists(dim_checkpoint):
        try:
            restored = load_step4_full_checkpoint(dim_checkpoint, dim_args, internal_collection)
            if restored is not None and dim in restored.get('roots', {}):
                root = restored['roots'][dim]
                dim_id2node = {nid: node for nid, node in restored['id2node'].items() if node.dimension == dim}
                dim_label2node = {lbl: node for lbl, node in restored['label2node'].items() if node.dimension == dim}
                visited = restored.get('visited', set())
                raw_queue = restored.get('queue', [])
                queue = deque([n for n in raw_queue if n.dimension == dim])
                print(f"[{dim}] Resumed from checkpoint: {len(visited)} visited, {len(queue)} in queue")
        except Exception as e:
            print(f"[{dim}] Failed to load checkpoint: {e}")
            import traceback
            traceback.print_exc()
    
    # === 2. If no queue from checkpoint, initialize from root ===
    if len(queue) == 0 and len(visited) == 0:
        queue = deque([root])
        print(f"[{dim}] Starting fresh with root node")
    
    # === 3. AUTO-RESUME: If queue is empty but tree has unexpanded nodes ===
    if len(queue) == 0 and len(dim_id2node) > 1:
        print(f"[{dim}] Queue empty after checkpoint load. Scanning for unexpanded nodes...")
        unexpanded = find_unexpanded_nodes(root, dim_args.max_depth, dim_args.max_density, 
                                            dim_label2node, dim, visited)
        if unexpanded:
            queue = deque(unexpanded)
            print(f"[{dim}] AUTO-RESUME: Found {len(queue)} nodes needing expansion:")
            for n in unexpanded:
                node_key = n.label + f"_{dim}"
                pc = len(dim_label2node[node_key].papers) if node_key in dim_label2node else len(n.papers)
                has_children = "yes" if len(n.children) > 0 else "no"
                print(f"[{dim}]   - {n.label} (level={n.level}, papers={pc}, children={has_children})")
    
    # === 4. Check if nothing to do ===
    if len(queue) == 0:
        print(f"[{dim}] ✅ Nothing to expand. Already complete!")
        return {
            'dim': dim,
            'root': root,
            'id2node': dim_id2node,
            'label2node': dim_label2node,
            'visited': visited,
        }
    
    print(f"[{dim}] Starting expansion with {len(queue)} nodes in queue")
    
    # === 5. Main BFS expansion loop ===
    max_iterations = 500  # Safety limit
    iteration = 0
    
    while queue and iteration < max_iterations:
        iteration += 1
        curr_node = queue.popleft()
        print(f'[{dim}] VISITING {curr_node.label} AT LEVEL {curr_node.level}. {len(queue)} NODES LEFT! (iter={iteration})')
        
        if len(curr_node.children) > 0:
            # --- Node has children: classify papers + width expansion ---
            if curr_node.id in visited:
                print(f"[{dim}]   Already visited, skipping.")
                continue
            visited.add(curr_node.id)

            # Classify papers into children
            print(f"[{dim}]   Classifying papers for {curr_node.label}...")
            curr_node.classify_node(dim_args, dim_label2node, visited)

            # Width expansion
            new_sibs = expandNodeWidth(dim_args, curr_node, dim_id2node, dim_label2node)
            print(f'[{dim}]   (WIDTH) new siblings: {new_sibs}')

            # Save checkpoint
            save_step4_full_checkpoint(dim_checkpoint, {dim: root}, dim_id2node, dim_label2node, 
                                       visited, queue, internal_collection,
                                       {'last_node': curr_node.label, 'last_action': 'width_expansion_completed'})

            # Re-classify if new siblings were added
            if len(new_sibs) > 0:
                print(f"[{dim}]   Re-classifying after width expansion...")
                curr_node.classify_node(dim_args, dim_label2node, visited)
                
                # Log paper counts for new siblings
                for sib_label in new_sibs:
                    sib_key = sib_label + f"_{dim}"
                    if sib_key in dim_label2node:
                        sib_papers = len(dim_label2node[sib_key].papers)
                        print(f"[{dim}]   New sibling '{sib_label}': {sib_papers} papers")
                        if sib_papers == 0:
                            print(f"[{dim}]   ⚠️ WARNING: '{sib_label}' has 0 papers")
            
            # Save checkpoint after full processing
            save_step4_full_checkpoint(dim_checkpoint, {dim: root}, dim_id2node, dim_label2node, 
                                       visited, queue, internal_collection,
                                       {'last_node': curr_node.label, 'last_action': 'node_completed'})
            
            # Add children to queue if they meet expansion criteria
            for child_label, child_node in curr_node.children.items():
                child_key = child_label + f"_{curr_node.dimension}"
                if child_key in dim_label2node:
                    c_papers = dim_label2node[child_key].papers
                else:
                    c_papers = child_node.papers
                
                paper_count = len(c_papers)
                
                if (child_node.level < dim_args.max_depth) and (paper_count > dim_args.max_density):
                    queue.append(child_node)
                    print(f"[{dim}]   → Child '{child_label}' added to queue (level={child_node.level}, papers={paper_count})")
                else:
                    if child_node.level >= dim_args.max_depth:
                        reason = f"max_depth reached (level={child_node.level})"
                    else:
                        reason = f"papers={paper_count} <= max_density={dim_args.max_density}"
                    print(f"[{dim}]   → Child '{child_label}' skipped ({reason})")
        
        else:
            # --- Node has NO children: depth expansion ---
            node_key = curr_node.label + f"_{dim}"
            if node_key in dim_label2node:
                paper_count = len(dim_label2node[node_key].papers)
            else:
                paper_count = len(curr_node.papers)
            
            print(f"[{dim}]   (DEPTH) Expanding {curr_node.label} (level={curr_node.level}, papers={paper_count})")
            
            if paper_count <= dim_args.max_density:
                print(f"[{dim}]   ⚠️ Skipping: papers={paper_count} <= max_density={dim_args.max_density}")
                continue
            
            if curr_node.level >= dim_args.max_depth:
                print(f"[{dim}]   ⚠️ Skipping: level={curr_node.level} >= max_depth={dim_args.max_depth}")
                continue
            
            new_children, success = expandNodeDepth(dim_args, curr_node, dim_id2node, dim_label2node)
            print(f'[{dim}]   (DEPTH) result: {len(new_children)} children, success={success}')
            
            if len(new_children) > 0:
                for nc in new_children:
                    print(f"[{dim}]     New child: {nc}")
            
            if (len(new_children) > 0) and success:
                queue.append(curr_node)
                print(f"[{dim}]   → Re-added {curr_node.label} to queue for classify+width")
            elif not success:
                print(f"[{dim}]   ❌ Depth expansion failed for {curr_node.label}")
            else:
                print(f"[{dim}]   ⚠️ No new children generated for {curr_node.label}")
            
            # Save checkpoint after depth expansion
            save_step4_full_checkpoint(dim_checkpoint, {dim: root}, dim_id2node, dim_label2node, 
                                       visited, queue, internal_collection,
                                       {'last_node': curr_node.label, 'last_action': 'depth_expansion'})
    
    # === 6. Post-loop: Check if there are still unexpanded nodes ===
    print(f"\n[{dim}] BFS loop finished after {iteration} iterations.")
    
    remaining = find_unexpanded_nodes(root, dim_args.max_depth, dim_args.max_density, 
                                       dim_label2node, dim, visited)
    if remaining:
        print(f"[{dim}] ⚠️ {len(remaining)} nodes still need expansion (may need another --resume run):")
        for n in remaining:
            node_key = n.label + f"_{dim}"
            pc = len(dim_label2node[node_key].papers) if node_key in dim_label2node else len(n.papers)
            print(f"[{dim}]   - {n.label} (level={n.level}, papers={pc}, children={len(n.children)})")
    else:
        print(f"[{dim}] ✅ All nodes fully expanded!")
    
    # Save final state checkpoint
    save_step4_full_checkpoint(dim_checkpoint, {dim: root}, dim_id2node, dim_label2node, 
                               visited, queue, internal_collection,
                               {'last_node': 'COMPLETED', 'last_action': 'step4_finished'})
    
    print(f"[{dim}] STEP4 completed! Processed {len(visited)} nodes, {iteration} iterations.")
    
    return {
        'dim': dim,
        'root': root,
        'id2node': dim_id2node,
        'label2node': dim_label2node,
        'visited': visited,
    }


def step4_parallel(args, roots, id2node, label2node, internal_collection):
    """Run Step 4 in parallel across dimensions using ThreadPoolExecutor.
    
    Each dimension gets:
    - Its own OpenAI client (with its own API key if available)
    - Its own subset of id2node/label2node (filtered by dimension)
    - Its own BFS queue
    """
    api_keys = load_all_api_keys()
    dimensions = list(roots.keys())
    
    print(f"\n{'='*60}")
    print(f"PARALLEL STEP 4: {len(dimensions)} dimensions, {len(api_keys)} API key(s)")
    print(f"{'='*60}")
    
    # Split id2node and label2node per dimension
    dim_states = {}
    for dim in dimensions:
        dim_id2node = {nid: node for nid, node in id2node.items() if node.dimension == dim}
        dim_label2node = {lbl: node for lbl, node in label2node.items() if node.dimension == dim}
        dim_states[dim] = (dim_id2node, dim_label2node)
    
    # Assign API keys round-robin to dimensions
    dim_args_map = {}
    for i, dim in enumerate(dimensions):
        key_idx = i % len(api_keys) if api_keys else 0
        api_key = api_keys[key_idx] if api_keys else None
        dim_args_map[dim] = create_dim_args(args, api_key)
        key_preview = api_key[:15] + '...' if api_key else 'None'
        print(f"  [{dim}] -> API key #{key_idx + 1} ({key_preview})")
    
    # Run dimensions in parallel
    results = {}
    max_workers = min(len(dimensions), len(api_keys)) if api_keys else 1
    print(f"\nUsing {max_workers} parallel worker(s)")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for dim in dimensions:
            dim_id2node, dim_label2node = dim_states[dim]
            future = executor.submit(
                step4_process_single_dimension,
                dim=dim,
                dim_args=dim_args_map[dim],
                root=roots[dim],
                dim_id2node=dim_id2node,
                dim_label2node=dim_label2node,
                internal_collection=internal_collection,
                data_dir=args.data_dir,
            )
            futures[future] = dim
        
        for future in as_completed(futures):
            dim = futures[future]
            try:
                result = future.result()
                results[dim] = result
                print(f"\n✅ [{dim}] Expansion completed successfully!")
            except Exception as e:
                print(f"\n❌ [{dim}] Expansion FAILED: {e}")
                import traceback
                traceback.print_exc()
    
    # Merge results back into unified state
    merged_roots = {}
    merged_id2node = {}
    merged_label2node = {}
    total_visited = set()
    
    for dim, result in results.items():
        merged_roots[dim] = result['root']
        merged_id2node.update(result['id2node'])
        merged_label2node.update(result['label2node'])
        total_visited.update(result['visited'])
    
    # For dimensions that failed, keep original state
    for dim in dimensions:
        if dim not in results:
            merged_roots[dim] = roots[dim]
            dim_id2node, dim_label2node = dim_states[dim]
            merged_id2node.update(dim_id2node)
            merged_label2node.update(dim_label2node)
    
    print(f"\n{'='*60}")
    print(f"PARALLEL STEP 4 COMPLETE: {len(results)}/{len(dimensions)} dimensions succeeded")
    print(f"Total nodes processed: {len(total_visited)}")
    print(f"{'='*60}\n")
    
    return merged_roots, merged_id2node, merged_label2node

   
def construct_dataset(args):
    """
    Load papers from internal.txt (JSON Lines format).
    The web interface is responsible for creating internal.txt from uploaded data.
    Each line in internal.txt should be: {"Title": "...", "Abstract": "..."}
    """
    if not os.path.exists(args.data_dir):
        os.makedirs(args.data_dir)
    
    internal_path = os.path.join(args.data_dir, 'internal.txt')
    
    # Check if internal.txt exists and has content
    if not os.path.exists(internal_path):
        print(f"Error: internal.txt not found at {internal_path}")
        print("Please upload data through the web interface first.")
        return {}, 0
    
    with open(internal_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    
    if not content:
        print(f"Error: internal.txt is empty at {internal_path}")
        print("Please upload data through the web interface first.")
        return {}, 0
    
    # Read papers from internal.txt (JSON Lines format)
    internal_collection = {}
    internal_count = 0
    paper_id = 0
    
    with open(internal_path, 'r', encoding='utf-8') as f:
        for line in tqdm(f, desc="Loading papers"):
            line = line.strip()
            if not line:
                continue
            
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                # Try tab-separated format as fallback
                parts = line.split('\t')
                if len(parts) >= 3:
                    p = {'Title': parts[1], 'Abstract': parts[2]}
                elif len(parts) >= 2:
                    p = {'Title': parts[0], 'Abstract': parts[1]}
                else:
                    continue
            
            # Normalize keys (accept both 'Title'/'title' and 'Abstract'/'abstract')
            title = p.get('Title', p.get('title', '')).strip()
            abstract = p.get('Abstract', p.get('abstract', '')).strip()
            
            if not title and not abstract:
                continue
            
            # Limit samples for testing if specified
            if args.test_samples is not None and internal_count >= args.test_samples:
                print(f"Limiting to {args.test_samples} samples for testing")
                break
            
            internal_collection[paper_id] = Paper(paper_id, title, abstract, label_opts=args.dimensions, internal=True)
            internal_count += 1
            paper_id += 1
    
    print(f"Total # of Papers: {internal_count}")
    print(f"Internal: {internal_count}")
    
    return internal_collection, internal_count

def initialize_DAG(args, use_txt=True):
    """Initialize DAG either from txt files or using LLM"""
    
    if use_txt:
        # Load from txt files
        roots = {}
        id2node = {}
        label2node = {}
        
        for dim in args.dimensions:
            txt_file = f'{args.data_dir}/initial_taxo_{dim}.txt'
            
            if not os.path.exists(txt_file):
                raise FileNotFoundError(f"Initial taxonomy file not found: {txt_file}")
            
            parsed_data = parse_initial_taxonomy_txt(txt_file)
            
            # Add id to each node
            node_counter = {'count': len(id2node)}
            def add_ids(node_dict, node_counter):
                node_dict['id'] = node_counter['count']
                node_counter['count'] += 1
                if 'children' in node_dict:
                    for child in node_dict['children'].values():
                        add_ids(child, node_counter)
            
            add_ids(parsed_data, node_counter)
            
            # Convert to Node objects
            root = Node.from_dict(parsed_data, id2node, label2node)
            roots[dim] = root
            mod_topic = args.topic.replace(' ', '_').lower()
            label2node[mod_topic + f"_{dim}"] = root
        
        return roots, id2node, label2node
    
    else:
        # Generate using LLM
        ## we want to make this a directed acyclic graph (DAG) so maintain a list of the nodes
        roots = {}
        id2node = {}
        label2node = {}
        idx = 0

        for dim in args.dimensions:
            mod_topic = args.topic.replace(' ', '_').lower()
            mod_full_topic = args.topic.replace(' ', '_').lower() + f"_{dim}"
            root = Node(
                    id=idx,
                    label=mod_topic,
                    dimension=dim
                )
            roots[dim] = root
            id2node[idx] = root
            label2node[mod_full_topic] = root
            idx += 1

        queue = deque([node for id, node in id2node.items()])

        # if taking long, you can probably parallelize this between the different taxonomies (expand by level)
        while queue:
            curr_node = queue.popleft()
            label = curr_node.label
            dim = curr_node.dimension
            # expand
            system_instruction, main_prompt, json_output_format = multi_dim_prompt(curr_node)
            prompts = [constructPrompt(args, system_instruction, main_prompt + "\n\n" + json_output_format)]
            outputs = promptLLM(args=args, prompts=prompts, schema=NodeListSchema, max_new_tokens=16384, json_mode=True, temperature=0.01, top_p=1.0)[0]
            outputs = json.loads(clean_json_string(outputs)) if "```" in outputs else json.loads(outputs.strip())
            outputs = outputs['root_topic'] if 'root_topic' in outputs else outputs[label]

            # add all children
            for key, value in outputs.items():
                mod_key = key.replace(' ', '_').lower()
                mod_full_key = mod_key + f"_{dim}"
                if mod_full_key not in label2node:
                    child_node = Node(
                            id=len(id2node),
                            label=mod_key,
                            dimension=dim,
                            description=value['description'],
                            parents=[curr_node]
                        )
                    curr_node.add_child(mod_key, child_node)
                    id2node[child_node.id] = child_node
                    label2node[mod_full_key] = child_node
                    if child_node.level < args.init_levels:
                        queue.append(child_node)
                elif label2node[mod_full_key] in label2node[label + f"_{dim}"].get_ancestors():
                    continue
                else:
                    child_node = label2node[mod_full_key]
                    curr_node.add_child(mod_key, child_node)
                    child_node.add_parent(curr_node)

        return roots, id2node, label2node


def parse_initial_taxonomy_txt(file_path):
    """Parse initial_taxo_*.txt file and return a dictionary structure"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    def parse_node(lines, start_idx):
        """Recursively parse a node and its children"""
        node = {}
        children = {}
        i = start_idx
        
        # Determine the base indent of this node
        base_indent = None
        while i < len(lines) and base_indent is None:
            stripped = lines[i].strip()
            if stripped and stripped.startswith('Label:'):
                base_indent = len(lines[i]) - len(lines[i].lstrip(' '))
                break
            i += 1
        
        if base_indent is None:
            return node, i
        
        # Parse current node's properties
        while i < len(lines):
            line = lines[i]
            indent = len(line) - len(line.lstrip(' '))
            stripped = line.strip()
            
            # Skip empty lines and separators
            if not stripped or stripped.startswith('---'):
                i += 1
                continue
            
            # Stop if we encounter a node at same or lower indent level (after we've started parsing)
            if stripped.startswith('Label:') and indent == base_indent and 'label' in node:
                break
            elif stripped.startswith('Label:') and indent < base_indent:
                break
            
            # Parse node properties at base indent level
            if indent == base_indent:
                if stripped.startswith('Label:'):
                    node['label'] = stripped.split('Label:')[1].strip()
                elif stripped.startswith('Dimension:'):
                    node['dimension'] = stripped.split('Dimension:')[1].strip()
                elif stripped.startswith('Description:'):
                    desc = stripped.split('Description:')[1].strip()
                    node['description'] = desc if desc else ''
                elif stripped.startswith('Level:'):
                    node['level'] = int(stripped.split('Level:')[1].strip())
                elif stripped.startswith('Source:'):
                    node['source'] = stripped.split('Source:')[1].strip()
                elif stripped == 'Children:':
                    # Found children section, parse all children
                    i += 1
                    while i < len(lines):
                        next_line = lines[i]
                        next_indent = len(next_line) - len(next_line.lstrip(' '))
                        next_stripped = next_line.strip()
                        
                        # Skip separators and empty lines
                        if not next_stripped or next_stripped.startswith('---'):
                            i += 1
                            continue
                        
                        # Child starts with Label: at deeper indent
                        if next_stripped.startswith('Label:') and next_indent > base_indent:
                            child_node, i = parse_node(lines, i)
                            if child_node and 'label' in child_node:
                                children[child_node['label']] = child_node
                            continue
                        
                        # If we're back to parent indent or less, stop parsing children
                        if next_indent <= base_indent:
                            break
                        
                        i += 1
                    continue
            
            i += 1
        
        if children:
            node['children'] = children
        
        return node, i
    
    root_node, _ = parse_node(lines, 0)
    return root_node


def main(args):

    print("######## STEP 1: LOAD IN DATASET ########")

    internal_collection, internal_count = construct_dataset(args)
    
    print(f'Internal: {internal_count}')

    print("######## STEP 2: INITIALIZE DAG ########")
    args = initializeLLM(args)

    # Check if all initial taxonomy txt files already exist
    initial_txt_files_exist = all(
        os.path.exists(f'{args.data_dir}/initial_taxo_{dim}.txt') 
        for dim in args.dimensions
    )
       
    if initial_txt_files_exist:
        print(f"Using existing initial taxonomy txt files from: {args.data_dir}/initial_taxo_*.txt")
        roots, id2node, label2node = initialize_DAG(args, use_txt=True)
        
        # Print taxonomy structure to confirm it's loaded from txt files
        print(f"\n확인: txt 파일에서 로드된 taxonomy 구조")
        for dim in args.dimensions:
            print(f"  {dim}: root='{roots[dim].label}', children={len(roots[dim].children)}, total_nodes={len([n for n in id2node.values() if n.dimension == dim])}")
        print()
    else:
        print("No initial taxonomy files found. Generating initial DAG with LLM...")
        roots, id2node, label2node = initialize_DAG(args, use_txt=False)
        
        # Save txt files
        for dim in args.dimensions:
            with open(f'{args.data_dir}/initial_taxo_{dim}.txt', 'w', encoding='utf-8') as f:
                with redirect_stdout(f):
                    roots[dim].display(0, indent_multiplier=5)

    print("######## STEP 3: CLASSIFY PAPERS BY DIMENSION (TASK, METHOD, DATASET, EVAL, APPLICATION, etc.) ########")

    dags = {dim:DAG(root=root, dim=dim) for dim, root in roots.items()}
    
    # Print info for all DAGs
    for dim in args.dimensions:
        print(f"\n{dim} DAG:")
        print(f"  Root: {dags[dim].root.label}")
        print(f"  Root children: {list(dags[dim].root.children.keys())}")
        print(f"  Root description: {dags[dim].root.description}")

    # Check if classification checkpoint exists
    classification_checkpoint = f'{args.data_dir}/classification_checkpoint.json'
    
    if os.path.exists(classification_checkpoint):
        print(f"Loading classification results from checkpoint: {classification_checkpoint}")
        with open(classification_checkpoint, 'r') as f:
            checkpoint_data = json.load(f)
            outputs = checkpoint_data['outputs']
    else:
        # do for internal collection
        print(f"Running classification on {len(internal_collection)} papers...")
        type_cls_system_instruction = generate_type_cls_system_instruction(prompt_dimension_definitions, args.topic)
        prompts = [constructPrompt(args, type_cls_system_instruction, type_cls_main_prompt(paper, prompt_dimension_definitions, args.topic)) for paper in internal_collection.values()]
        outputs = promptLLM(args=args, prompts=prompts, schema=TypeClsSchema, max_new_tokens=16384, json_mode=True, temperature=0.1, top_p=0.99)
        outputs = [json.loads(clean_json_string(c)) if "```" in c else json.loads(c.strip()) for c in outputs]
        
        # Save checkpoint
        print(f"Saving classification checkpoint to: {classification_checkpoint}")
        with open(classification_checkpoint, 'w') as f:
            json.dump({'outputs': outputs}, f, indent=2)

    for r in roots:
        roots[r].papers = {}
    type_dist = {dim:[] for dim in args.dimensions}
    for p_id, out in enumerate(outputs):
        internal_collection[p_id].labels = {}
        for key, val in out.items():
            # Only process keys that are in our configured dimensions
            if val and key in args.dimensions:
                type_dist[key].append(internal_collection[p_id])
                internal_collection[p_id].labels[key] = []
                roots[key].papers[p_id] = internal_collection[p_id]
    
    print(str({k:len(v) for k,v in type_dist.items()}))


    # for each node, classify its papers for the children or perform depth expansion
    print("######## STEP 4: ITERATIVELY CLASSIFY & EXPAND (PARALLEL BY DIMENSION) ########")

    # === RESUME MODE: Load from final_taxo files if they exist and are incomplete ===
    if getattr(args, 'resume', False):
        print("\n🔄 RESUME MODE: Checking existing final_taxo files...")
        dims_to_resume = []
        dims_already_done = []
        
        for dim in args.dimensions:
            final_json = f'{args.data_dir}/final_taxo_{dim}.json'
            if os.path.exists(final_json):
                # Load existing taxonomy from final_taxo
                loaded_root, loaded_id2node, loaded_label2node, new_id_counter = \
                    load_taxonomy_from_final_json(final_json, dim, internal_collection, id_counter_start=len(id2node))
                
                max_achieved = get_max_depth_of_tree(loaded_root)
                node_count = len(loaded_id2node)
                
                # Replace with loaded taxonomy
                roots[dim] = loaded_root
                id2node.update(loaded_id2node)
                label2node.update(loaded_label2node)
                mod_topic = args.topic.replace(' ', '_').lower()
                label2node[mod_topic + f"_{dim}"] = loaded_root
                
                if max_achieved >= args.max_depth:
                    dims_already_done.append(dim)
                    print(f"  ✅ [{dim}] COMPLETE: {node_count} nodes, max_level={max_achieved}")
                else:
                    dims_to_resume.append(dim)
                    print(f"  🔄 [{dim}] INCOMPLETE: {node_count} nodes, max_level={max_achieved} < max_depth={args.max_depth}")
            else:
                dims_to_resume.append(dim)
                print(f"  ❌ [{dim}] NO FILE: will run from scratch")
        
        print(f"\n📊 Resume summary: {len(dims_already_done)} done, {len(dims_to_resume)} to resume")
        if dims_already_done:
            print(f"   Done: {', '.join(dims_already_done)}")
        if dims_to_resume:
            print(f"   Resume: {', '.join(dims_to_resume)}")
        print()
        
        # Update dimensions to only process incomplete ones
        if not dims_to_resume:
            print("🎉 All dimensions already complete! Skipping Step 4.")
            # Jump directly to Step 5
            print("######## STEP 5: SAVE THE TAXONOMY ########")
            try:
                for dim in args.dimensions:
                    with open(f'{args.data_dir}/final_taxo_{dim}.txt', 'w') as f:
                        with redirect_stdout(f):
                            taxo_dict = roots[dim].display(0, indent_multiplier=5)
                    with open(f'{args.data_dir}/final_taxo_{dim}.json', 'w', encoding='utf-8') as f:
                        json.dump(taxo_dict, f, ensure_ascii=False, indent=4)
                print("✅ All taxonomy files saved successfully!")
                print("🎉 TaxoAdapt completed successfully!")
            except Exception as e:
                print(f"❌ Error during Step 5 (saving): {e}")
                raise
            return
        
        # Only process incomplete dimensions
        args.resume_dimensions = dims_to_resume
    else:
        args.resume_dimensions = None

    # Check if multiple API keys are available for parallel execution
    api_keys = load_all_api_keys()
    dims_to_process = getattr(args, 'resume_dimensions', None) or args.dimensions
    print(f"[DEBUG] Detected {len(api_keys)} API key(s)")
    print(f"[DEBUG] API key previews: {[k[:15] + '...' if len(k) > 15 else k for k in api_keys]}")
    print(f"[DEBUG] Dimensions to process: {len(dims_to_process)} -> {dims_to_process}")
    
    if len(api_keys) > 1 and len(dims_to_process) > 1:
        # === PARALLEL MODE: Each dimension runs in its own thread with its own API key ===
        print(f"🚀 Running PARALLEL expansion: {len(dims_to_process)} dimensions × {len(api_keys)} API keys")
        # Only pass dimensions that need processing
        resume_roots = {dim: roots[dim] for dim in dims_to_process}
        new_roots, new_id2node, new_label2node = step4_parallel(args, resume_roots, id2node, label2node, internal_collection)
        roots.update(new_roots)
        id2node.update(new_id2node)
        label2node.update(new_label2node)
    else:
        # === SEQUENTIAL MODE: Original single-threaded behavior ===
        if len(api_keys) <= 1:
            print("ℹ️ Single API key detected. Running sequential mode.")
            print("   To enable parallel mode, set OPENAI_API_KEY_1, OPENAI_API_KEY_2, ... in .env")
        else:
            print("ℹ️ Single dimension. Running sequential mode.")
        
        # Load STEP4 checkpoint if exists
        step4_checkpoint = f'{args.data_dir}/step4_checkpoint.json'
        
        if os.path.exists(step4_checkpoint):
            print(f"Loading STEP4 checkpoint from: {step4_checkpoint}")
            restored = load_step4_full_checkpoint(step4_checkpoint, args, internal_collection)
            if restored is not None:
                roots = restored['roots']
                id2node = restored['id2node']
                label2node = restored['label2node']
                visited = restored['visited']
                queue = restored['queue']
                dags = {dim: DAG(root=root, dim=dim) for dim, root in roots.items()}
                print(f"Resuming from STEP4 with {len(visited)} nodes already processed, {len(queue)} in queue")
            else:
                visited = set()
                queue = deque([roots[r] for r in roots])
        else:
            visited = set()
            queue = deque([roots[r] for r in roots])

        while queue:
            curr_node = queue.popleft()
            print(f'VISITING {curr_node.label} ({curr_node.dimension}) AT LEVEL {curr_node.level}. WE HAVE {len(queue)} NODES LEFT IN THE QUEUE!')
            
            if len(curr_node.children) > 0:
                if curr_node.id in visited:
                    continue
                visited.add(curr_node.id)

                # classify
                curr_node.classify_node(args, label2node, visited)

                # sibling expansion if needed
                new_sibs = expandNodeWidth(args, curr_node, id2node, label2node)
                print(f'(WIDTH EXPANSION) new children for {curr_node.label} ({curr_node.dimension}) are: {str((new_sibs))}')

                # Save checkpoint immediately after width expansion (before re-classification)
                save_step4_full_checkpoint(step4_checkpoint, roots, id2node, label2node, visited,
                                           queue, internal_collection,
                                           {'last_node': f"{curr_node.label} ({curr_node.dimension})", 'last_action': 'width_expansion_completed'})

                # re-classify and re-do process if necessary
                if len(new_sibs) > 0:
                    print(f"Re-classifying {curr_node.label} after width expansion...")
                    curr_node.classify_node(args, label2node, visited)
                    print(f"Re-classification completed for {curr_node.label}")
                
                # Save STEP4 checkpoint after processing this node
                save_step4_full_checkpoint(step4_checkpoint, roots, id2node, label2node, visited,
                                           queue, internal_collection,
                                           {'last_node': f"{curr_node.label} ({curr_node.dimension})", 'last_action': 'node_completed'})
                
                # add children to queue if constraints are met
                for child_label, child_node in curr_node.children.items():
                    c_papers = label2node[child_label + f"_{curr_node.dimension}"].papers
                    if (child_node.level < args.max_depth) and (len(c_papers) > args.max_density):
                        queue.append(child_node)
            else:
                # no children -> perform depth expansion
                new_children, success = expandNodeDepth(args, curr_node, id2node, label2node)
                print(f'(DEPTH EXPANSION) new {len(new_children)} children for {curr_node.label} ({curr_node.dimension}) are: {str((new_children))}')
                if (len(new_children) > 0) and success:
                    queue.append(curr_node)
                
                # Save STEP4 checkpoint after depth expansion
                save_step4_full_checkpoint(step4_checkpoint, roots, id2node, label2node, visited,
                                           queue, internal_collection)
        
        print(f"STEP4 completed! Processed {len(visited)} nodes total.")
    
    print("######## STEP 5: SAVE THE TAXONOMY ########")
    try:
        for dim in args.dimensions:
            with open(f'{args.data_dir}/final_taxo_{dim}.txt', 'w') as f:
                with redirect_stdout(f):
                    taxo_dict = roots[dim].display(0, indent_multiplier=5)

            with open(f'{args.data_dir}/final_taxo_{dim}.json', 'w', encoding='utf-8') as f:
                json.dump(taxo_dict, f, ensure_ascii=False, indent=4)
        
        print("✅ All taxonomy files saved successfully!")
        
        # ✅ 모든 파일 저장 완료 후 checkpoint를 step4_checkpoints/{timestamp} 폴더로 이동
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        step4_backup_dir = f'{args.data_dir}/step4_checkpoints/{timestamp}'
        os.makedirs(step4_backup_dir, exist_ok=True)
        
        step4_checkpoint = f'{args.data_dir}/step4_checkpoint.json'
        if os.path.exists(step4_checkpoint):
            shutil.move(step4_checkpoint, f'{step4_backup_dir}/step4_checkpoint.json')
            print(f"📦 Step4 checkpoint moved to {step4_backup_dir}/")
        
        # 개별 차원 checkpoint들도 이동
        for dim in args.dimensions:
            dim_checkpoint = f'{args.data_dir}/step4_checkpoint_{dim}.json'
            if os.path.exists(dim_checkpoint):
                shutil.move(dim_checkpoint, f'{step4_backup_dir}/step4_checkpoint_{dim}.json')
                print(f"📦 {dim} checkpoint moved to {step4_backup_dir}/")
        
        print("🎉 TaxoAdapt completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during Step 5 (saving): {e}")
        print("📁 Checkpoints preserved for recovery.")
        raise  # Re-raise to maintain error handling




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--topic', type=str, default='cost-effective low-carborn steel technologies')
    parser.add_argument('--dataset', type=str, default='posco')
    parser.add_argument('--llm', type=str, default='gpt')
    parser.add_argument('--max_depth', type=int, default=4)
    parser.add_argument('--init_levels', type=int, default=1)
    parser.add_argument('--max_density', type=int, default=15)
    parser.add_argument('--test_samples', type=int, default=None, help='Number of papers to use for testing (None = use all)')
    parser.add_argument('--data_dir', type=str, default=None, help='Explicit data directory path (overrides --dataset path)')
    parser.add_argument('--resume', action='store_true', default=False, help='Resume from existing final_taxo files, only expanding incomplete dimensions')
    args = parser.parse_args()

    # If user provided a positional dataset name, use it to override the flag
    if getattr(args, 'dataset_pos', None):
        args.dataset = args.dataset_pos

    # Load dimensions dynamically from prompts.py
    from prompts import dimension_definitions as _dim_defs
    args.dimensions = list(_dim_defs.keys())

    if args.data_dir is None:
        args.data_dir = f"datasets/{args.dataset.lower().replace(' ', '_')}"
    args.internal = f"{args.data_dir}/internal.txt"

    main(args)