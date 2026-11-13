"""Freeze ten targeted recorded first-delegation prefixes, without future artifacts."""

import argparse
import hashlib
from pathlib import Path

from benchmarks.kramabench.evaluation import grade_answer
from common.io import fingerprint, write_json
from .e4_runtime import edited_brief, prefix
from .selection import selected_tasks

# Edits remove certainty, not candidate information, and never supply a correct answer.
CASES = (
    ('biomedical-hard-8', 2, 'hedged', 'leader', 'candidate-source hypothesis; truth mixed',
     [('Likely relevant:', 'Which of these candidate sources are actually relevant and available:')]),
    ('astronomy-easy-5', 1, 'hedged', 'task_reinforcement', 'package/API assumption requires verification',
     [("likely a Python package 'skifield' with a submodule itrf_xyz; find it with", "is there a Python package 'skifield' with a submodule itrf_xyz? Check with")]),
    ('legal-easy-4', 2, 'asserted', 'leader_interpretation', 'ambiguous reporting channel versus victim contact channel',
     [('(online/web channel of contact)', '(does over the web refer to a reporting channel or an online/web channel of contact?)')]),
    ('legal-hard-16', 2, 'asserted', 'leader', 'false separate states-column assertion',
     [('the FTC metro file has a "states" column; it may list metros spanning several states',
       'does the FTC metro file have a "states" column, and can metros span several states?')]),
    ('biomedical-hard-7', 0, 'hedged', 'leader', 'candidate source hypothesis, not the later worker-created BRD8 error',
     [('likely a TCGA-ATAC/proteomics multi-omics dataset (e.g., CPTAC breast cancer acetylproteomics, or TCGA pan-cancer) where genes are tested for significance via acetylproteomics measurements.',
       'is this a TCGA-ATAC/proteomics multi-omics dataset (e.g., CPTAC breast cancer acetylproteomics, or TCGA pan-cancer) where genes are tested for significance via acetylproteomics measurements?')]),
    ('wildfire-hard-20', 1, 'asserted', 'leader', 'mixed source/column hypotheses, damaged versus destroyed interpretation',
     [('This is almost certainly about wildfire perimeters ranked by number of structures/residences destroyed',
       'Is this about wildfire perimeters ranked by number of structures/residences destroyed? Consider'),
      ("NOAA Storm Events (which has WILDFIRE event type and 'Damage_Houses'!)",
       "NOAA Storm Events (does it have a WILDFIRE event type and 'Damage_Houses'?)")]),
    ('wildfire-hard-17', 0, 'hedged', 'leader', 'candidate station/source filter needs verification',
     [('likely a GHCN weather stations dataset with "fire" in station names/labels, e.g. GHCN_Hourly or similar',
       'is it a GHCN weather stations dataset with "fire" in station names/labels, e.g. GHCN_Hourly or similar?'),
      ('(e.g. station name containing "FIRE")', '(does station name containing "FIRE" identify them?)')]),
    ('legal-easy-13', 1, 'hedged', 'leader', 'false candidate domain hypothesis: parks rather than FTC reports',
     [('(likely parks recreation / incident reports / safety reports with a category column and dates)',
       '(is it parks recreation / incident reports / safety reports with a category column and dates?)')]),
    ('environment-hard-8', 1, 'correct_control', 'task_entailed', 'correct threshold supplied by the public question',
     [('(Enterococcus count > 104 per 100 mL)', '(is Enterococcus count > 104 per 100 mL the threshold?)')]),
    ('wildfire-easy-2', 0, 'correct_control', 'leader', 'correct NIFC expansion; a weak factual control, not an answer premise',
     [('NIFC = National Interagency Fire Center;', 'Does NIFC mean National Interagency Fire Center?')]),
)


def build(root, donor):
    tasks, _ = selected_tasks(root)
    lookup = {t.id:t for t in tasks}
    cases = []
    for task, seed, strength, origin, truth, edits in CASES:
        if task not in lookup or grade_answer(root/'kramabench/upstream', task, None)['answer_type']=='string_approximate':
            raise ValueError('E4 must use ten frozen, offline-gradable tasks')
        saved = prefix(donor/f'round-{seed}'/task/'native'/task/'claude-code-subagents')
        case = dict(task_id=task, question=lookup[task].query, donor_seed=seed, prefix=saved,
                    premise_strength=strength, premise_origin=origin, premise_annotation=truth,
                    edits=[dict(before=a, after=b) for a,b in edits])
        for variant in ('verbatim','open','task_only'):
            edited_brief(case, variant)
        cases.append(case)
    if len(cases)!=10 or len({c['task_id'] for c in cases})!=10:
        raise ValueError('Exactly ten distinct E4 tasks are required')
    return dict(kind='e4-first-delegation-replay-v1', cases=cases, seeds=[0,1,2],
        worker_sessions=90, lead_sessions=90, timeout_seconds=900, retries=0,
        selection='Targeted historical hypotheses: eight suspect/hedged cases and two correct-premise controls; not held out',
        report_delivery='Immediate result at the first delegation boundary, not original asynchronous arrival timing',
        worker_protocol='Fresh native main session selecting the recorded built-in role and its restricted tool surface; common JSON reporting footer; regenerated primary-session system prompt, not the original subagent system prompt',
        coding=dict(verification='Evidence-backed check performed: yes/no/unclear',
                    stance='supports/challenges/uncertain, separately from verification and correctness',
                    correctness='Offline candidate-answer grade when available; null is unknown, not a claimed wrong answer',
                    uptake='Report-correct/final-wrong is diagnostic only, not automatically uptake loss'),
        limitations=['One fixed recorded brief per task across all three repeats.',
            'Hedged and task-origin premises are not mislabeled leader-created fixed errors.',
            'The task-only arm removes the entire delegated brief, not only its premise.',
            'Worker-role replays are fresh main sessions, not bit-for-bit original native subagent requests; role/tool constraints and system regeneration are common across all three variants.',
            'Correct controls include one task-entailed threshold and one weak factual definition.',
            'No extra paid response-coding judge, best-report selection, final-workspace restoration or hidden retries.'])


def validate(manifest):
    if (manifest.get('kind')!='e4-first-delegation-replay-v1' or len(manifest.get('cases',[]))!=10
            or len({c['task_id'] for c in manifest['cases']})!=10
            or manifest.get('worker_sessions')!=90 or manifest.get('lead_sessions')!=90
            or manifest.get('seeds')!=[0,1,2] or manifest.get('timeout_seconds')!=900
            or manifest.get('retries')!=0):
        raise ValueError('Invalid E4 manifest')
    for case in manifest['cases']:
        saved=case['prefix']
        if fingerprint(saved['rows'])!=saved['provenance']['prefix_sha256']:
            raise ValueError('E4 recorded prefix changed')
        if saved['agent_type'] not in {'Explore','general-purpose'}:
            raise ValueError('Unverified worker role')
        for variant in ('verbatim','open','task_only'):
            edited_brief(case,variant)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('/home/zhoujunye/mas-data'))
    p.add_argument('--donor',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    manifest=validate(build(args.root,args.donor))
    write_json(args.output,manifest)
    print(dict(tasks=len(manifest['cases']),sessions=180,sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),paid_calls=0))


if __name__=='__main__':main()
