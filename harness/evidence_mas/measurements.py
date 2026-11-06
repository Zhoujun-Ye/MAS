"""Gold-blind result capture: explicit estimands are comparable; labels are hints."""

import ast
import csv
import hashlib
import json
import math
import re
import warnings

from .store import packed, StoreError

DIMENSIONS = ('quantity', 'statistic', 'population', 'period', 'unit', 'dataset')
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
LABELED = re.compile(r'^\s*([A-Za-z][^:=\n]{0,160})\s*[:=]\s*(' + NUMBER + r')\s*([^\d\n]{0,24})$')
SPACED = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_ ()./%-]{0,160}?)\s{2,}(' + NUMBER + r')\s*([^\d\n]{0,24})$')


def whitespace(text):
    return ' '.join(text.split())


def numeric(value):
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def payload(output):
    if isinstance(output, dict):
        if output.get('interrupted') or output.get('exit_code', output.get('exitCode', 0)) not in (None, 0):
            return None
        if 'stdout' in output:
            return output['stdout']
    return output


def parse_record(text):
    if len(text) > 1024 * 1024:
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', SyntaxWarning)
                return ast.literal_eval(text)
        except (ValueError, SyntaxError, RecursionError, MemoryError):
            return None


def records(output):
    value = payload(output)
    if isinstance(value, (dict, list)):
        return [value]
    if not isinstance(value, str):
        return []
    whole = parse_record(value)
    if isinstance(whole, (dict, list)):
        return [whole]
    return [item for line in value.splitlines() if isinstance(item := parse_record(line), (dict, list))]


def target_key(target):
    return hashlib.sha256(packed(target).encode()).hexdigest()


def measurement(value, target, variant, *, answer_target=False):
    """Use from a parameterized computation to serialize each actual result, not a claim."""
    def valid_value(item):
        return numeric(item) or isinstance(item, str) or (isinstance(item, list) and all(valid_value(x) for x in item))
    if not valid_value(value) or not isinstance(target, dict) or set(target) != set(DIMENSIONS):
        raise StoreError('Measurement needs a finite number, string or list and all six target dimensions')
    if not all(isinstance(v, str) and whitespace(v) and whitespace(v).lower() not in ('unknown','unspecified') for v in target.values()):
        raise StoreError('Target dimensions must be explicit; use not_applicable where appropriate')
    if not isinstance(variant, dict) or type(answer_target) is not bool:
        raise StoreError('Variant must be an object and answer_target a boolean')
    return {'measurement': dict(value=value, target={k:whitespace(target[k]) for k in DIMENSIONS},
                                variant=variant, answer_target=answer_target)}


def emit_measurement(value, target, variant, *, answer_target=False):
    print(packed(measurement(value, target, variant, answer_target=answer_target)), flush=True)


def table_measurements(text):
    """Recover column/row labels, without claiming that a printed table is an estimand."""
    lines = text.splitlines()
    result, index = [], 0
    while index < len(lines)-1:
        header_line = lines[index].strip()
        index += 1
        if header_line.startswith(('{','[','(')):
            continue
        delimiter = '\t' if '\t' in header_line else ',' if ',' in header_line else None
        def split(line):
            return [x.strip() for x in next(csv.reader([line], delimiter=delimiter))] if delimiter else re.split(r'\s{2,}',line.strip())
        try:
            headers = split(header_line)
        except csv.Error:
            continue
        if len(headers)<2 or not all(re.fullmatch(r'[A-Za-z_][\w /().%-]{0,64}',h) for h in headers):
            continue
        row_index = 0
        while index < len(lines):
            try:
                cells = split(lines[index])
            except csv.Error:
                break
            if len(cells) != len(headers):
                break
            numbers = {}
            for col, cell in enumerate(cells):
                if re.fullmatch(r'[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?',cell):
                    cell = cell.replace(',','')
                if re.fullmatch(NUMBER, cell):
                    value = float(cell) if any(c in cell for c in '.eE') else int(cell)
                    if numeric(value):
                        numbers[col] = value
            if not numbers:
                break
            row_labels = {headers[i]:cell for i,cell in enumerate(cells) if i not in numbers}
            for col, value in numbers.items():
                target = dict(table_columns=headers, column=headers[col], row_labels=row_labels, row_position=row_index)
                result.append(dict(value=value,target=target,variant={},answer_target=False,
                                   confidence='possible',group=target_key(target)))
            index += 1
            row_index += 1
    return result


def extract_measurements(output, diagnostics=None):
    found = []
    def walk(item, path=''):
        if isinstance(item, dict):
            typed = item.get('measurement')
            if 'measurement' in item:
                try:
                    if not isinstance(typed, dict):
                        raise StoreError('Measurement must be an object')
                    valid = measurement(typed['value'], typed['target'], typed.get('variant', {}),
                                        answer_target=typed.get('answer_target', False))['measurement']
                    found.append(dict(valid, confidence='explicit', group=target_key(valid['target'])))
                    return
                except (KeyError, StoreError) as exc:
                    if diagnostics is not None:
                        diagnostics.append(dict(path=path + '/measurement', reason=str(exc)))
                    return
            for key, child in item.items():
                if isinstance(key, str):
                    walk(child, path + '/' + key)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, path + '/' + str(index))
        elif (numeric(item) and re.search('[A-Za-z]', path)
              and not any(path == key or path.startswith(key + '/') for key in ('/answer','/final_answer'))):
            target = {'label':path}
            found.append(dict(value=item, target=target, variant={}, answer_target=False,
                              confidence='possible', group=target_key(target)))
    for item in records(output):
        walk(item)
    value = payload(output)
    if isinstance(value, str) and not isinstance(parse_record(value), (dict, list)):
        found.extend(table_measurements(value))
        for line in value.splitlines():
            if re.match(r'^\s*[bcdlps-][rwxStTs-]{9}[+@.]?\s', line):
                continue  # ls timestamps are not labeled calculations.
            match = LABELED.fullmatch(line) or SPACED.fullmatch(line)
            if match:
                label, number, unit = match.groups()
                number = float(number) if any(c in number for c in '.eE') else int(number)
                if numeric(number):
                    target = {'label':whitespace(label), 'unit_hint':whitespace(unit)}
                    found.append(dict(value=number,target=target,variant={},answer_target=False,
                                      confidence='possible',group=target_key(target)))
    unique = {packed(row):row for row in found}
    return list(unique.values())
