import sys
from decimal import Decimal
sys.path.insert(0, '.')
from ledger import Ledger

L = Ledger('smoke')
L.add_account('cash', 'asset')
L.add_account('revenue', 'revenue')
L.add_account('rent_expense', 'expense')
L.add_account('owner_equity', 'equity')

# Initial capital
L.post('initial capital', debits=[('cash', '1000.00')], credits=[('owner_equity', '1000.00')])
# Sale
L.post('cash sale', debits=[('cash', '250.00')], credits=[('revenue', '250.00')])
# Pay rent
L.post('rent payment', debits=[('rent_expense', '300.00')], credits=[('cash', '300.00')])

tb = L.trial_balance()
print('balances:', {k: str(v) for k, v in tb.items()})
print('balanced:', L.is_balanced())
print('cash should be 950:', L.balance('cash') == Decimal('950'))

# Persistence roundtrip
p = L.save()
print('saved:', p.name)
L2 = Ledger.load('smoke')
print('reload txns:', len(L2.transactions), 'accounts:', len(L2.accounts))
print('reload cash:', L2.balance('cash'))

# Error: unbalanced
try:
    L.post('bad', debits=[('cash', '10')], credits=[('revenue', '5')])
except ValueError as e:
    print('caught unbalanced:', e)

# Error: negative
try:
    L.post('bad2', debits=[('cash', '-5')], credits=[('revenue', '5')])
except ValueError as e:
    print('caught negative:', e)
