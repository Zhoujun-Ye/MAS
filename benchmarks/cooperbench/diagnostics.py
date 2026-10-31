"""Additive evaluation diagnostics; never replace the official verdict."""
import re


VERSION = 'evaluation-diagnostics-v1'
KNOWN_ISSUES = {
    ('openai_tiktoken_task', 0, 9): {
        'id': 'tiktoken-compress-keyword',
        'kind': 'specification_test_mismatch',
        'detail': 'Assignment requests compress; hidden test calls compression.',
    },
    ('dspy_task', 8394, 5): {
        'id': 'dspy-uncompressed-representation',
        'kind': 'specification_test_mismatch',
        'detail': 'Assignment describes header-prefixed pickle including codec 0; test requires an uncompressed live object.',
    },
}


def benchmark_issues(pair):
    return [dict(feature=f, **KNOWN_ISSUES[(pair.repo, pair.task_id, f)])
            for f in pair.features if (pair.repo, pair.task_id, f) in KNOWN_ISSUES]


def diagnose(pair, raw):
    features = []
    for slot, feature in zip(('feature1', 'feature2'), pair.features):
        result = raw.get(slot) or {}
        output = result.get('output') or result.get('test_output') or ''
        output = re.sub(r'\x1b\[[0-9;]*m', '', output)
        # Test phase is an observation, not a claim about who caused the error.
        if result.get('error'):
            kind = 'evaluation_error'
        elif re.search(r'ERROR collecting|errors? during collection', output, re.I):
            kind = 'collection_error'
        elif re.search(r'ERROR at (?:setup|teardown)', output):
            kind = 'fixture_error'
        elif result.get('passed') is True:
            kind = 'passed'
        elif re.search(r'^FAILED\s|^--- FAIL:', output, re.M) or result.get('tests_failed', 0) > 0:
            kind = 'test_failure'
        else:
            kind = 'unresolved'
        features.append(dict(feature=feature, kind=kind,
                             exit_code=result.get('exit_code'),
                             cause='not_determined' if kind != 'passed' else None))
    return dict(version=VERSION, features=features, benchmark_issues=benchmark_issues(pair),
                causal_attribution='not_established')
