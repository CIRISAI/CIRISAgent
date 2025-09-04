#!/usr/bin/env python3
"""
Test script for the enhanced pause/step QA functionality.
"""

import subprocess
import sys


def run_pause_step_tests():
    """Run the pause/step QA tests."""
    print("🧪 Testing Enhanced Pause/Step QA Functionality")
    print("=" * 60)
    
    # Run the QA runner with pause_step module
    cmd = [
        sys.executable, 
        "-m", 
        "tools.qa_runner", 
        "pause_step",
        "--verbose",
        "--json",
        "--report-dir", 
        "qa_reports"
    ]
    
    print("Running command:")
    print(" ".join(cmd))
    print()
    
    try:
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)
        
        print(f"\nReturn code: {result.returncode}")
        
        if result.returncode == 0:
            print("\n✅ Pause/Step QA tests completed successfully!")
        else:
            print("\n❌ Pause/Step QA tests failed!")
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("❌ Tests timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


if __name__ == "__main__":
    success = run_pause_step_tests()
    sys.exit(0 if success else 1)