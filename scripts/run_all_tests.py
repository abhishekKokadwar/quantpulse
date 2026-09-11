import unittest
import sys
import os
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def run_tests():
    test_dir = os.path.join(PROJECT_ROOT, "tests")

    test_files = sorted([f for f in os.listdir(test_dir) if f.startswith("test_") and f.endswith(".py")])
    
    results = {}
    total_start = time.time()
    
    for tf in test_files:
        mod_name = f"tests.{tf[:-3]}"
        print(f"\n{'='*20} Running {tf} {'='*20}")
        start = time.time()
        suite = unittest.defaultTestLoader.loadTestsFromName(mod_name)
        runner = unittest.TextTestRunner(verbosity=2)
        res = runner.run(suite)
        elapsed = time.time() - start
        results[tf] = {
            "tests": res.testsRun,
            "errors": len(res.errors),
            "failures": len(res.failures),
            "skipped": len(res.skipped),
            "time": elapsed,
            "success": res.wasSuccessful()
        }
    
    print("\n" + "="*60)
    print("TEST EXECUTION SUMMARY:")
    print("="*60)
    all_ok = True
    for tf, r in results.items():
        status = "PASSED" if r["success"] else "FAILED"
        if not r["success"]:
            all_ok = False
        print(f"{tf:<25} | {status:<8} | Ran: {r['tests']:2d} | Failed: {r['failures']:2d} | Errs: {r['errors']:2d} | {r['time']:.2f}s")
    
    total_elapsed = time.time() - total_start
    print(f"\nTotal Elapsed Time: {total_elapsed:.2f}s")
    if not all_ok:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
