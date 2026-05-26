
with open('dashboard/brain.js', 'r', encoding='utf-8') as f:
    js = f.read()
with open('dashboard/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

print('=== brain.js ===')
print('API_BASE:', 'API_BASE' in js)
print('hardcoded 8765:', '127.0.0.1:8765' in js)
print('null check neuralCtx:', 'neuralCanvas && neuralCtx' in js)
print('.catch recall:', 'botMsg' in js and '.catch' in js)
print('parseFloat animCounter:', 'parseFloat' in js)

print()
print('=== index.html ===')
print('CSP:', 'Content-Security-Policy' in html)
print('crossorigin:', 'crossorigin' in html)
print('no dir rtl on html:', 'lang="he" dir="rtl"' not in html)
