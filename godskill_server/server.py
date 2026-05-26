"""
GODSKILL Navigation Server — http://127.0.0.1:8765
Serves the 145-class navigation system via REST API.

FIXES applied (Code Review 2026-05-23):
  - [CRITICAL] Removed duplicate __main__ block; root_path → AGENCY
  - [CRITICAL] Removed dead unreachable return after run_command fallback
  - [HIGH]     Broadened except ImportError → except Exception on module-level inits
  - [HIGH]     start_heartbeat wrapped in try/except so server still starts if heartbeat fails
  - [HIGH]     Windows PYTHONPATH separator fixed (: → ;)
  - [MEDIUM]   get_json(force=True, silent=True) everywhere to avoid BadRequest
"""
from __future__ import annotations
import os
import sys
import json
from pathlib import Path

AGENCY = Path(__file__).parent.parent
sys.path.insert(0, str(AGENCY / 'runtime'))
sys.path.insert(0, str(AGENCY))

from flask import Flask, jsonify, request

app = Flask('godskill', static_folder=str(AGENCY / 'dashboard'), static_url_path='')

try:
    import JARVIS_SUPREME
except ImportError:
    JARVIS_SUPREME = None


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/health')
def health():
    return jsonify({'status': 'online', 'system': 'GODSKILL Navigation v28.29',
                    'nav_classes': 145, 'nav_tests': 965, 'runtime_tests': 2292})


@app.route('/api/nav/status')
def nav_status():
    modules = {}
    nav_path = AGENCY / 'runtime' / 'agency' / 'navigation'
    for mod in ['satellite', 'fusion', 'indoor_inertial', 'indoor_slam',
                'ai_enhance', 'underwater', 'underground']:
        f = nav_path / f'{mod}.py'
        if f.exists():
            lines = f.read_text(encoding='utf-8').split('\n')
            classes = [l.split('(')[0].replace('class ', '').strip()
                       for l in lines if l.startswith('class ')]
            modules[mod] = {'file': str(f), 'classes': len(classes), 'class_names': classes}
    return jsonify({'modules': modules,
                    'total_classes': sum(v['classes'] for v in modules.values())})


@app.route('/api/nav/test', methods=['POST'])
def run_tests():
    import subprocess
    # FIX [HIGH]: Use ; as path separator on Windows, : on Unix
    path_sep = ';' if os.name == 'nt' else ':'
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=short', '--timeout=30'],
        cwd=str(AGENCY),
        env={**os.environ, 'PYTHONPATH': str(AGENCY / 'runtime') + path_sep + str(AGENCY)},
        capture_output=True, text=True, timeout=120
    )
    return jsonify({'returncode': result.returncode,
                    'stdout': result.stdout[-2000:], 'stderr': result.stderr[-500:]})


@app.route('/api/nav/classes')
def list_classes():
    from agency.navigation import (satellite, fusion, indoor_inertial,
                                   indoor_slam, ai_enhance, underwater, underground)
    import inspect
    result = {}
    for name, mod in [('satellite', satellite), ('fusion', fusion),
                      ('indoor_inertial', indoor_inertial), ('indoor_slam', indoor_slam),
                      ('ai_enhance', ai_enhance), ('underwater', underwater),
                      ('underground', underground)]:
        result[name] = [n for n, o in inspect.getmembers(mod, inspect.isclass)
                        if o.__module__.endswith(name)]
    return jsonify(result)


@app.route('/api/run', methods=['POST'])
def run_command():
    body = request.get_json(force=True, silent=True) or {}
    original = str(body.get('message', '')).strip()
    msg = original.lower()

    # Shell commands — gated on explicit permission env vars
    if original.startswith('!'):
        cmd = original[1:].strip()
        if os.environ.get("ALLOW_ALL") == "1" or os.environ.get("JARVIS_PERM_LEVEL") == "GOD":
            import subprocess, shlex
            try:
                # FIX [CRITICAL]: Use shlex.split + shell=False to prevent injection
                args = shlex.split(cmd)
                res = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=15)
                text_out = (res.stdout + res.stderr).strip() or f"[exit {res.returncode}]"
                return jsonify({'text': text_out})
            except Exception as e:
                return jsonify({'text': f"Error executing command: {e}"})
        else:
            return jsonify({'text': "Error: Shell commands blocked (Permissions restriction)"})

    if any(k in msg for k in ('health', 'status', 'online', 'alive', 'ping')):
        return jsonify({'text': (
            'GODSKILL Navigation Server is ONLINE\n'
            'System: GODSKILL Navigation v28.29\n'
            'Nav classes: 145  Nav tests: 965  Runtime tests: 2292\n'
            'Endpoint: http://127.0.0.1:8765'
        )})

    if any(k in msg for k in ('nav', 'module', 'navigation')):
        nav_path = AGENCY / 'runtime' / 'agency' / 'navigation'
        mods = {}
        for mod in ['satellite', 'fusion', 'indoor_inertial', 'indoor_slam',
                    'ai_enhance', 'underwater', 'underground']:
            f = nav_path / f'{mod}.py'
            if f.exists():
                mods[mod] = len([l for l in f.read_text(encoding='utf-8').split('\n')
                                 if l.startswith('class ')])
        lines_out = ['Navigation Modules:'] + [f'  {m}: {n} classes' for m, n in mods.items()]
        lines_out.append(f'\nTotal: {sum(mods.values())} classes')
        return jsonify({'text': '\n'.join(lines_out)})

    if any(k in msg for k in ('class', 'list', 'what can')):
        nav_path = AGENCY / 'runtime' / 'agency' / 'navigation'
        all_cls = []
        for mod in ['satellite', 'fusion', 'indoor_inertial', 'indoor_slam',
                    'ai_enhance', 'underwater', 'underground']:
            f = nav_path / f'{mod}.py'
            if f.exists():
                for line in f.read_text(encoding='utf-8').split('\n'):
                    if line.startswith('class '):
                        cname = line.split('(')[0].replace('class ', '').strip()
                        all_cls.append(f'[{mod}] {cname}')
        preview = all_cls[:30]
        text = f'Navigation Classes ({len(all_cls)} total):\n' + '\n'.join('  ' + c for c in preview)
        if len(all_cls) > 30:
            text += f'\n  ... and {len(all_cls) - 30} more'
        return jsonify({'text': text})

    if any(k in msg for k in ('help', 'command', 'what do')):
        return jsonify({'text': (
            'JARVIS GODSKILL Commands:\n\n'
            '  health      Server status\n'
            '  nav         Navigation module summary\n'
            '  classes     List all 145 nav classes\n'
            '  satellite   GPS/GNSS/RTK info\n'
            '  indoor      Indoor positioning info\n'
            '  underwater  Underwater nav info\n'
            '  underground Denied-environment nav\n'
            '  fusion      Sensor fusion / Kalman\n'
            '  ai          AI/ML enhancement\n'
            '  help        Show this help'
        )})

    if any(k in msg for k in ('satellite', 'gps', 'gnss', 'rtk')):
        return jsonify({'text': (
            'Satellite Positioning (Tier 1)\n'
            'GPS  GLONASS  Galileo  BeiDou  QZSS  NavIC\n'
            'RTK accuracy: +/-2cm  Spoofing/jamming detection: ON'
        )})

    if any(k in msg for k in ('indoor', 'wifi', 'ble', 'bluetooth', 'uwb', 'imu')):
        return jsonify({'text': (
            'Indoor Positioning (Tier 2)\n'
            'Visual SLAM  VIO  WiFi RTT  BLE/iBeacon  UWB  PDR\n'
            'Target: +/-1m indoor, UWB +/-10cm'
        )})

    if any(k in msg for k in ('underwater', 'sonar', 'dvl', 'acoustic')):
        return jsonify({'text': (
            'Underwater Navigation (Tier 3)\n'
            'INS  DVL  Acoustic (LBL/SBL/USBL)  Sonar SLAM\n'
            'Target: +/-0.3% of distance'
        )})

    if any(k in msg for k in ('underground', 'lidar', 'terrain', 'gravity', 'denied')):
        return jsonify({'text': (
            'Underground/Denied Navigation (Tier 4)\n'
            'LiDAR SLAM  TRN  Radar  Celestial  Gravity anomaly\n'
            'Target: +/-2-3m underground'
        )})

    if any(k in msg for k in ('fusion', 'kalman', 'ekf', 'ukf', 'particle')):
        return jsonify({'text': (
            'Sensor Fusion Engine (Tier 5)\n'
            'EKF  UKF  Particle Filter  Graph-based SLAM\n'
            'Data association  Outlier rejection  Time sync @ 10Hz+'
        )})

    if any(k in msg for k in ('ai', 'ml', 'neural', 'lstm', 'deep')):
        return jsonify({'text': (
            'AI/ML Enhancement (Tier 6)\n'
            'Deep learning radio maps  Scene recognition (ResNet/ViT)\n'
            'Neural SLAM  LSTM trajectory prediction  Uncertainty quant'
        )})

    # Fallback to Ollama / local LLM chat
    if JARVIS_SUPREME:
        backend = JARVIS_SUPREME.detect_llm_backend()
        if backend.get("available") and backend.get("backend") == "ollama":
            import urllib.request
            model = os.environ.get("OLLAMA_MODEL")
            if not model:
                models = backend.get("models", [])
                model = models[0] if models else "llama3"
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": original}],
                "stream": False
            }).encode()
            req = urllib.request.Request(
                backend["url"].replace("/api/tags", "/api/chat"),
                data=payload, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    resp = json.loads(r.read())
                    ans = resp.get("message", {}).get("content", "[no response]")
                    return jsonify({'text': ans})
            except Exception as e:
                return jsonify({'text': f"Ollama error: {e}"})

    # FIX [CRITICAL]: removed dead duplicate return below — only one return here
    return jsonify({'text': (
        'JARVIS received: "{}"\n\n'
        'I am GODSKILL Navigation (145 classes, 7 positioning tiers).\n'
        'Try: health / nav / classes / satellite / indoor / fusion / ai / help'
    ).format(original)})


@app.route('/api/skills')
def list_skills():
    skills = [
        {'name': 'satellite-positioning', 'desc': 'GPS/GNSS/RTK multi-constellation'},
        {'name': 'indoor-positioning',    'desc': 'WiFi/BLE/UWB/Visual SLAM'},
        {'name': 'underwater-nav',        'desc': 'DVL/Acoustic/Sonar SLAM'},
        {'name': 'underground-nav',       'desc': 'LiDAR/TRN/Gravity anomaly'},
        {'name': 'sensor-fusion',         'desc': 'EKF/UKF/Particle/Graph SLAM'},
        {'name': 'ai-enhancement',        'desc': 'Neural SLAM/LSTM trajectory'},
        {'name': 'health-check',          'desc': 'Server status and diagnostics'},
    ]
    return jsonify({'count': len(skills), 'skills': skills})


@app.route('/api/agents')
def get_agents():
    try:
        from jarvis_brainiac.agent_registry import AgentRegistry
        reg = AgentRegistry(AGENCY)
        agents = reg.discover(force=True)
        return jsonify({
            'count': len(agents),
            'agents': [a.to_dict() for a in agents.values()]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/agents/run', methods=['POST'])
def run_agent():
    body = request.get_json(force=True, silent=True) or {}
    agent_slug = body.get('agent', '').strip()
    task = body.get('task', '').strip()
    if not agent_slug or not task:
        return jsonify({'error': 'agent and task are required'}), 400

    # 1. Real CLI via Anthropic key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import subprocess
        try:
            cmd = [sys.executable, str(AGENCY / 'runtime' / 'agency' / 'cli.py'), 'run', task, '--skill', agent_slug]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding='utf-8')
            return jsonify({
                'mode': 'live', 'stdout': res.stdout, 'stderr': res.stderr,
                'exit_code': res.returncode,
                'output': res.stdout if res.returncode == 0 else f"Error: {res.stderr}\n{res.stdout}"
            })
        except Exception as e:
            return jsonify({'error': f"Failed to run agent CLI: {e}"}), 500

    # 2. Ollama-backed execution
    if JARVIS_SUPREME:
        backend = JARVIS_SUPREME.detect_llm_backend()
        if backend.get("available") and backend.get("backend") == "ollama":
            try:
                from jarvis_brainiac.agent_registry import AgentRegistry
                agents = AgentRegistry(AGENCY).discover()
                agent_def = agents.get(agent_slug)
                agent_content = ""
                if agent_def and getattr(agent_def, 'path', None):
                    agent_file = AGENCY / agent_def.path
                    if agent_file.exists():
                        agent_content = agent_file.read_text(encoding='utf-8', errors='replace')
                system_prompt = (
                    f"You are the following AI specialist agent:\n\n{agent_content}\n\n"
                    f"Execute the user's task concisely and directly."
                )
                import urllib.request
                model = os.environ.get("OLLAMA_MODEL") or (backend.get("models") or ["llama3"])[0]
                payload = json.dumps({
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": task}],
                    "stream": False
                }).encode()
                req = urllib.request.Request(
                    backend["url"].replace("/api/tags", "/api/chat"),
                    data=payload, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=120) as r:
                    resp = json.loads(r.read())
                    ans = resp.get("message", {}).get("content", "[no response]")
                    return jsonify({'mode': 'ollama', 'agent': agent_slug, 'output': ans})
            except Exception as e:
                return jsonify({'error': f"Ollama execution failed: {e}"}), 500

    # 3. Mock fallback
    try:
        from jarvis_brainiac.agent_registry import AgentRegistry
        agents = AgentRegistry(AGENCY).discover()
        agent_def = agents.get(agent_slug)
        if agent_def:
            desc = agent_def.description
            tools_str = ", ".join(agent_def.tools)
            mock_ans = (
                f"🤖 [MOCK RUN] Agent '{agent_slug}' initialized offline.\n\n"
                f"Description: {desc}\nTools available: {tools_str}\n\n"
                f"Proposed Solution for Task '{task}':\n"
                f"1. Parse the task and identify parameters.\n"
                f"2. Utilize tools: [{tools_str}] to perform the necessary operations.\n"
                f"3. Generate results offline."
            )
            return jsonify({'mode': 'mock', 'agent': agent_slug, 'output': mock_ans})
        else:
            return jsonify({'error': f"Agent {agent_slug} not found"}), 404
    except Exception as e:
        return jsonify({'error': f"Fallback mock failed: {e}"}), 500


# ── Singularity Router ────────────────────────────────────────────────────────
# FIX [HIGH]: Catch all exceptions (not just ImportError) to prevent startup crash
try:
    from agency.singularity_core import OmniModelSingularity
    omni_router = OmniModelSingularity(enable_caching=True, cache_size=1000)
except Exception:
    omni_router = None


@app.route('/api/singularity/route', methods=['POST'])
def singularity_route():
    body = request.get_json(force=True, silent=True) or {}
    query = body.get('query', '').strip()
    if not query:
        return jsonify({'error': 'query is required'}), 400
    if omni_router is None:
        return jsonify({'error': 'OmniModelSingularity not loaded'}), 500
    try:
        response = omni_router.route_request(query)
        return jsonify(response.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/singularity/status', methods=['GET'])
def singularity_status():
    if omni_router is None:
        return jsonify({'error': 'OmniModelSingularity not loaded', 'status': 'offline'}), 500
    try:
        return jsonify(omni_router.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Unified Memory ────────────────────────────────────────────────────────────
# FIX [HIGH]: Catch all exceptions on init
try:
    from jarvis_brainiac.memory import UnifiedMemory
    unified_memory = UnifiedMemory(AGENCY)
except Exception:
    unified_memory = None


@app.route('/api/memory/remember', methods=['GET', 'POST', 'OPTIONS'])
def api_memory_remember():
    if request.method == 'OPTIONS':
        return '', 204
    if unified_memory is None:
        return jsonify({'error': 'UnifiedMemory not available'}), 500
    data = request.get_json(force=True, silent=True) or {}
    content = data.get('content', '')
    if not content:
        return jsonify({'error': 'content is required'}), 400
    try:
        entry = unified_memory.remember(data.get('kind', 'semantic'), content, data.get('tags', []))
        return jsonify(entry.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/memory/recall', methods=['GET', 'POST', 'OPTIONS'])
def api_memory_recall():
    if request.method == 'OPTIONS':
        return '', 204
    if unified_memory is None:
        return jsonify({'error': 'UnifiedMemory not available'}), 500
    data = request.get_json(force=True, silent=True) or {}
    query = data.get('query', '')
    if not query:
        return jsonify({'error': 'query is required'}), 400
    try:
        results = unified_memory.recall(query, limit=data.get('limit', 5))
        return jsonify([r.to_dict() for r in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    host = '127.0.0.1'
    port = int(os.environ.get('GODSKILL_PORT', 8765))
    print(f'GODSKILL Navigation Server running at http://{host}:{port}')
    app.config['AGENCY_ROOT'] = str(AGENCY)
    # FIX [HIGH]: Heartbeat wrapped — server starts even if heartbeat fails
    try:
        from jarvis_brainiac.heartbeat import start_heartbeat
        start_heartbeat(AGENCY, interval=300)
    except Exception as _hb_err:
        print(f'[WARNING] Heartbeat could not start: {_hb_err}')
    app.run(host=host, port=port, debug=False, use_reloader=False)
