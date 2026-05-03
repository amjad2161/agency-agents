import sys, time
sys.path.insert(0, 'runtime')
from agency.daemon import Daemon
from agency.kpi import registry, snapshot
from agency.trace_logger import TraceLogger

hits = {'a': 0, 'b': 0}

def task_a():
    hits['a'] += 1

def task_b():
    hits['b'] += 1
    if hits['b'] == 2:
        raise RuntimeError("simulated failure on 2nd run")

d = Daemon(name='smoke', tick_seconds=0.05)
d.add_job('a', 0.1, task_a)
d.add_job('b', 0.15, task_b)
d.start()
time.sleep(0.6)
d.stop()
print('hits:', hits)
print('jobs:', [(j.name, j.runs, j.last_ok, j.last_error) for j in d.jobs()])
print('kpi:', registry.export())
print('snapshot:', snapshot('daemon-smoke').name)

# verify trace spans for daemon + jobs
spans = TraceLogger.tail(d._session, n=50)
names = [s['name'] for s in spans]
print('span names:', sorted(set(names)))
print('any errors:', any(s.get('meta', {}).get('ok') is False for s in spans))
