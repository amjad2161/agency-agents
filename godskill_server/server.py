"""
GODSKILL Navigation Server — http://127.0.0.1:8765
Serves the 145-class navigation system via REST API.
"""
from __future__ import annotations
import os, sys
from pathlib import Path

AGENCY = Path(__file__).parent.parent
sys.path.insert(0, str(AGENCY / 'runtime'))
sys.path.insert(0, str(AGENCY))

from flask import Flask, jsonify, request

app = Flask('godskill')


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
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=short', '--timeout=30'],
        cwd=str(AGENCY),
        env={**os.environ, 'PYTHONPATH': str(AGENCY / 'runtime') + ':' + str(AGENCY)},
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
    body = {}
    try:
        body = request.get_json(force=True) or {}
    except Exception:
        pass
    original = str(body.get('message', '')).strip()
    msg = original.lower()

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
        lines_out = ['Navigation Modules:']
        for m, n in mods.items():
            lines_out.append('  {}: {} classes'.format(m, n))
        lines_out.append('\nTotal: {} classes'.format(sum(mods.values())))
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
                        all_cls.append('[{}] {}'.format(mod, cname))
        preview = all_cls[:30]
        text = 'Navigation Classes ({} total):\n'.format(len(all_cls))
        text += '\n'.join('  ' + c for c in preview)
        if len(all_cls) > 30:
            text += '\n  ... and {} more'.format(len(all_cls) - 30)
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


if __name__ == '__main__':
    host = '127.0.0.1'
    port = int(os.environ.get('GODSKILL_PORT', 8765))
    print('GODSKILL Navigation Server running at http://{}:{}'.format(host, port))
    print('Endpoints: /api/health  /api/run  /api/skills  /api/nav/status  /api/nav/classes')
    app.run(host=host, port=port, debug=False, use_reloader=False)
