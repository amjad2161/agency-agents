"""
Quick offline verification script — validates all new JARVIS modules without running a server.
Run: python tests/verify_offline.py
"""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = []

def check(label: str, fn):
    try:
        fn()
        results.append((True, label))
        print(f"  {PASS} {label}")
    except Exception as e:
        results.append((False, label))
        print(f"  {FAIL} {label}")
        print(f"    ERROR: {e}")
        traceback.print_exc()

print("\n━━━ FREE LLM ━━━")

def test_free_llm_import():
    from jarvis_brainiac.free_llm import FreeLLM, LLMResponse, SmartLocalProvider
    assert FreeLLM is not None

def test_free_llm_init():
    from jarvis_brainiac.free_llm import FreeLLM
    llm = FreeLLM()
    result = llm.initialize()
    assert isinstance(result, dict)
    assert "local" in result
    assert result["local"] is True  # SmartLocal always available

def test_free_llm_chat():
    from jarvis_brainiac.free_llm import FreeLLM
    llm = FreeLLM()
    llm.initialize()
    resp = llm.chat("hello")
    assert resp.text.strip() != ""
    assert resp.provider in ("ollama", "groq", "gemini", "huggingface", "local")

def test_free_llm_status():
    from jarvis_brainiac.free_llm import FreeLLM
    llm = FreeLLM()
    llm.initialize()
    s = llm.status()
    assert "primary" in s
    assert "available" in s
    assert "local" in s["available"]

def test_smart_local_greeting():
    from jarvis_brainiac.free_llm import SmartLocalProvider
    p = SmartLocalProvider()
    p.check()
    resp = p.chat([{"role": "user", "content": "hello"}])
    assert "service" in resp.text.lower() or "hello" in resp.text.lower()

def test_smart_local_time():
    from jarvis_brainiac.free_llm import SmartLocalProvider
    p = SmartLocalProvider()
    p.check()
    resp = p.chat([{"role": "user", "content": "what time is it?"}])
    assert "time" in resp.text.lower() or ":" in resp.text

def test_quick_chat():
    from jarvis_brainiac.free_llm import quick_chat
    result = quick_chat("hello")
    assert isinstance(result, str) and len(result) > 0

check("FreeLLM import", test_free_llm_import)
check("FreeLLM initialize() dict", test_free_llm_init)
check("FreeLLM chat() always returns", test_free_llm_chat)
check("FreeLLM status()", test_free_llm_status)
check("SmartLocal greeting", test_smart_local_greeting)
check("SmartLocal time query", test_smart_local_time)
check("quick_chat() convenience", test_quick_chat)

print("\n━━━ IDEA PIPELINE ━━━")

def test_pipeline_import():
    from jarvis_brainiac.idea_pipeline import IdeaPipeline, IdeaAnalyzer, AgentTeamBuilder, ProjectScaffolder

def test_pipeline_analyzer_saas():
    from jarvis_brainiac.idea_pipeline import IdeaAnalyzer
    a = IdeaAnalyzer()
    domains, ptype = a.analyze("Build a SaaS platform with React and FastAPI")
    assert len(domains) >= 1
    assert ptype in ("saas", "default", "api", "data")

def test_pipeline_analyzer_ecommerce():
    from jarvis_brainiac.idea_pipeline import IdeaAnalyzer
    a = IdeaAnalyzer()
    _, ptype = a.analyze("Online shop to sell products")
    assert ptype == "ecommerce"

def test_pipeline_team_builder():
    from jarvis_brainiac.idea_pipeline import AgentTeamBuilder
    b = AgentTeamBuilder()
    team = b.build_team(["frontend", "backend", "devops"])
    assert len(team) == 3
    for m in team:
        assert m.agent_name and m.domain and m.role
        assert m.maintenance_frequency in ("daily", "weekly", "monthly")

def test_pipeline_scaffolder():
    from jarvis_brainiac.idea_pipeline import ProjectScaffolder
    s = ProjectScaffolder()
    files, readme = s.scaffold("Task manager", "saas", ["frontend", "backend"])
    assert len(files) >= 3
    paths = [f.path for f in files]
    assert ".gitignore" in paths
    assert ".env.example" in paths
    assert len(readme) > 100

def test_pipeline_run():
    from jarvis_brainiac.idea_pipeline import IdeaPipeline
    p = IdeaPipeline()
    result = p.run("Build a SaaS for project management")
    assert result.run_id
    assert result.project_type
    assert len(result.team) >= 1
    assert len(result.scaffold) >= 3
    assert result.maintenance_plan

def test_pipeline_to_json():
    import json
    from jarvis_brainiac.idea_pipeline import IdeaPipeline
    p = IdeaPipeline()
    result = p.run("E-commerce shop")
    j = json.loads(result.to_json())
    assert j["project_type"] == "ecommerce"

def test_pipeline_write_disk(tmp_path=None):
    from jarvis_brainiac.idea_pipeline import IdeaPipeline
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = IdeaPipeline(output_base=Path(td))
        result = p.run("Portfolio site", write_to_disk=True)
        assert result.output_dir is not None
        out = Path(result.output_dir)
        assert (out / "README.md").exists()
        assert (out / ".gitignore").exists()

check("Pipeline import", test_pipeline_import)
check("Pipeline analyzer SaaS", test_pipeline_analyzer_saas)
check("Pipeline analyzer ecommerce", test_pipeline_analyzer_ecommerce)
check("Pipeline team builder (3 domains)", test_pipeline_team_builder)
check("Pipeline scaffolder generates files", test_pipeline_scaffolder)
check("Pipeline full run()", test_pipeline_run)
check("Pipeline to_json()", test_pipeline_to_json)
check("Pipeline write to disk", test_pipeline_write_disk)

print("\n━━━ 3D WEBSITE BUILDER ━━━")

def test_wb_import():
    from jarvis_brainiac.website_builder import (
        WebsiteBuilder, BriefParser, ThreeJSSceneBuilder, WebsiteAssembler, STYLE_PRESETS
    )
    assert len(STYLE_PRESETS) == 5

def test_wb_parser_luxury():
    from jarvis_brainiac.website_builder import BriefParser
    p = BriefParser()
    r = p.parse("luxury watch brand, dark, cinematic")
    assert r.style == "luxury"
    assert r.color_palette["bg"] == "#0a0a0a"
    assert r.hero_message

def test_wb_parser_tech():
    from jarvis_brainiac.website_builder import BriefParser
    p = BriefParser()
    r = p.parse("SaaS platform for developers, AI tools")
    assert r.style == "tech"
    assert r.scene_type == "particle_field"

def test_wb_all_scenes():
    from jarvis_brainiac.website_builder import ThreeJSSceneBuilder
    builder = ThreeJSSceneBuilder()
    for scene in ("floating_sphere", "particle_field", "geometric_morph", "liquid_glass"):
        js = builder.build(scene, "#00d4ff", "medium")
        assert "THREE" in js
        assert "animate" in js
        assert "renderer" in js

def test_wb_full_html():
    from jarvis_brainiac.website_builder import WebsiteBuilder
    wb = WebsiteBuilder()
    html, parsed = wb.build("luxury jewelry brand, gold, elegant")
    assert "<!DOCTYPE html>" in html
    assert "</html>" in html
    assert "three@" in html.lower() or "three.min.js" in html
    assert len(html) > 10000

def test_wb_all_styles():
    from jarvis_brainiac.website_builder import WebsiteBuilder, STYLE_PRESETS
    wb = WebsiteBuilder()
    for style in STYLE_PRESETS:
        html, parsed = wb.build("test brief", style_override=style)
        assert "<!DOCTYPE html>" in html, f"style {style} failed"
        assert parsed.style == style

def test_wb_write_disk():
    from jarvis_brainiac.website_builder import WebsiteBuilder
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        wb = WebsiteBuilder(output_dir=Path(td))
        html, parsed = wb.build("minimal portfolio")
        files = list(Path(td).glob("*.html"))
        assert len(files) == 1
        assert "<!DOCTYPE html>" in files[0].read_text(encoding="utf-8")

check("WebsiteBuilder import + 5 styles", test_wb_import)
check("BriefParser → luxury style", test_wb_parser_luxury)
check("BriefParser → tech style", test_wb_parser_tech)
check("ThreeJS all 4 scene types", test_wb_all_scenes)
check("Full HTML generation (>10KB)", test_wb_full_html)
check("All 5 styles generate valid HTML", test_wb_all_styles)
check("Write HTML to disk", test_wb_write_disk)

print("\n━━━ SERVER MODULE IMPORTS ━━━")

def test_server_can_import():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "server", ROOT / "godskill_server" / "server.py"
    )
    # We don't actually exec it (needs Flask app context), just check it's parseable
    import ast
    src = (ROOT / "godskill_server" / "server.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # Check all our new routes are present
    func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    required = [
        "api_pipeline_analyze", "api_pipeline_scaffold", "api_pipeline_maintenance",
        "api_website_brief", "api_website_generate", "api_website_templates",
        "api_llm_status", "api_llm_chat",
        "api_memory_remember", "api_memory_recall",
    ]
    for name in required:
        assert name in func_names, f"Missing route: {name}"

def test_jarvis_brainiac_parseable():
    import ast
    src = (ROOT / "JARVIS_BRAINIAC.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert "_free_llm_chat" in func_names
    assert "_god_mode_shell" in func_names
    assert "_smart_fallback" in func_names
    assert "_ollama" not in func_names
    assert "_claude" not in func_names

check("server.py AST parse + all routes present", test_server_can_import)
check("JARVIS_BRAINIAC.py AST parse clean", test_jarvis_brainiac_parseable)

print()
passed = sum(1 for ok, _ in results if ok)
total = len(results)
failed = [(label, ) for ok, label in results if not ok]

print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"  RESULTS: {passed}/{total} passed", end="")
if passed == total:
    print("  ✅ ALL PASS")
else:
    print(f"  ❌ {total - passed} FAILED")
    for (label,) in failed:
        print(f"    - {label}")
print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
sys.exit(0 if passed == total else 1)
