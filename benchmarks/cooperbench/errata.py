"""Explicit post-study assignment variant; official inputs remain the default."""
from hashlib import sha256

PROFILES = ('official', 'clarified-v1')
CLARIFICATIONS = {
    ('openai_tiktoken_task', 0, 9):
        'Public API clarification: encode must accept compression=True/False. '
        'The compress keyword described above must also remain supported as an alias '
        'with the same adjacent-token deduplication behavior.',
    ('dspy_task', 8394, 5):
        'Storage clarification: when compress=None, store the original Python object '
        'in disk_cache, preserving its existing default behavior. Encode header-prefixed '
        'pickle bytes for gzip/zlib writes. Continue decoding existing header-prefixed '
        'entries, including codec 0, and support legacy entries. The unconditional '
        'write-header description above is superseded for compress=None.',
}


def clarify(text, repo, task, feature, profile):
    if profile not in PROFILES:
        raise ValueError('Unknown benchmark profile: ' + profile)
    note = CLARIFICATIONS.get((repo, task, feature))
    if profile == 'official' or not note:
        return text
    return text + '\n\n## Clarified-v1 Erratum\n\n' + note + '\n'


def input_receipt(inputs, profile):
    if profile not in PROFILES:
        raise ValueError('Unknown benchmark profile: ' + profile)
    return dict(profile=profile, official_assignments=profile == 'official',
                input_sha256={role: sha256(text.encode()).hexdigest() for role, text in inputs.items()})
