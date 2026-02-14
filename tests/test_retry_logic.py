"""
Test to verify retry logic is working correctly.
Creates a mock that fails twice then succeeds to test exponential backoff.
"""
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_retry_logic():
    """Test that retry logic works with exponential backoff"""
    print("="*80)
    print("TEST: Retry Logic with Exponential Backoff")
    print("="*80)
    
    from app.graph import safe_llm_invoke
    
    # Create a mock chain that fails twice then succeeds
    mock_chain = MagicMock()
    call_count = [0]
    
    def side_effect(input_data):
        call_count[0] += 1
        print(f"\n[ATTEMPT {call_count[0]}] LLM call with input: {list(input_data.keys())}")
        
        if call_count[0] < 3:
            print(f"  ❌ Simulating failure (attempt {call_count[0]}/3)")
            raise Exception("Simulated API error")
        else:
            print(f"  ✅ Success on attempt {call_count[0]}")
            return {"result": "success", "data": "mock response"}
    
    mock_chain.invoke = MagicMock(side_effect=side_effect)
    
    try:
        # This should retry 2 times then succeed on the 3rd attempt
        result = safe_llm_invoke(mock_chain, {"query": "test query"})
        
        print(f"\n[RESULT] Final result: {result}")
        print(f"[RESULT] Total attempts: {call_count[0]}")
        
        if call_count[0] == 3 and result["result"] == "success":
            print("\n✅ PASS: Retry logic worked! Failed 2 times, succeeded on 3rd attempt")
            return True
        else:
            print(f"\n❌ FAIL: Expected 3 attempts, got {call_count[0]}")
            return False
            
    except Exception as e:
        print(f"\n❌ FAIL: Retry logic failed with error: {e}")
        print(f"   Attempts made: {call_count[0]}")
        return False

def test_max_retries_exceeded():
    """Test that retry gives up after max attempts"""
    print("\n" + "="*80)
    print("TEST: Max Retries Exceeded")
    print("="*80)
    
    from app.graph import safe_llm_invoke
    
    # Create a mock that always fails
    mock_chain = MagicMock()
    call_count = [0]
    
    def always_fail(input_data):
        call_count[0] += 1
        print(f"\n[ATTEMPT {call_count[0]}] LLM call (will fail)")
        raise Exception("Persistent API error")
    
    mock_chain.invoke = MagicMock(side_effect=always_fail)
    
    try:
        result = safe_llm_invoke(mock_chain, {" query": "test"})
        print(f"\n❌ FAIL: Should have raised an exception after 3 attempts")
        return False
    except Exception as e:
        print(f"\n[RESULT] Failed after {call_count[0]} attempts (expected 3)")
        
        if call_count[0] == 3:
            print(f"✅ PASS: Correctly gave up after 3 attempts")
            return True
        else:
            print(f"❌ FAIL: Expected 3 attempts, got {call_count[0]}")
            return False

if __name__ == "__main__":
    print("\nRUNNING RETRY LOGIC TESTS\n")
    
    test1 = test_retry_logic()
    test2 = test_max_retries_exceeded()
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Test 1 (Retry Success): {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"Test 2 (Max Retries): {'✅ PASS' if test2 else '❌ FAIL'}")
    
    if test1 and test2:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)
