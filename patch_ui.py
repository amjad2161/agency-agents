import re
import sys

def patch_brain():
    with open('dashboard/brain.js', 'r', encoding='utf-8') as f:
        text = f.read()

    # 1. Add API_BASE to CFG
    if "API_BASE" not in text:
        text = text.replace("PERM_LEVEL: 'GOD',", "PERM_LEVEL: 'GOD',\n  API_BASE: 'http://127.0.0.1:8765',")

    # 2. Replace hardcoded IPs in fetch
    text = re.sub(r"'http://127\.0\.0\.1:8765/([^']+)'", r"`${CFG.API_BASE}/\1`", text)

    # 3. Fix resizeAll null check
    text = text.replace("if (neuralCanvas) {", "if (neuralCanvas && neuralCtx) {")

    # 4. Fix parseInt -> parseFloat
    text = text.replace("parseInt(raw.replace(/[KM]/g,''))", "parseFloat(raw.replace(/[KM]/g,''))")
    text = text.replace("parseInt(el.dataset.delay || 0)", "parseInt(el.dataset.delay || 0, 10)")

    # 5. Fix double-response in handleChat
    text = text.replace("  // Visual routing\n  callSingularityRoute(text);", "  // Visual routing (moved to fallback)")
    old_fallback = """  // Ollama or fallback
  if (S.ollama.available) {
    callOllama(text);
  } else {
    callLocalAgentServer(text, true);
  }"""
    new_fallback = """  // Singularity backend routing (replaces old local fallback)
  callSingularityRoute(text);"""
    text = text.replace(old_fallback, new_fallback)

    # 6. Fix recall fetch missing .catch
    old_recall = """    }).then(r => r.json()).then(data => {
      if (data && data.length > 0) {
         botMsg(`**${k}**: ${data[0].content}`);
      } else {
         botMsg(`לא נמצא זיכרון תחת המפתח *${k}* ב-Vector Memory.`);
      }
    });"""
    new_recall = old_recall.replace("    });", "    }).catch(e => botMsg('שגיאה בשליפת זיכרון: ' + e.message));")
    text = text.replace(old_recall, new_recall)

    with open('dashboard/brain.js', 'w', encoding='utf-8') as f:
        f.write(text)
    print("brain.js patched")

def patch_index():
    with open('dashboard/index.html', 'r', encoding='utf-8') as f:
        html = f.read()

    html = html.replace('<html lang="he" dir="rtl">', '<html lang="he">')
    html = html.replace('<link rel="preconnect" href="https://fonts.googleapis.com"/>', '<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin/>')

    csp = '<meta http-equiv="Content-Security-Policy" content="default-src \'self\' \'unsafe-inline\' \'unsafe-eval\' https://fonts.googleapis.com https://fonts.gstatic.com; connect-src \'self\' http://127.0.0.1:* http://localhost:* https://api.github.com; img-src \'self\' data: https:; font-src \'self\' https://fonts.gstatic.com data:;">'
    if "Content-Security-Policy" not in html:
        html = html.replace('<meta charset="UTF-8"/>', f'<meta charset="UTF-8"/>\n  {csp}')

    with open('dashboard/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("index.html patched")

try:
    patch_brain()
    patch_index()
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
