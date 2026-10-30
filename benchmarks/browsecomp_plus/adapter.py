"""Read-only BM25 tools, public-task boundary and conservative answer checks."""
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import unicodedata

from harness.agent import Observation, Tool

ROOT = Path(__file__).resolve().parent
INDEX = Path('/home/zhoujunye/agent-team/.cache/browsecomp-plus/bm25')
JAVA = Path('/home/zhoujunye/agent-team/.runtime/java21')
SOURCE_SHA = '44b80cc9fcd9dd5a44aa09292c2165364b0c0e9df26c9cd6c11846165a0916b7'
FORMS = ('summary', 'structured', 'document_retrieval', 'adaptive')
LIMITS = dict(tool_budget=50, max_calls=64, max_messages=28, max_reads=12,
              max_input_chars=800_000, finalization_reserve=2)
OUTPUT = '''Return only one JSON object with answer (a concise string, or "unknown"),
reasoning (a string explaining how the clues fit), and citations (a list of
objects containing docid, claim and quote, all strings). Quotes must be exact
excerpts you actually observed. Do not fabricate evidence or claim an unverified
clue was verified. Give the best supported answer; no more tools after the
reserved finalization notice.'''
CONTRACT = '''Use only the fixed benchmark corpus through the supplied tools.
All agents receive the complete question. The stored corpus, not the live web,
is the source of evidence. Search returns explicitly bounded leading excerpts;
use open_document for subsequent character windows, or find_in_document to
locate a literal phrase. Missing search hits do not establish nonexistence.
Communicate exact identifiers, dates, qualifiers, unresolved contradictions and
source docids. Distinguish a candidate from a verified answer. Do not repeatedly
confirm unchanged findings; finish your assignment when its useful work is done.'''
TOOL_CAPABILITIES = {'search': 'search', 'open_document': 'read', 'find_in_document': 'read'}


def public_task(row):
    return row['query'] + '\n\n' + CONTRACT + '\n\n' + OUTPUT


def task_rows(path=ROOT / 'assets/tasks.jsonl'):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA:
        raise ValueError('Official test data differs from the verified pinned copy')
    rows = [json.loads(line) for line in data.splitlines() if line.strip()]
    if len(rows) != 830 or len({str(r['query_id']) for r in rows}) != 830:
        raise ValueError('Expected 830 unique official test queries')
    return rows


def select_sample(rows, excluded):
    candidates = [r for r in rows if 150 <= len(r['query']) <= 1600 and str(r['query_id']) not in excluded]
    return sorted(candidates, key=lambda r: hashlib.sha256(
        ('bcp-team-20261029:' + str(r['query_id'])).encode()).hexdigest())[:6]


def valid_final(text):
    try:
        value = json.loads(text)
        return (isinstance(value, dict) and set(value) == {'answer', 'reasoning', 'citations'}
                and isinstance(value['answer'], str) and bool(value['answer'].strip())
                and isinstance(value['reasoning'], str) and isinstance(value['citations'], list)
                and all(isinstance(c, dict) and set(c) == {'docid', 'claim', 'quote'}
                        and all(isinstance(v, str) for v in c.values()) for c in value['citations']))
    except (ValueError, TypeError):
        return False


def exact_grade(answer, reference):
    def normalize(value):
        return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())
    match = normalize(answer) == normalize(reference)
    return dict(status='graded' if match else 'needs_review', correct=True if match else None,
                method='normalized_exact_match', official_judge=False)


class BM25:
    """The pinned Anserini search implementation, shared read-only behind a lock."""
    def __init__(self, index=INDEX, java_home=JAVA):
        os.environ['JAVA_HOME'] = str(java_home)
        from pyserini.pyclass import autoclass
        self.searcher = autoclass('io.anserini.search.SimpleSearcher')(str(index))
        self.lock = threading.Lock()

    def search(self, query, k):
        with self.lock:
            hits = [(h.docid, h.score, h.lucene_document.get('raw')) for h in self.searcher.search(query, k)]
        return [dict(docid=d, score=s, text=json.loads(raw)['contents']) for d, s, raw in hits]

    def get_document(self, docid):
        with self.lock:
            doc = self.searcher.doc(docid)
            raw = doc.get('raw') if doc is not None else None
        return dict(docid=docid, text=json.loads(raw)['contents']) if raw else None


class CorpusTools:
    """Per-run telemetry. Tools have no access to answers, qrels or other runs."""
    def __init__(self, retriever):
        self.retriever = retriever
        self.errors = []
        self.retrieved = set()

    def tools(self):
        definitions = {
            'search': ('Search the fixed corpus with BM25. k is 1-5 (default 3), not 10. Returns leading excerpts (1500 characters each); use the returned offsets to read further.',
                       dict(query=dict(type='string', minLength=1, maxLength=2000), k=dict(type='integer', minimum=1, maximum=5)), ['query']),
            'open_document': ('Read an exact document character window, with next_offset for further reading.',
                              dict(docid=dict(type='string'), offset=dict(type='integer', minimum=0),
                                   limit=dict(type='integer', minimum=1, maximum=12000)), ['docid']),
            'find_in_document': ('Locate a literal phrase in one document; return at most five matches with character offsets.',
                                 dict(docid=dict(type='string'), phrase=dict(type='string')), ['docid', 'phrase']),
        }
        result = []
        for name, (description, properties, required) in definitions.items():
            def run(args, agent, name=name, properties=properties, required=required):
                if not isinstance(args, dict) or not set(required) <= args.keys() or set(args) - set(properties):
                    return Observation('Invalid tool arguments', {'error': True})
                for key, value in args.items():
                    schema = properties[key]
                    if schema['type'] == 'string' and (not isinstance(value, str) or not value.strip() or len(value) > 2000):
                        return Observation('Expected a nonempty string of at most 2000 characters', {'error': True})
                    if schema['type'] == 'integer' and (type(value) is not int or value < schema['minimum']
                                                        or value > schema.get('maximum', 100_000_000)):
                        return Observation('Invalid window or result count', {'error': True})
                try:
                    value = self.execute(name, args)
                except Exception as error:
                    self.errors.append(type(error).__name__ + ': ' + str(error)[:1000])
                    raise
                return Observation(json.dumps(value, ensure_ascii=False), {'native_tool': True})
            result.append(Tool(name, description, dict(type='object', properties=properties,
                                                       required=required, additionalProperties=False), run, budgeted=True))
        return result

    def execute(self, name, args):
        if name == 'search':
            hits = self.retriever.search(args['query'], args.get('k', 3))
            self.retrieved.update(h['docid'] for h in hits)
            return dict(results=[dict(docid=h['docid'], score=h['score'], text=h['text'][:1500], offset=0,
                                      total_chars=len(h['text']), next_offset=1500 if len(h['text']) > 1500 else None)
                                 for h in hits], requested_k=args.get('k', 3))
        doc = self.retriever.get_document(args['docid'])
        if doc is None:
            return dict(docid=args['docid'], found=False)
        self.retrieved.add(doc['docid'])
        text = doc['text']
        if name == 'open_document':
            start, limit = args.get('offset', 0), args.get('limit', 6000)
            return dict(docid=doc['docid'], text=text[start:start + limit], offset=start, total_chars=len(text),
                        next_offset=start + limit if start + limit < len(text) else None)
        matches, count = [], 0
        for match in re.finditer(re.escape(args['phrase']), text, re.IGNORECASE):
            count += 1
            if len(matches) < 5:
                matches.append(match)
        return dict(docid=doc['docid'], total_matches=count, matches=[
            dict(match_offset=m.start(), offset=max(0, m.start() - 250),
                 text=text[max(0, m.start() - 250):m.end() + 750]) for m in matches[:5]])
