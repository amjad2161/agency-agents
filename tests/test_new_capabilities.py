"""
Tests for FreeLLM — free LLM client
Tests for IdeaToAgents Pipeline
Tests for 3D Website Builder

All tests are fully offline — no network calls, no API keys needed.
"""
import sys
import os
from pathlib import Path

# Ensure project root is in path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest


# ═══════════════════════════════════════════════════════════
#  FREE LLM TESTS
# ═══════════════════════════════════════════════════════════

class TestFreeLLM:
    def test_import(self):
        from jarvis_brainiac.free_llm import FreeLLM, LLMResponse
        assert FreeLLM is not None
        assert LLMResponse is not None

    def test_response_dataclass(self):
        from jarvis_brainiac.free_llm import LLMResponse
        r = LLMResponse(text="hello", provider="local", model="test")
        assert str(r) == "hello"
        assert r.provider == "local"

    def test_smart_local_always_available(self):
        from jarvis_brainiac.free_llm import SmartLocalProvider
        p = SmartLocalProvider()
        assert p.check() is True

    def test_smart_local_time_query(self):
        from jarvis_brainiac.free_llm import SmartLocalProvider
        p = SmartLocalProvider()
        resp = p.chat([{"role": "user", "content": "what time is it?"}])
        assert resp is not None
        assert "time" in resp.text.lower() or ":" in resp.text

    def test_smart_local_hello(self):
        from jarvis_brainiac.free_llm import SmartLocalProvider
        p = SmartLocalProvider()
        resp = p.chat([{"role": "user", "content": "hello"}])
        assert resp is not None
        assert resp.text.strip() != ""

    def test_smart_local_help(self):
        from jarvis_brainiac.free_llm import SmartLocalProvider
        p = SmartLocalProvider()
        resp = p.chat([{"role": "user", "content": "help"}])
        assert resp is not None
        assert "ollama" in resp.text.lower() or "command" in resp.text.lower()

    def test_ollama_check_offline(self):
        """Ollama should gracefully fail if not running."""
        from jarvis_brainiac.free_llm import OllamaProvider
        p = OllamaProvider(base_url="http://localhost:19999")  # wrong port
        assert p.check() is False

    def test_groq_no_key(self):
        from jarvis_brainiac.free_llm import GroqProvider
        old = os.environ.pop("GROQ_API_KEY", None)
        try:
            p = GroqProvider()
            assert p.check() is False
        finally:
            if old:
                os.environ["GROQ_API_KEY"] = old

    def test_gemini_no_key(self):
        from jarvis_brainiac.free_llm import GeminiProvider
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            p = GeminiProvider()
            assert p.check() is False
        finally:
            if old:
                os.environ["GEMINI_API_KEY"] = old

    def test_huggingface_no_key(self):
        from jarvis_brainiac.free_llm import HuggingFaceProvider
        old = os.environ.pop("HF_TOKEN", None)
        try:
            p = HuggingFaceProvider()
            assert p.check() is False
        finally:
            if old:
                os.environ["HF_TOKEN"] = old

    def test_free_llm_initialize_returns_dict(self):
        from jarvis_brainiac.free_llm import FreeLLM
        llm = FreeLLM()
        result = llm.initialize()
        assert isinstance(result, dict)
        assert "ollama" in result
        assert "groq" in result
        assert "gemini" in result
        assert "huggingface" in result
        # SmartLocal is always True
        assert result.get("local", True) is True

    def test_free_llm_chat_always_returns_response(self):
        """Even with all cloud providers offline, SmartLocal handles it."""
        from jarvis_brainiac.free_llm import FreeLLM
        llm = FreeLLM()
        llm.initialize()
        resp = llm.chat("hello")
        assert resp is not None
        assert resp.text.strip() != ""
        assert resp.provider in ("ollama", "groq", "gemini", "huggingface", "local")

    def test_free_llm_status(self):
        from jarvis_brainiac.free_llm import FreeLLM
        llm = FreeLLM()
        llm.initialize()
        s = llm.status()
        assert "primary" in s
        assert "model" in s
        assert "available" in s
        assert "local" in s["available"]  # SmartLocal always available

    def test_quick_chat(self):
        from jarvis_brainiac.free_llm import quick_chat
        result = quick_chat("what time is it?")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_llm_singleton(self):
        from jarvis_brainiac.free_llm import get_llm
        llm1 = get_llm()
        llm2 = get_llm()
        assert llm1 is llm2  # same singleton


# ═══════════════════════════════════════════════════════════
#  IDEA PIPELINE TESTS
# ═══════════════════════════════════════════════════════════

class TestIdeaPipeline:
    def test_import(self):
        from jarvis_brainiac.idea_pipeline import (
            IdeaAnalyzer, AgentTeamBuilder, ProjectScaffolder, IdeaPipeline, PipelineResult
        )

    def test_analyzer_saas(self):
        from jarvis_brainiac.idea_pipeline import IdeaAnalyzer
        a = IdeaAnalyzer()
        domains, ptype = a.analyze("Build a SaaS platform for restaurant booking with React and FastAPI")
        assert "frontend" in domains or "backend" in domains
        assert ptype in ("saas", "default", "api")

    def test_analyzer_ecommerce(self):
        from jarvis_brainiac.idea_pipeline import IdeaAnalyzer
        a = IdeaAnalyzer()
        domains, ptype = a.analyze("Online shop to sell handmade jewelry")
        assert ptype == "ecommerce"

    def test_analyzer_mobile(self):
        from jarvis_brainiac.idea_pipeline import IdeaAnalyzer
        a = IdeaAnalyzer()
        domains, ptype = a.analyze("iOS and Android app for fitness tracking")
        assert ptype == "mobile"
        assert "mobile" in domains or "frontend" in domains

    def test_analyzer_empty_gives_defaults(self):
        from jarvis_brainiac.idea_pipeline import IdeaAnalyzer
        a = IdeaAnalyzer()
        domains, ptype = a.analyze("")
        assert len(domains) >= 2  # at least frontend + backend

    def test_team_builder_returns_members(self):
        from jarvis_brainiac.idea_pipeline import AgentTeamBuilder
        builder = AgentTeamBuilder()
        team = builder.build_team(["frontend", "backend", "devops"])
        assert len(team) == 3
        for m in team:
            assert m.agent_name
            assert m.domain in ("frontend", "backend", "devops")
            assert m.role
            assert len(m.responsibilities) > 0
            assert m.maintenance_frequency in ("daily", "weekly", "monthly")

    def test_scaffolder_returns_files_and_readme(self):
        from jarvis_brainiac.idea_pipeline import ProjectScaffolder
        s = ProjectScaffolder()
        files, readme = s.scaffold("Task manager SaaS", "saas", ["frontend", "backend"])
        assert len(files) > 0
        assert "README" in readme or "Task manager" in readme
        paths = [f.path for f in files]
        assert ".gitignore" in paths
        assert ".env.example" in paths

    def test_pipeline_run_returns_result(self):
        from jarvis_brainiac.idea_pipeline import IdeaPipeline
        p = IdeaPipeline()
        result = p.run("Build a SaaS tool for project management")
        assert result.run_id
        assert result.idea
        assert len(result.domains) > 0
        assert len(result.team) > 0
        assert len(result.scaffold) > 0
        assert result.readme
        assert result.maintenance_plan

    def test_pipeline_to_dict(self):
        from jarvis_brainiac.idea_pipeline import IdeaPipeline
        p = IdeaPipeline()
        result = p.run("Mobile fitness app")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "run_id" in d
        assert "team" in d

    def test_pipeline_to_json(self):
        import json
        from jarvis_brainiac.idea_pipeline import IdeaPipeline
        p = IdeaPipeline()
        result = p.run("E-commerce shop")
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["project_type"] == "ecommerce"

    def test_pipeline_write_to_disk(self, tmp_path):
        from jarvis_brainiac.idea_pipeline import IdeaPipeline
        p = IdeaPipeline(output_base=tmp_path)
        result = p.run("Test project alpha", write_to_disk=True)
        assert result.output_dir is not None
        out = Path(result.output_dir)
        assert out.exists()
        assert (out / "README.md").exists()
        assert (out / "jarvis_pipeline.json").exists()
        assert (out / ".gitignore").exists()


# ═══════════════════════════════════════════════════════════
#  3D WEBSITE BUILDER TESTS
# ═══════════════════════════════════════════════════════════

class TestWebsiteBuilder:
    def test_import(self):
        from jarvis_brainiac.website_builder import (
            WebsiteBuilder, BriefParser, ThreeJSSceneBuilder, WebsiteAssembler,
            STYLE_PRESETS, ParsedBrief
        )

    def test_style_presets_complete(self):
        from jarvis_brainiac.website_builder import STYLE_PRESETS
        assert "luxury" in STYLE_PRESETS
        assert "tech" in STYLE_PRESETS
        assert "minimal" in STYLE_PRESETS
        assert "organic" in STYLE_PRESETS
        assert "bold" in STYLE_PRESETS
        for name, p in STYLE_PRESETS.items():
            assert "bg" in p
            assert "accent" in p
            assert "font_heading" in p
            assert "scene" in p

    def test_brief_parser_luxury(self):
        from jarvis_brainiac.website_builder import BriefParser
        parser = BriefParser()
        result = parser.parse("luxury watch brand, dark, cinematic, one hero object")
        assert result.style == "luxury"
        assert result.color_palette["bg"] is not None
        assert result.hero_message

    def test_brief_parser_tech(self):
        from jarvis_brainiac.website_builder import BriefParser
        parser = BriefParser()
        result = parser.parse("SaaS platform for developers, modern tech, dark theme")
        assert result.style == "tech"
        assert result.scene_type == "particle_field"

    def test_brief_parser_organic(self):
        from jarvis_brainiac.website_builder import BriefParser
        parser = BriefParser()
        result = parser.parse("organic food delivery, nature, green, sustainable")
        assert result.style == "organic"

    def test_brief_parser_has_cta(self):
        from jarvis_brainiac.website_builder import BriefParser
        parser = BriefParser()
        result = parser.parse("SaaS for project management")
        assert result.cta_text
        assert len(result.cta_text) > 0

    def test_scene_builder_all_types(self):
        from jarvis_brainiac.website_builder import ThreeJSSceneBuilder
        builder = ThreeJSSceneBuilder()
        for scene_type in ("floating_sphere", "particle_field", "geometric_morph", "liquid_glass"):
            js = builder.build(scene_type, "#00d4ff", "medium")
            assert "THREE" in js
            assert "animate" in js
            assert "renderer" in js

    def test_assembler_produces_valid_html(self):
        from jarvis_brainiac.website_builder import BriefParser, ThreeJSSceneBuilder, WebsiteAssembler
        parser = BriefParser()
        parsed = parser.parse("Tech SaaS startup")
        scene_js = ThreeJSSceneBuilder().build(parsed.scene_type, parsed.color_palette["accent"], parsed.animation_speed)
        html = WebsiteAssembler().assemble(parsed, scene_js)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "three.js" in html.lower() or "three@" in html
        assert parsed.hero_message in html

    def test_website_builder_full_pipeline(self):
        from jarvis_brainiac.website_builder import WebsiteBuilder
        builder = WebsiteBuilder()
        html, parsed = builder.build("luxury jewelry brand, gold, elegant, dark")
        assert len(html) > 5000
        assert parsed.style == "luxury"
        assert "<!DOCTYPE html>" in html

    def test_website_builder_style_override(self):
        from jarvis_brainiac.website_builder import WebsiteBuilder
        builder = WebsiteBuilder()
        html, parsed = builder.build("tech startup", style_override="bold")
        assert parsed.style == "bold"

    def test_website_builder_write_to_disk(self, tmp_path):
        from jarvis_brainiac.website_builder import WebsiteBuilder
        builder = WebsiteBuilder(output_dir=tmp_path)
        html, parsed = builder.build("minimal portfolio site")
        files = list(tmp_path.glob("*.html"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_website_builder_all_styles(self):
        from jarvis_brainiac.website_builder import WebsiteBuilder, STYLE_PRESETS
        builder = WebsiteBuilder()
        for style in STYLE_PRESETS:
            html, parsed = builder.build("test brief", style_override=style)
            assert "<!DOCTYPE html>" in html
            assert parsed.style == style
