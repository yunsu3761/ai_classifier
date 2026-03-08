"""
Classification orchestration service.
Wraps existing main2.py logic for LLM-based taxonomy classification.
"""
import os
import sys
import json
import uuid
import threading
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ..core.config import DATASETS_DIR, SAVE_OUTPUT_DIR, OPENAI_API_KEY, OPENAI_MODEL
from ..core.events import get_tracker, ProgressTracker
from ..models.schemas import ClassifyRequest, RunStatus


def _build_args(request: ClassifyRequest, data_dir: str) -> argparse.Namespace:
    """Convert ClassifyRequest into argparse.Namespace compatible with main2.py."""
    args = argparse.Namespace(
        llm="gpt",
        topic=request.topic,
        dataset=request.dataset_folder,
        data_dir=data_dir,
        max_depth=request.max_depth,
        max_density=request.max_density,
        init_levels=request.init_levels,
        test_samples=request.test_samples if request.test_samples > 0 else None,
        dimensions=request.selected_dimensions,
        resume=request.resume,
        client={},
    )
    return args


def _run_classification(run_id: str, request: ClassifyRequest):
    """Run classification in a background thread."""
    tracker = get_tracker(run_id)
    tracker.update(status="running", current_step="Initializing")

    try:
        # Import existing modules
        from model_definitions import initializeLLM, create_openai_client
        from main2 import construct_dataset, initialize_DAG, step4_parallel

        # Set API key
        api_key = request.api_key or OPENAI_API_KEY
        model = request.model or OPENAI_MODEL
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_MODEL"] = model

        # Build args
        data_dir = str(DATASETS_DIR / request.dataset_folder.lower().replace(" ", "_"))
        args = _build_args(request, data_dir)

        # Initialize LLM
        tracker.update(current_step="Initializing LLM", progress_pct=5.0)
        tracker.add_log(f"Model: {model}")
        args = initializeLLM(args)

        # Load dataset
        tracker.update(current_step="Loading dataset", progress_pct=10.0)
        tracker.add_log("Loading papers from internal.txt...")
        internal_collection, total_count = construct_dataset(args)
        tracker.add_log(f"Loaded {total_count} documents")

        if total_count == 0:
            tracker.update(
                status="failed",
                error="No documents found. Please upload data first.",
            )
            return

        # Initialize taxonomy DAG
        tracker.update(current_step="Initializing taxonomy", progress_pct=20.0)
        tracker.add_log("Building taxonomy DAG from initial_taxo files...")

        # Check which initial_taxo files exist
        available_dims = []
        for dim in args.dimensions:
            txt_path = os.path.join(data_dir, f"initial_taxo_{dim}.txt")
            if os.path.exists(txt_path):
                available_dims.append(dim)
                tracker.add_log(f"  Found: initial_taxo_{dim}.txt")
            else:
                tracker.add_log(f"  Missing: initial_taxo_{dim}.txt (skipping)")

        if not available_dims:
            tracker.update(
                status="failed",
                error="No initial taxonomy files found. Generate them first.",
            )
            return

        args.dimensions = available_dims
        roots, id2node, label2node = initialize_DAG(args, use_txt=True)
        tracker.add_log(f"DAG initialized with {len(id2node)} nodes across {len(roots)} dimensions")

        # Assign papers to root nodes
        tracker.update(current_step="Type classification", progress_pct=30.0)
        tracker.add_log("Classifying papers by type (dimension)...")

        # Type classification using existing prompts
        from prompts import (
            generate_type_cls_system_instruction,
            type_cls_main_prompt,
            dimension_definitions,
        )
        from model_definitions import constructPrompt, promptLLM
        from utils import clean_json_string

        # Build dimension_definitions from loaded config
        dim_defs = {}
        for dim in args.dimensions:
            if dim in dimension_definitions:
                dim_defs[dim] = dimension_definitions[dim]
            else:
                dim_defs[dim] = f"Technology dimension: {dim}"

        type_cls_instruction = generate_type_cls_system_instruction(dim_defs, args.topic)

        type_prompts = []
        paper_list = list(internal_collection.values())
        for paper in paper_list:
            prompt = constructPrompt(
                args,
                type_cls_instruction,
                type_cls_main_prompt(paper, dim_defs, args.topic),
            )
            type_prompts.append(prompt)

        tracker.add_log(f"Running type classification for {len(type_prompts)} papers...")
        type_outputs = promptLLM(args, type_prompts, max_new_tokens=3000)

        # Parse type classification results
        for paper, output in zip(paper_list, type_outputs):
            try:
                result = json.loads(clean_json_string(output)) if "```" in output else json.loads(output.strip())
                for dim in args.dimensions:
                    # Check various key formats
                    dim_val = result.get(dim, result.get(dim.lower(), False))
                    if dim_val is True or str(dim_val).lower() == "true":
                        if dim in roots:
                            roots[dim].papers[paper.id] = paper
            except Exception as e:
                tracker.add_log(f"Warning: Failed to parse type cls for paper {paper.id}: {e}")

        # Log paper distribution
        for dim, root in roots.items():
            tracker.add_log(f"  {dim}: {len(root.papers)} papers")

        # Step 4: Expansion (parallel)
        tracker.update(current_step="Taxonomy expansion (BFS)", progress_pct=40.0)
        tracker.add_log("Starting taxonomy expansion...")

        merged_roots, merged_id2node, merged_label2node = step4_parallel(
            args, roots, id2node, label2node, internal_collection
        )

        tracker.update(current_step="Saving results", progress_pct=90.0)

        # Save results
        results_dir = Path(data_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

        for dim, root in merged_roots.items():
            output_dict = root.display()
            if output_dict:
                output_path = results_dir / f"final_taxo_{dim}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output_dict, f, ensure_ascii=False, indent=2)
                tracker.add_log(f"Saved: final_taxo_{dim}.json")

        # Save run metadata
        run_meta = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "parameters": {
                "model": model,
                "topic": request.topic,
                "max_depth": request.max_depth,
                "max_density": request.max_density,
                "test_samples": request.test_samples,
                "dimensions": args.dimensions,
                "dataset_folder": request.dataset_folder,
            },
            "total_documents": total_count,
            "total_nodes": len(merged_id2node),
        }
        meta_path = results_dir / f"run_{run_id}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(run_meta, f, ensure_ascii=False, indent=2)

        tracker.update(
            status="completed",
            progress_pct=100.0,
            current_step="Done",
        )
        tracker.add_log(f"Classification complete! {len(merged_id2node)} nodes in taxonomy.")

    except Exception as e:
        import traceback
        tracker.update(
            status="failed",
            error=str(e),
        )
        tracker.add_log(f"ERROR: {str(e)}")
        tracker.add_log(traceback.format_exc())


def start_classification(request: ClassifyRequest) -> str:
    """Start a classification run in the background. Returns run_id."""
    run_id = str(uuid.uuid4())[:8]
    thread = threading.Thread(
        target=_run_classification,
        args=(run_id, request),
        daemon=True,
    )
    thread.start()
    return run_id


# Track active runs
_active_runs: Dict[str, threading.Thread] = {}
