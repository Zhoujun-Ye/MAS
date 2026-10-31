import copy

import pytest

from scripts.cooperbench.native_check import baseline_failure_evidence


OUTPUT = '''JestAssertionError: expect(received).resolves.toBeUndefined()
Received promise rejected instead of resolved
Rejected to value: [TypeError: onValid is not a function]
    at expect (/workspace/repo/node_modules/expect/build/index.js:105:15)
    at expect (/workspace/repo/src/__tests__/useForm/handleSubmit.test.tsx:603:13)
'''


def test_unhandled_jest_assertion_has_explicit_evidence_without_fabricating_counts():
    result = dict(passed=False, tests_passed=0, tests_failed=0, exit_code=1, output=OUTPUT)
    before = copy.deepcopy(result)
    evidence = baseline_failure_evidence(result)
    assert evidence['kind'] == 'unhandled-jest-expectation'
    assert evidence['test_source'].endswith('handleSubmit.test.tsx:603:13')
    assert result == before


@pytest.mark.parametrize('change', [
    dict(output='TypeError: onValid is not a function'),
    dict(output=OUTPUT.replace('JestAssertionError:', 'TypeError:')),
    dict(output=OUTPUT.replace('/src/__tests__/useForm/handleSubmit.test.tsx', '/node_modules/expect/build/index.js')),
    dict(output=OUTPUT.replace('Received promise rejected instead of resolved', '')),
    dict(exit_code=124), dict(exit_code=137), dict(passed=True), dict(error='execution timeout'),
])
def test_crashes_timeouts_and_non_test_exceptions_do_not_admit(change):
    assert baseline_failure_evidence(dict(passed=False, tests_failed=0, exit_code=1, output=OUTPUT) | change) is None
