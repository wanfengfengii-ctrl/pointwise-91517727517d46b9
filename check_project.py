"""Run this project's full unittest suite from the repository root."""
import sys
import traceback
import unittest


def run_suite() -> int:
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    if suite.countTestCases():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print('No tests discovered in tests/', file=sys.stderr)
        result = unittest.TestResult()
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    successful = result.testsRun > 0 and result.wasSuccessful()
    print(f'TEST SUMMARY total={result.testsRun} failures={len(result.failures)} '
          f'errors={len(result.errors)} skipped={len(result.skipped)} '
          f'expected_failures={len(result.expectedFailures)} '
          f'unexpected_successes={len(result.unexpectedSuccesses)} '
          f'result={"PASS" if successful else "FAIL"}')
    return 0 if successful else 1


def run_examples() -> int:
    import anchor_examples
    for label, check in (
        ('v1', anchor_examples.v1_examples),
        ('review', anchor_examples.review_examples),
    ):
        try:
            check()
        except Exception:
            print(f'EXAMPLE CHECK FAILED: anchor_examples {label}', file=sys.stderr)
            traceback.print_exc()
            return 1
    print('EXAMPLE SUMMARY cases=v1,review result=PASS')
    return 0


def main():
    status = run_suite()
    if status:
        return status
    return run_examples()


if __name__ == '__main__':
    raise SystemExit(main())
