"""Keep active documentation navigable after source and protocol retirement."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_relative_markdown_links_resolve():
    paths = [ROOT / 'README.md', *ROOT.joinpath('docs').rglob('*.md')]
    paths += list(ROOT.joinpath('harness').rglob('README.md'))
    paths += list(ROOT.joinpath('scripts').rglob('README.md'))
    for path in paths:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            target = target.split('#', 1)[0]
            if not target or re.match(r'[a-z]+:|/', target):
                continue
            assert (path.parent / target).exists(), (path.relative_to(ROOT), target)


def test_current_timeout_document_names_the_owning_module():
    text = (ROOT / 'docs/timeout-policy.md').read_text()
    assert '`benchmarks/policy.py`' in text
    assert 'scripts/common/timeouts.py' not in text


def test_layout_entries_are_unique():
    text = (ROOT / 'README.md').read_text().split('## Layout', 1)[1].split('## ', 1)[0]
    entries = re.findall(r'^- `([^`]+)`:', text, flags=re.MULTILINE)
    assert len(entries) == len(set(entries))


def test_evidence_readme_describes_current_not_retired_composition():
    text = (ROOT / 'harness/evidence_mas/README.md').read_text()
    assert 'decision-v3' in text
    assert 'exact existing Native (N) prompt' in text
    assert 'Both modes prepend the exact frozen Structured lead prompt' not in text
