"""Host-side cgroup-v2 CPU observations, without inspecting solver content."""

import json
import math
from pathlib import Path
import subprocess
import threading
import time

from common.io import write_json


def cpu_sample(cgroup, elapsed):
    fields = dict(line.split() for line in (cgroup / 'cpu.stat').read_text().splitlines())
    return dict(elapsed_seconds=elapsed, **{k: int(fields[k]) for k in
        ('usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled', 'throttled_usec')})


def memory_sample(cgroup):
    result={}
    for name in ('current','peak'):
        try:
            result[name+'_bytes']=int((cgroup/('memory.'+name)).read_text())
        except (OSError,ValueError):
            result[name+'_bytes']=None
    try:
        result['events']={k:int(v) for k,v in (line.split() for line in (cgroup/'memory.events').read_text().splitlines())}
    except (OSError,ValueError):
        result['events']=None
    return result


def pressure_sample(cgroup):
    result = {}
    for resource in ('cpu', 'io', 'memory'):
        try:
            rows = [line.split() for line in (cgroup / (resource + '.pressure')).read_text().splitlines()]
            result[resource] = {row[0]: int(dict(item.split('=') for item in row[1:])['total'])
                                for row in rows}
        except (OSError, ValueError, KeyError):
            result[resource] = None
    return result


def pressure_summary(samples):
    result = {}
    for resource in ('cpu', 'io', 'memory'):
        values = [s.get('pressure', {}).get(resource) for s in samples]
        complete = len(values) >= 2 and all(isinstance(v, dict) and 'some' in v for v in values)
        delta = None
        if complete and values[0].keys() == values[-1].keys():
            delta = {k: (values[-1][k] - values[0][k]) / 1e6 for k in values[0]}
            if any(v < 0 for v in delta.values()):
                delta = None
        result[resource] = dict(capture_complete=complete and delta is not None, stalled_seconds=delta)
    return result


def memory_summary(samples):
    values=[s.get('memory',{}) for s in samples]
    current=[v.get('current_bytes') for v in values if v.get('current_bytes') is not None]
    peak=[v.get('peak_bytes') for v in values if v.get('peak_bytes') is not None]
    events=[v['events'] for v in values if v.get('events') is not None]
    delta={k:events[-1].get(k,0)-events[0].get(k,0) for k in ('oom','oom_kill','max')} if len(events)>=2 else None
    reset=delta is not None and any(v<0 for v in delta.values())
    if reset:delta=None
    return dict(available=bool(current),sampled_peak_bytes=max(current) if current else None,
                cgroup_peak_bytes=max(peak) if peak else None,events_delta=delta,
                capture_complete=bool(values) and all(v.get('current_bytes') is not None and v.get('events') is not None for v in values),
                counter_reset=reset,
                oom_observed=(delta['oom_kill']>0 or delta['oom']>0) if delta and all(v>=0 for v in delta.values()) else None,
                scope='Cgroup lifetime peak and sampled usage; absent counters are unknown, not zero')


def summarize(samples, cpus):
    if len(samples) < 2:
        return dict(available=False, reason='insufficient_samples')
    first, last = samples[0], samples[-1]
    elapsed = last['elapsed_seconds'] - first['elapsed_seconds']
    if elapsed <= 0:
        return dict(available=False, reason='no_elapsed_interval')
    delta = {k: last[k] - first[k] for k in ('usage_usec', 'nr_periods', 'nr_throttled', 'throttled_usec')}
    if any(v < 0 for v in delta.values()):
        return dict(available=False, reason='counter_reset')
    cores = delta['usage_usec'] / 1e6 / elapsed
    intervals = [(b['usage_usec'] - a['usage_usec']) / 1e6 / (b['elapsed_seconds'] - a['elapsed_seconds'])
                 for a, b in zip(samples, samples[1:])
                 if b['elapsed_seconds'] > a['elapsed_seconds'] and b['usage_usec'] >= a['usage_usec']]
    return dict(available=True, measured_seconds=elapsed, cpu_seconds=delta['usage_usec'] / 1e6,
        average_cores=cores, quota_utilization_percent=100 * cores / cpus,
        maximum_sample_interval_cores=max(intervals) if intervals else None,
        throttled_seconds=delta['throttled_usec'] / 1e6,
        throttled_periods=delta['nr_throttled'], periods=delta['nr_periods'],
        throttled_period_fraction=delta['nr_throttled'] / delta['nr_periods'] if delta['nr_periods'] else None,
        scope='Container cgroup deltas; throttled time is kernel quota accounting, not provider rate-limit waiting')


class ContainerResources:
    def __init__(self, identity, output, cpus, interval=5):
        if type(cpus) is not int or not 1 <= cpus <= 128:
            raise ValueError('Expected 1-128 integer CPUs')
        if isinstance(interval, bool) or not math.isfinite(interval) or interval <= 0:
            raise ValueError('Sampling interval must be positive and finite')
        self.identity, self.output, self.cpus = identity, Path(output), cpus
        self.interval = interval
        self.samples, self.errors = [], []
        self.done = threading.Event()
        self.thread = None
        self.result = None

    def sample(self):
        try:
            row = cpu_sample(self.cgroup, time.monotonic() - self.started)
            row['memory']=memory_sample(self.cgroup)
            row['pressure']=pressure_sample(self.cgroup)
            self.samples.append(row)
            with (self.output / 'cpu-samples.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row) + '\n')
        except (OSError, ValueError, KeyError) as error:
            self.errors.append(type(error).__name__)

    def start(self):
        if self.thread is not None:
            raise RuntimeError('Resource collector is already started')
        if any((self.output / name).exists() for name in ('cpu-samples.jsonl', 'cpu-quota.json', 'cpu-summary.json')):
            raise FileExistsError('Refuse to mix resource captures from different lifetimes')
        info = json.loads(subprocess.check_output(['docker', 'inspect', self.identity], text=True, timeout=15))[0]
        if info['HostConfig']['NanoCpus'] != self.cpus * 1_000_000_000:
            raise ValueError('Observed CPU quota differs from the frozen setting')
        pid = info['State']['Pid']
        relative = next(line.split(':', 2)[2] for line in Path(f'/proc/{pid}/cgroup').read_text().splitlines()
                        if line.startswith('0::'))
        root = Path('/sys/fs/cgroup').resolve()
        self.cgroup = (root / relative.lstrip('/')).resolve()
        if not self.cgroup.is_relative_to(root):
            raise ValueError('Invalid cgroup path')
        self.started = time.monotonic()
        self.sample()
        if not self.samples or self.errors:
            raise RuntimeError('Host cgroup CPU metrics unavailable before solver launch')
        write_json(self.output / 'cpu-quota.json', dict(cpus=self.cpus,
            cpu_max=(self.cgroup / 'cpu.max').read_text().strip(), interval_seconds=self.interval))
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return self

    def run(self):
        while not self.done.wait(self.interval):
            self.sample()

    def exit_state(self):
        try:
            state=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}',self.identity],text=True,timeout=15))
            return dict(running=state['Running'],oom_killed=state['OOMKilled'],
                        exit_code=state['ExitCode'] if not state['Running'] else None,
                        scope='Container init state, not the solver docker-exec exit code')
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):
            return dict(available=False)

    @staticmethod
    def merge_exit_oom(result):
        if (result.get('container_exit') or {}).get('oom_killed') is True:
            memory = result['memory']
            memory.setdefault('sampled_oom_observed', memory.get('oom_observed'))
            memory['oom_observed'] = True
            memory['oom_observation_basis'] = 'docker_container_state'

    def close(self, *, final_sample=True):
        if self.result is not None:
            return self.result
        self.done.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
        sampler_alive = self.thread is not None and self.thread.is_alive()
        if sampler_alive:
            self.errors.append('sampler_shutdown_timeout')
        if final_sample and not sampler_alive:
            self.sample()
        result = dict(summarize(self.samples, self.cpus), cpus=self.cpus,
                      sample_count=len(self.samples), sample_errors=list(self.errors),
                      final_sample_requested=final_sample,
                      capture_complete=not self.errors and final_sample)
        result['memory']=memory_summary(self.samples)
        result['pressure']=pressure_summary(self.samples)
        result['container_exit']=self.exit_state() if self.thread is not None else None
        self.merge_exit_oom(result)
        write_json(self.output / 'cpu-summary.json', result)
        self.result = result
        return result

    def record_exit(self):
        result=self.close()
        result['container_exit']=self.exit_state()
        self.merge_exit_oom(result)
        write_json(self.output/'cpu-summary.json',result)
        return result
