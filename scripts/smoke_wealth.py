import sys, time
from decimal import Decimal
sys.path.insert(0, '.')
sys.path.insert(0, 'runtime')
from agency.wealth import WealthEngine
from agency.kpi import registry

# fresh ledger
from pathlib import Path
p = Path.home() / '.agency' / 'ledger' / 'wealth.jsonl'
if p.exists():
    p.unlink()

w = WealthEngine()
print('agents loaded:', len(w.agents))
print('accounts:', sorted(w.ledger.accounts))

w.record_capital('10000')
w.record_revenue('2500', memo='Q1 sale')
w.record_revenue('1500', memo='credit sale', on_credit=True)
w.record_expense('800', memo='materials', category='cogs')
w.record_expense('600', memo='rent', category='opex')
w.record_collection('1500', memo='paid invoice')

print('pnl:', {k: str(v) for k,v in w.pnl().items()})
print('bs:',  {k: str(v) for k,v in w.balance_sheet().items()})
print('balanced:', w.ledger.is_balanced())

w.publish_kpis()
print('kpi gauges:', {k: v for k, v in registry.export()['gauges'].items() if k.startswith('wealth.')})

# daemon spin
d = w.start_daemon(snapshot_every_s=0.1, save_every_s=0.2)
time.sleep(0.5)
w.stop_daemon()
print('daemon ran jobs:', [(j.name, j.runs, j.last_ok) for j in d.jobs()])
print('ledger persisted:', p.exists())
