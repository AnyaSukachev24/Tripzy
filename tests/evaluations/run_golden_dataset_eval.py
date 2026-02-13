"""
Automated Test Runner for Tripzy Golden Dataset Evaluation
Runs all test cases from golden_dataset.json and generates evaluation reports.
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.evaluations.eval_framework import evaluate_test_case


def load_golden_dataset() -> List[Dict[str, Any]]:
    """Load test cases from golden_dataset.json"""
    dataset_path = Path(__file__).parent / "golden_dataset.json"
    with open(dataset_path, 'r') as f:
        return json.load(f)


def run_agent_on_test_case(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the Tripzy agent on a test case.
    
    Handles both single-turn and multi-turn conversation scenarios.
    Returns the agent's final output including trip plan and conversation history.
    """
    # Import agent graph
    from app.graph import graph
    
    # Initialize configuration for this test run
    config = {"configurable": {"thread_id": test_case.get("id", "test_thread")}}
    
    # Check if this is a multi-turn conversation
    conversation_turns = test_case.get("conversation_turns", [])
    
    if conversation_turns:
        # Multi-turn scenario: simulate conversation
        all_states = []
        for turn_num, turn in enumerate(conversation_turns, 1):
            user_message = turn.get("user", "")
            
            # Invoke graph with this turn's message
            try:
                result = graph.invoke(
                    {"user_query": user_message},
                    config=config
                )
                all_states.append(result)
                
                # Check if we have a final plan or if we  need more turns
                if result.get("trip_plan") and result.get("trip_plan") != {}:
                    break  # Plan generated, stop conversation
                    
            except Exception as e:
                return {
                    "trip_plan": {},
                    "conversation": all_states,
                    "error": f"Turn {turn_num} failed: {str(e)}"
                }
        
        # Return the final state
        final_state = all_states[-1] if all_states else {}
        return {
            "trip_plan": final_state.get("trip_plan", {}),
            "conversation": all_states,
            "error": None
        }
    
    else:
        # Single-turn scenario
        user_query = test_case.get("user_query", "")
        
        try:
            result = graph.invoke(
                {"user_query": user_query},
                config=config
            )
            
            return {
                "trip_plan": result.get("trip_plan", {}),
                "conversation": [result],
                "error": None
            }
            
        except Exception as e:
            return {
                "trip_plan": {},
                "conversation": [],
                "error": str(e)
            }



def run_evaluation_suite(
    output_file: str = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Run evaluation on all golden dataset test cases.
    
    Args:
        output_file: Path to save results JSON (optional, auto-generates timestamped path if None)
        verbose: Print progress and results
        
    Returns:
        Dictionary with aggregate results
    """
    if verbose:
        print("=" * 80)
        print("TRIPZY GOLDEN DATASET EVALUATION")
        print("=" * 80)
        print()
    
    # Auto-generate timestamped output path if not specified
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = Path(__file__).parent.parent.parent / "evaluation-results"
        results_dir.mkdir(parents=True, exist_ok=True)
        output_file = str(results_dir / f"eval_{timestamp}.json")
    
    # Load test cases
    test_cases = load_golden_dataset()
    if verbose:
        print(f"Loaded {len(test_cases)} test cases")
        print()
    
    # --- CACHING LOGIC ---
    import hashlib
    cache_file = Path(__file__).parent / ".eval_cache.json"
    cache = {}
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
        except:
            cache = {}
            
    # Helper to get test hash
    def get_test_hash(test_case):
        # Hash the string representation of the test case to detect changes
        return hashlib.sha256(json.dumps(test_case, sort_keys=True).encode()).hexdigest()

    # Run evaluations
    results = []
    passed_count = 0
    failed_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        test_id = test_case.get("id", f"test_{i}")
        description = test_case.get("description", "No description")
        test_hash = get_test_hash(test_case)
        
        # Check cache
        cached_result = cache.get(test_id)
        if cached_result and cached_result.get("hash") == test_hash and cached_result.get("passed"):
            if verbose:
                print(f"[{i}/{len(test_cases)}] Skipping (Cached Pass): {test_id}")
            results.append(cached_result["data"])
            passed_count += 1
            continue
            
        if verbose:
            print(f"[{i}/{len(test_cases)}] Running: {test_id}")
            print(f"  Description: {description}")
        
        try:
            # Run agent
            agent_output = run_agent_on_test_case(test_case)
            
            # Evaluate
            evaluation = evaluate_test_case(agent_output, test_case)
            
            # Track results
            results.append(evaluation)
            if evaluation["passed"]:
                passed_count += 1
                status = "✓ PASSED"
                # Update cache
                cache[test_id] = {
                    "hash": test_hash,
                    "passed": True,
                    "data": evaluation,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                passed_count += 0 # logic fix
                failed_count += 1
                status = "✗ FAILED"
                # Remove from cache if failed (force re-run next time)
                if test_id in cache:
                    del cache[test_id]
            
            if verbose:
                print(f"  Score: {evaluation['overall_score']:.2f}")
                print(f"  Status: {status}")
                print(f"  Progress: {i}/{len(test_cases)} ({i/len(test_cases)*100:.1f}%)")
                print()
                
            # INCREMENTAL SAVE: Save results and cache after every test
            # This allows monitoring progress even if the script crashes or is long-running
            try:
                # Save cache
                with open(cache_file, 'w') as f:
                    json.dump(cache, f, indent=2)
                
                # Save intermediate results if output_file is set
                if output_file:
                    current_stats = {
                        "timestamp": datetime.now().isoformat(),
                        "total_tests": len(test_cases),
                        "completed": i,
                        "passed": passed_count,
                        "failed": failed_count,
                        "pass_rate": passed_count / i if i > 0 else 0.0,
                        "individual_results": results
                    }
                    output_path = Path(output_file)
                    with open(output_path, 'w') as f:
                        json.dump(current_stats, f, indent=2)
                        
            except Exception as e:
                if verbose:
                    print(f"  [Warning] Incremental save failed: {e}")
                
        except Exception as e:
            if verbose:
                print(f"  ERROR: {str(e)}")
                print()
            results.append({
                "test_id": test_id,
                "test_description": description,
                "error": str(e),
                "overall_score": 0.0,
                "passed": False
            })
            failed_count += 1
    
    # Calculate aggregate statistics
    scores = [r["overall_score"] for r in results if "overall_score" in r]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    pass_rate = passed_count / len(test_cases) if test_cases else 0.0
    
    aggregate_results = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(test_cases),
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": pass_rate,
        "average_score": avg_score,
        "individual_results": results
    }
    
    # Print summary
    if verbose:
        print("=" * 80)
        print("EVALUATION SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {len(test_cases)}")
        print(f"Passed: {passed_count} ({pass_rate*100:.1f}%)")
        print(f"Failed: {failed_count}")
        print(f"Average Score: {avg_score:.2f}")
        print()
        
        # Breakdown by category
        print("RESULTS BY CATEGORY:")
        print()
        
        categories = {
            "vague_": "Vague Request Handling",
            "edge_case_": "Edge Case Detection",
            "extreme_budget_": "Extreme Budget Handling",
            "special_": "Special Requirements",
            "multi_": "Multi-City Planning",
            "attractions_only": "Partial Plan (Attractions)",
            "full_plan": "Full Plan",
            "flights_only": "Partial Plan (Flights)"
        }
        
        for prefix, category_name in categories.items():
            category_results = [r for r in results if r["test_id"].startswith(prefix)]
            if category_results:
                cat_passed = sum(1 for r in category_results if r.get("passed", False))
                cat_scores = [r["overall_score"] for r in category_results if "overall_score" in r]
                cat_avg = sum(cat_scores) / len(cat_scores) if cat_scores else 0.0
                print(f"  {category_name}:")
                print(f"    Tests: {len(category_results)}")
                print(f"    Passed: {cat_passed}/{len(category_results)}")
                print(f"    Avg Score: {cat_avg:.2f}")
                print()
    
    # Save results
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(aggregate_results, f, indent=2)
        if verbose:
            print(f"Results saved to: {output_path}")
            print()
    
    return aggregate_results


def print_detailed_analysis(results_file: str):
    """Print detailed analysis from a results file"""
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    print("=" * 80)
    print("DETAILED EVALUATION ANALYSIS")
    print("=" * 80)
    print()
    
    for result in results["individual_results"]:
        test_id = result["test_id"]
        score = result.get("overall_score", 0.0)
        passed = result.get("passed", False)
        
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_id}: {score:.2f} - {status}")
        
        if "evaluations" in result:
            for eval_name, eval_data in result["evaluations"].items():
                eval_score = eval_data.get("score", 0.0)
                reasoning = eval_data.get("reasoning", "No reasoning")
                print(f"  - {eval_name}: {eval_score:.2f}")
                print(f"    Reasoning: {reasoning}")
        
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        
        print()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Tripzy Golden Dataset Evaluation")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file for results (default: auto-generated in evaluation-results/ with timestamp)"
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress verbose output"
    )
    parser.add_argument(
        "--analyze",
        "-a",
        type=str,
        help="Analyze existing results file instead of running tests"
    )
    
    args = parser.parse_args()
    
    if args.analyze:
        print_detailed_analysis(args.analyze)
    else:
        run_evaluation_suite(
            output_file=args.output,
            verbose=not args.quiet
        )
