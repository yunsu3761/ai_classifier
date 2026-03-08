"""
Test script for:
1. Token truncation logic (model_definitions.py)
2. Step4 checkpoint save/load (main2.py)
3. UnboundLocalError fix (expansion.py)

Run: python -m tests.test_token_truncation_and_checkpoint
"""
import os
import sys
import json
import tempfile
import shutil
from collections import deque

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model_definitions import estimate_token_count, truncate_messages_to_token_limit
from taxonomy import Node
from paper import Paper

passed = 0
failed = 0

def test(name, condition):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name}")
        failed += 1


###############################################################################
# TEST 1: Token estimation
###############################################################################
print("\n===== TEST 1: Token Estimation =====")
test("Empty string = 0 tokens", estimate_token_count("") == 0)
test("None = 0 tokens", estimate_token_count(None) == 0)
test("400 chars ~ 100 tokens", estimate_token_count("a" * 400) == 100)
test("128000*4 chars ~ 128000 tokens", estimate_token_count("x" * (128000 * 4)) == 128000)


###############################################################################
# TEST 2: Truncation - short messages (no truncation needed)
###############################################################################
print("\n===== TEST 2: Truncation (short messages, no truncation) =====")
short_messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello, how are you?"}
]
result = truncate_messages_to_token_limit(short_messages, max_context_tokens=128000, reserved_output_tokens=3000)
test("Short messages not truncated", result == short_messages)


###############################################################################
# TEST 3: Truncation - long messages (truncation needed)
###############################################################################
print("\n===== TEST 3: Truncation (long messages, truncation) =====")
# Create a message that would be ~200,000 tokens (800,000 chars)
long_content = "word " * 160000  # ~800,000 chars = ~200,000 tokens
long_messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": long_content}
]
result = truncate_messages_to_token_limit(long_messages, max_context_tokens=128000, reserved_output_tokens=3000)
total_after = sum(estimate_token_count(m.get('content', '')) for m in result)
test(f"Truncated to fit: {total_after} <= 125000", total_after <= 125000)
test("System message preserved", result[0] == long_messages[0])
test("User message was truncated", len(result[1]['content']) < len(long_content))
test("Truncation marker present", "[TRUNCATED DUE TO TOKEN LIMIT]" in result[1]['content'])


###############################################################################
# TEST 4: Checkpoint save/load roundtrip
###############################################################################
print("\n===== TEST 4: Checkpoint Save/Load Roundtrip =====")

# Import checkpoint functions from main2
from main2 import save_step4_full_checkpoint, load_step4_full_checkpoint

# Create a temporary directory for checkpoint files
test_dir = tempfile.mkdtemp(prefix="taxoadapt_test_")
checkpoint_path = os.path.join(test_dir, "step4_checkpoint.json")

try:
    # Build a small taxonomy
    id2node = {}
    label2node = {}
    
    root = Node(id=0, label="steel_tech", dimension="Tech_Dim", description="Root node")
    id2node[0] = root
    label2node["steel_tech_Tech_Dim"] = root

    child1 = Node(id=1, label="hydrogen", dimension="Tech_Dim", description="Hydrogen tech", parents=[root], source="depth")
    root.children["hydrogen"] = child1
    id2node[1] = child1
    label2node["hydrogen_Tech_Dim"] = child1

    child2 = Node(id=2, label="biomass", dimension="Tech_Dim", description="Biomass tech", parents=[root], source="width")
    root.children["biomass"] = child2
    id2node[2] = child2
    label2node["biomass_Tech_Dim"] = child2

    roots = {"Tech_Dim": root}

    # Create mock papers
    dimensions = ["Tech_Dim"]
    papers = {
        0: Paper(0, "Paper A", "Abstract A about hydrogen", label_opts=dimensions, internal=True),
        1: Paper(1, "Paper B", "Abstract B about biomass", label_opts=dimensions, internal=True),
        2: Paper(2, "Paper C", "Abstract C about steel", label_opts=dimensions, internal=True),
    }
    
    # Assign papers to nodes
    root.papers = {0: papers[0], 1: papers[1], 2: papers[2]}
    child1.papers = {0: papers[0]}
    child2.papers = {1: papers[1]}
    
    # Set paper labels
    papers[0].labels = {"Tech_Dim": ["hydrogen"]}
    papers[1].labels = {"Tech_Dim": ["biomass"]}
    papers[2].labels = {"Tech_Dim": []}

    visited = {0}
    queue = deque([child1, child2])

    # Create mock args
    class MockArgs:
        topic = "steel_tech"
        dimensions = ["Tech_Dim"]
    args = MockArgs()

    # Save checkpoint
    save_step4_full_checkpoint(checkpoint_path, roots, id2node, label2node, visited, queue, papers,
                               {'last_node': 'steel_tech (Tech_Dim)', 'last_action': 'node_completed'})
    
    test("Checkpoint file created", os.path.exists(checkpoint_path))
    
    # Verify JSON is valid
    with open(checkpoint_path, 'r', encoding='utf-8') as f:
        saved_data = json.load(f)
    test("Checkpoint JSON is valid", isinstance(saved_data, dict))
    test("Has taxonomy_state", 'taxonomy_state' in saved_data)
    test("Has paper_assignments", 'paper_assignments' in saved_data)
    test("Has visited", 'visited' in saved_data)
    test("Has queue_node_ids", 'queue_node_ids' in saved_data)
    test("Visited contains node 0", 0 in saved_data['visited'])
    test("Queue has 2 nodes", len(saved_data['queue_node_ids']) == 2)
    
    # Load checkpoint 
    restored = load_step4_full_checkpoint(checkpoint_path, args, papers)
    test("Checkpoint loaded successfully", restored is not None)
    test("Restored roots has Tech_Dim", "Tech_Dim" in restored['roots'])
    test("Restored 3 nodes", len(restored['id2node']) == 3)
    test("Restored visited = {0}", restored['visited'] == {0})
    test("Restored queue has 2 nodes", len(restored['queue']) == 2)
    
    # Verify taxonomy structure
    restored_root = restored['roots']['Tech_Dim']
    test("Root label correct", restored_root.label == "steel_tech")
    test("Root has 2 children", len(restored_root.children) == 2)
    test("hydrogen child exists", "hydrogen" in restored_root.children)
    test("biomass child exists", "biomass" in restored_root.children)
    test("hydrogen source = depth", restored_root.children["hydrogen"].source == "depth")
    test("biomass source = width", restored_root.children["biomass"].source == "width")
    
    # Verify paper assignments restored
    test("Root has 3 papers", len(restored_root.papers) == 3)
    test("hydrogen child has 1 paper", len(restored_root.children["hydrogen"].papers) == 1)
    test("biomass child has 1 paper", len(restored_root.children["biomass"].papers) == 1)

finally:
    # Clean up
    shutil.rmtree(test_dir, ignore_errors=True)


###############################################################################
# TEST 5: expansion.py - cluster_topics initialized (no UnboundLocalError)
###############################################################################
print("\n===== TEST 5: expansion.py - variable initialization =====")
import expansion
import inspect

width_source = inspect.getsource(expansion.expandNodeWidth)
depth_source = inspect.getsource(expansion.expandNodeDepth)

test("width: cluster_topics = None before loop", "cluster_topics = None" in width_source)
test("width: cluster_outputs = None before loop", "cluster_outputs = None" in width_source)
test("depth: cluster_topics = None before loop", "cluster_topics = None" in depth_source)
test("depth: cluster_outputs = None before loop", "cluster_outputs = None" in depth_source)


###############################################################################
# SUMMARY
###############################################################################
print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
if failed == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"WARNING: {failed} test(s) failed!")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
