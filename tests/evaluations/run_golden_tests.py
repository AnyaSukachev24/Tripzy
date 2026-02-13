"""
Golden dataset evaluation runner for Tripzy.
Runs all test cases from golden_dataset.json and evaluates plan quality.
"""
import sys
import os
import json
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.graph import graph
from langchain_core.messages import HumanMessage


def load_golden_dataset() -> List[Dict[str, Any]]:
    """Load the golden dataset from JSON file"""
    dataset_path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
    with open(dataset_path, 'r') as f:
        return json.load(f)


def evaluate_duration_accuracy(plan: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate if the plan has the correct number of days"""
    if not plan or "itinerary" not in plan:
        return {"passed": False, "score": 0.0, "reason": "No itinerary in plan"}
    
    actual_days = len(plan["itinerary"])
    expected_days = expected["duration_days"]
    
    if actual_days == expected_days:
        return {"passed": True, "score": 1.0, "actual": actual_days, "expected": expected_days}
    else:
        return {
            "passed": False,
            "score": 0.0,
            "reason": f"Expected {expected_days} days, got {actual_days}",
            "actual": actual_days,
            "expected": expected_days
        }


def evaluate_destination_match(plan: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate if the destination matches"""
    if not plan or "destination" not in plan:
        return {"passed": False, "score": 0.0, "reason": "No destination in plan"}
    
    actual_dest = plan["destination"].lower()
    expected_dest = expected["destination"].lower()
    
    if expected_dest in actual_dest:
        return {"passed": True, "score": 1.0, "actual": plan["destination"]}
    else:
        return {
            "passed": False,
            "score": 0.0,
            "reason": f"Expected '{expected_dest}', got '{actual_dest}'",
            "actual": plan["destination"],
            "expected": expected["destination"]
        }


def evaluate_budget_utilization(plan: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate if budget utilization is within expected range"""
    if not plan or "budget_estimate" not in plan:
        return {"passed": False, "score": 0.0, "reason": "No budget estimate in plan"}
    
    actual_cost = plan["budget_estimate"]
    budget_limit = expected["budget_limit"]
    utilization = actual_cost / budget_limit
    
    min_util = expected.get("min_budget_utilization", 0.75)
    max_util = expected.get("max_budget_utilization", 1.0)
    
    if min_util <= utilization <= max_util:
        return {
            "passed": True,
            "score": 1.0,
            "utilization": utilization,
            "actual_cost": actual_cost,
            "budget_limit": budget_limit
        }
    else:
        return {
            "passed": False,
            "score": max(0, 1 - abs(utilization - 0.9)),  # Partial score
            "reason": f"Utilization {utilization:.1%} outside range [{min_util:.1%}, {max_util:.1%}]",
            "utilization": utilization,
            "actual_cost": actual_cost,
            "budget_limit": budget_limit
        }


def run_test_case(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single test case and evaluate results"""
    print(f"\n{'='*80}")
    print(f"Test Case: {test_case['id']}")
    print(f"Description: {test_case['description']}")
    print(f"{'='*80}")
    print(f"Query: {test_case['user_query']}")
    
    initial_state = {
        "messages": [HumanMessage(content=test_case["user_query"])],
        "user_query": test_case["user_query"],
        "trip_plan": None,
        "budget": None,
        "next_step": "ProfileLoader",
        "critique_feedback": None,
        "revision_count": 0,
        "steps": []
    }
    
    config = {"configurable": {"thread_id": f"golden-{test_case['id']}"}}
    
    try:
        # Run the graph
        final_state = None
        for state in graph.stream(initial_state, config):
            if "__end__" in state:
                final_state = state["__end__"]
                break
        
        if not final_state:
            return {
                "test_id": test_case["id"],
                "status": "error",
                "error": "No final state received"
            }
        
        trip_plan = final_state.get("trip_plan")
        expected = test_case["expected"]
        
        # Run evaluations
        duration_result = evaluate_duration_accuracy(trip_plan, expected)
        destination_result = evaluate_destination_match(trip_plan, expected)
        budget_result = evaluate_budget_utilization(trip_plan, expected)
        
        # Calculate overall score
        evaluations = [duration_result, destination_result, budget_result]
        overall_score = sum(e["score"] for e in evaluations) / len(evaluations)
        all_passed = all(e["passed"] for e in evaluations)
        
        print(f"\nEvaluations:")
        print(f"  Duration: {'PASS' if duration_result['passed'] else 'FAIL'} - {duration_result}")
        print(f"  Destination: {'PASS' if destination_result['passed'] else 'FAIL'} - {destination_result}")
        print(f"  Budget: {'PASS' if budget_result['passed'] else 'FAIL'} - {budget_result}")
        print(f"  Overall Score: {overall_score:.2%}")
        
        return {
            "test_id": test_case["id"],
            "status": "completed",
            "passed": all_passed,
            "overall_score": overall_score,
            "evaluations": {
                "duration": duration_result,
                "destination": destination_result,
                "budget": budget_result
            },
            "trip_plan": trip_plan
        }
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            "test_id": test_case["id"],
            "status": "error",
            "error": str(e)
        }


def generate_report(results: List[Dict[str, Any]]):
    """Generate evaluation report"""
    print("\n" + "="*80)
    print("GOLDEN DATASET EVALUATION REPORT")
    print("="*80)
    
    passed_tests = sum(1 for r in results if r.get("passed", False))
    total_tests = len(results)
    avg_score = sum(r.get("overall_score", 0) for r in results) / total_tests if total_tests > 0 else 0
    
    print(f"\nOverall Results:")
    print(f"  Tests Passed: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
    print(f"  Average Score: {avg_score:.2%}")
    
    print(f"\nDetailed Results:")
    for result in results:
        status_icon = "PASS" if result.get("passed", False) else "FAIL"
        score = result.get("overall_score", 0)
        print(f"  [{status_icon}] {result['test_id']}: {score:.2%}")
    
    # Save report to file
    report_path = os.path.join(os.path.dirname(__file__), "evaluation_report.json")
    with open(report_path, 'w') as f:
        json.dump({
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "pass_rate": passed_tests / total_tests if total_tests > 0 else 0,
                "average_score": avg_score
            },
            "results": results
        }, f, indent=2)
    
    print(f"\nReport saved to: {report_path}")


def main():
    """Main entry point"""
    print("Loading golden dataset...")
    dataset = load_golden_dataset()
    print(f"Loaded {len(dataset)} test cases")
    
    results = []
    for test_case in dataset:
        result = run_test_case(test_case)
        results.append(result)
    
    generate_report(results)


if __name__ == "__main__":
    main()
