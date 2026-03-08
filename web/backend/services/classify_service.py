"""
Classification orchestration service with multi-user concurrency control.
"""
import os
import sys
import json
import uuid
import time
import threading
import argparse
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ..core.config import (
    DATASETS_DIR, OPENAI_API_KEY, OPENAI_MODEL,
    EST_SECONDS_PER_DOC_TYPE_CLS, EST_SECONDS_PER_DOC_EXPANSION,
)
from ..core.events import (
    create_tracker, get_tracker, try_acquire_run_slot, release_run_slot,
    get_queue_info, ProgressTracker,
)
from ..models.schemas import ClassifyRequest, RunStatus


def estimate_time(doc_count: int, dim_count: int, max_depth: int) -> float:
    """Estimate total seconds for classification. Returns seconds."""
    type_cls_time = doc_count * EST_SECONDS_PER_DOC_TYPE_CLS
    avg_papers_per_dim = doc_count * 0.4  # ~40% match per dim
    expansion_time = avg_papers_per_dim * dim_count * max_depth * EST_SECONDS_PER_DOC_EXPANSION * 0.1
    return type_cls_time + expansion_time


def _build_args(request: ClassifyRequest, data_dir: str) -> argparse.Namespace:
    return argparse.Namespace(
        llm='gpt',
        topic=request.topic,
        dataset=request.dataset_folder,
        data_dir=data_dir,
        max_depth=request.max_depth,
        max_density=request.max_density,
        init_levels=request.init_levels,
        test_samples=request.test_samples if request.test_samples > 0 else None,
        dimensions=list(request.selected_dimensions),
        resume=request.resume,
        client={},
    )


def _run_classification(run_id: str, request: ClassifyRequest, user_id: str):
    """Run classification in a background thread with cancel support."""
    tracker = get_tracker(run_id)
    start_time = time.time()

    try:
        from model_definitions import initializeLLM, create_openai_client
        from main2 import construct_dataset, initialize_DAG, step4_parallel

        api_key = request.api_key or OPENAI_API_KEY
        model = request.model or OPENAI_MODEL
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_MODEL"] = model
        os.environ["OPENAI_TEMPERATURE"] = str(request.temperature)
        os.environ["OPENAI_TOP_P"] = str(request.top_p)

        # Use user-scoped data directory
        data_dir = str(DATASETS_DIR / user_id / request.dataset_folder.lower().replace(" ", "_"))
        args = _build_args(request, data_dir)

        # Check cancel before each major step
        def check_cancel():
            if tracker.is_cancelled:
                raise InterruptedError("Classification cancelled by user")
            tracker.elapsed_seconds = time.time() - start_time

        # Step 1: Init LLM
        tracker.update(status="running", current_step="Initializing LLM", progress_pct=5.0)
        tracker.add_log(f"Model: {model}")
        tracker.add_log(f"Temperature: {request.temperature}, Top-P: {request.top_p}")
        if request.test_samples > 0:
            tracker.add_log(f"Test Samples: {request.test_samples}개 (테스트 모드)")
        else:
            tracker.add_log(f"Test Samples: 전체 문서")
        check_cancel()
        args = initializeLLM(args)

        # Step 2: Load dataset
        tracker.update(current_step="Loading dataset", progress_pct=10.0)
        check_cancel()
        internal_collection, total_count = construct_dataset(args)
        tracker.add_log(f"Loaded {total_count} documents")

        if total_count == 0:
            tracker.update(status="failed", error="No documents found. Upload and convert data first.")
            return

        # Estimate time
        est = estimate_time(total_count, len(args.dimensions), args.max_depth)
        tracker.estimated_seconds = est
        tracker.add_log(f"Estimated time: {int(est // 60)}m {int(est % 60)}s")

        # Step 3: Init DAG
        tracker.update(current_step="Initializing taxonomy", progress_pct=15.0)
        check_cancel()

        available_dims = []
        for dim in args.dimensions:
            txt_path = os.path.join(data_dir, f"initial_taxo_{dim}.txt")
            if os.path.exists(txt_path):
                available_dims.append(dim)
                tracker.add_log(f"  Found: initial_taxo_{dim}.txt")
            else:
                tracker.add_log(f"  Missing: initial_taxo_{dim}.txt (skipping)")

        if not available_dims:
            tracker.update(status="failed", error="No initial taxonomy files found.")
            return

        args.dimensions = available_dims
        roots, id2node, label2node = initialize_DAG(args, use_txt=True)
        tracker.add_log(f"DAG: {len(id2node)} nodes, {len(roots)} dimensions")

        # Step 4: Type classification
        tracker.update(current_step="Type classification", progress_pct=25.0)
        check_cancel()

        from prompts import generate_type_cls_system_instruction, type_cls_main_prompt, dimension_definitions
        from model_definitions import constructPrompt, promptLLM
        from utils import clean_json_string

        dim_defs = {}
        for dim in args.dimensions:
            if dim in dimension_definitions:
                dim_defs[dim] = dimension_definitions[dim]
            else:
                dim_defs[dim] = f"Technology dimension: {dim}"

        type_cls_instruction = generate_type_cls_system_instruction(dim_defs, args.topic)
        paper_list = list(internal_collection.values())

        # Batch with cancel checks
        type_prompts = []
        for paper in paper_list:
            type_prompts.append(constructPrompt(args, type_cls_instruction, type_cls_main_prompt(paper, dim_defs, args.topic)))

        tracker.add_log(f"Classifying {len(type_prompts)} papers...")
        check_cancel()

        # Run LLM with periodic cancel checks (process in batches of 500 to allow full parallel saturation)
        batch_size = 500
        type_outputs = []
        for i in range(0, len(type_prompts), batch_size):
            check_cancel()
            batch = type_prompts[i:i + batch_size]
            batch_outputs = promptLLM(
                args, 
                batch, 
                max_new_tokens=3000, 
                cancel_event=tracker._cancel_event
            )
            type_outputs.extend(batch_outputs)

            pct = 25.0 + (i + len(batch)) / len(type_prompts) * 40.0
            tracker.update(
                progress_pct=min(pct, 65.0),
                current_step=f"Type classification ({i + len(batch)}/{len(type_prompts)})",
            )
            tracker.elapsed_seconds = time.time() - start_time

        # Parse results
        for paper, output in zip(paper_list, type_outputs):
            try:
                result = json.loads(clean_json_string(output) if "```" in output else output.strip())
                for dim in args.dimensions:
                    dim_val = result.get(dim, result.get(dim.lower(), False))
                    if dim_val is True or str(dim_val).lower() == 'true':
                        if dim in roots:
                            roots[dim].papers[paper.id] = paper
            except Exception as e:
                tracker.add_log(f"Warning: parse error for {paper.id}: {str(e)[:100]}")

        for dim, root in roots.items():
            tracker.add_log(f"  {dim}: {len(root.papers)} papers")

        # Step 5: Expansion
        tracker.update(current_step="Taxonomy expansion (BFS)", progress_pct=70.0)
        check_cancel()

        merged_roots, merged_id2node, merged_label2node = step4_parallel(
            args, roots, id2node, label2node, internal_collection
        )

        # Step 6: Save
        tracker.update(current_step="Saving results", progress_pct=90.0)
        check_cancel()

        results_dir = Path(data_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

        for dim, root in merged_roots.items():
            output_dict = root.display()
            if output_dict:
                out_path = results_dir / f"final_taxo_{dim}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(output_dict, f, ensure_ascii=False, indent=2)
                tracker.add_log(f"Saved: final_taxo_{dim}.json")
                
                # Save as TXT
                from .result_service import _write_node_to_txt
                txt_path = results_dir / f"final_taxo_{dim}.txt"
                lines = []
                _write_node_to_txt(output_dict, dim, lines, 0)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                tracker.add_log(f"Saved: final_taxo_{dim}.txt")

        run_meta = {
            "run_id": run_id,
            "user_id": user_id,
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
            "elapsed_seconds": time.time() - start_time,
        }
        with open(results_dir / f"run_{run_id}.json", "w", encoding="utf-8") as f:
            json.dump(run_meta, f, ensure_ascii=False, indent=2)

        tracker.update(status="completed", progress_pct=100.0, current_step="Done")
        tracker.elapsed_seconds = time.time() - start_time
        tracker.add_log(f"Complete! {len(merged_id2node)} nodes. Elapsed: {int(tracker.elapsed_seconds)}s")

    except InterruptedError:
        tracker.add_log("Classification cancelled by user.")
    except Exception as e:
        import traceback
        tracker.update(status="failed", error=str(e))
        tracker.add_log(f"ERROR: {str(e)}")
        tracker.add_log(traceback.format_exc()[-500:])
    finally:
        tracker.elapsed_seconds = time.time() - start_time
        release_run_slot(run_id)


def start_classification(request: ClassifyRequest, user_id: str = "default") -> dict:
    """Start a classification run. Returns {run_id, status, message} or error."""
    run_id = str(uuid.uuid4())[:8]

    # Check concurrency
    if not try_acquire_run_slot(run_id, user_id):
        info = get_queue_info()
        return {
            "run_id": None,
            "status": "rejected",
            "message": f"Server is at capacity ({info['active_runs']}/{info['max_concurrent']} runs active). Please wait and try again.",
            "queue_info": info,
        }

    # Count total docs
    data_dir = DATASETS_DIR / user_id / request.dataset_folder.lower().replace(" ", "_")
    internal_path = data_dir / "internal.txt"
    total_docs = 0
    if internal_path.exists():
        total_docs = sum(1 for line in open(internal_path, "r", encoding="utf-8") if line.strip())

    # Apply test_samples limit for estimation
    effective_docs = total_docs
    if request.test_samples > 0 and request.test_samples < total_docs:
        effective_docs = request.test_samples

    est = estimate_time(effective_docs, len(request.selected_dimensions), request.max_depth)

    tracker = create_tracker(run_id, user_id)
    tracker.estimated_seconds = est
    tracker.update(status="pending", current_step="Queued")

    thread = threading.Thread(
        target=_run_classification,
        args=(run_id, request, user_id),
        daemon=True,
    )
    thread.start()

    return {
        "run_id": run_id,
        "status": "running",
        "message": f"Classification started. Estimated time: {int(est // 60)}m {int(est % 60)}s ({effective_docs} docs)",
        "estimated_seconds": est,
        "total_documents": total_docs,
        "effective_documents": effective_docs,
        "test_samples": request.test_samples,
        "queue_info": get_queue_info(),
    }

