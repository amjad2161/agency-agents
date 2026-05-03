import sys, asyncio
sys.path.insert(0, '.')
from pipelines import Pipeline, Stage

def s1(c): c['a'] = 1; return c
def s2(c): c['b'] = c['a'] + 10; return c
async def s3(c): c['c'] = 'async'; return c

out = Pipeline.of('demo', ('init', s1), ('add', s2)).run({})
print('sync out:', out)

out2 = asyncio.run(Pipeline.of('demo2', s1, s3).arun({}))
print('async out:', out2)

# error path
def bad(c): raise RuntimeError('boom')
try:
    Pipeline.of('demo3', s1, ('bad', bad)).run({})
except RuntimeError as e:
    print('caught:', e)

# verify trace was flushed
from agency.trace_logger import TraceLogger
import os
from pathlib import Path
traces = Path.home() / '.agency' / 'traces'
files = sorted(traces.glob('pipeline-demo-*.jsonl'))
print('trace files:', len(files))
if files:
    spans = TraceLogger.tail(files[-1].stem, n=10)
    print('spans:', [(s['name'], s.get('parent') is None) for s in spans])
