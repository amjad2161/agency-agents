"""
IdeaToAgents Pipeline — JARVIS BRAINIAC Capability 1
=====================================================
Inspired by: @_no_hype_ai — "AI pipeline that takes an idea input and ships
a full team of AI agents to build and maintain that project."

Pipeline:
    idea (str)
        → IdeaAnalyzer     — classify domains, extract keywords, detect type
        → AgentTeamBuilder — select optimal agents from registry per domain
        → ProjectScaffolder — generate file structure + README + requirements
        → MaintenancePlan  — assign recurring tasks per agent
        → PipelineResult   — store in UnifiedMemory + return to caller

No external API required — fully local, deterministic, instant.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# HR-005 FIX: cap idea string length to prevent regex DoS on huge inputs
MAX_IDEA_LENGTH = 2000

# ─── Domain keyword maps ──────────────────────────────────────────────────────

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "frontend": [
        "website", "landing page", "dashboard", "ui", "ux", "react", "vue",
        "next.js", "web app", "mobile app", "ios", "android", "flutter",
        "design", "interface", "3d", "animation", "portfolio",
    ],
    "backend": [
        "api", "server", "database", "backend", "microservice", "rest",
        "graphql", "auth", "authentication", "saas", "platform", "service",
        "fastapi", "flask", "django", "node", "express", "postgres", "mysql",
    ],
    "devops": [
        "deploy", "docker", "kubernetes", "ci/cd", "cloud", "aws", "gcp",
        "azure", "infrastructure", "scale", "monitoring", "devops", "pipeline",
        "nginx", "ssl", "domain", "hosting",
    ],
    "data": [
        "data", "analytics", "ml", "ai", "machine learning", "model",
        "dataset", "etl", "pipeline", "dashboard", "report", "visualization",
        "pandas", "spark", "bigquery", "warehouse",
    ],
    "marketing": [
        "marketing", "seo", "social media", "content", "growth", "viral",
        "launch", "go-to-market", "gtm", "email", "newsletter", "campaign",
        "landing page", "conversion", "funnel", "brand",
    ],
    "security": [
        "security", "auth", "oauth", "jwt", "encryption", "vulnerability",
        "pentest", "compliance", "gdpr", "hipaa", "audit", "firewall",
    ],
    "testing": [
        "test", "qa", "quality", "bug", "unit test", "e2e", "selenium",
        "pytest", "jest", "cypress", "coverage", "regression",
    ],
    "mobile": [
        "mobile", "ios", "android", "react native", "flutter", "swift",
        "kotlin", "app store", "push notification", "offline",
    ],
}

# Domain → best agent names from registry
DOMAIN_AGENTS: dict[str, list[str]] = {
    "frontend": ["frontend-developer", "ui-designer", "ux-architect", "rapid-prototyper"],
    "backend": ["backend-architect", "senior-developer", "database-optimizer"],
    "devops": ["devops-automator", "platform-engineer", "sre"],
    "data": ["data-engineer", "ai-engineer", "rag-engineer"],
    "marketing": ["content-creator", "growth-hacker", "twitter-engager", "brand-guardian"],
    "security": ["security-engineer", "llm-red-teamer", "privacy-engineer"],
    "testing": ["qa-engineer", "engineering-rapid-prototyper"],
    "mobile": ["mobile-app-builder", "frontend-developer"],
}

# Project type → file scaffold template name
PROJECT_TYPE_MAP: dict[str, str] = {
    "saas": "saas_web_app",
    "ecommerce": "ecommerce",
    "mobile": "mobile_app",
    "data": "data_pipeline",
    "api": "rest_api",
    "landing": "landing_page",
    "portfolio": "portfolio_site",
    "default": "saas_web_app",
}

# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class TeamMember:
    agent_name: str
    domain: str
    role: str
    responsibilities: list[str]
    maintenance_frequency: str  # daily | weekly | monthly


@dataclass
class ScaffoldFile:
    path: str           # relative to project root
    content: str        # file content
    description: str    # what this file does


@dataclass
class PipelineResult:
    run_id: str
    idea: str
    project_type: str
    domains: list[str]
    team: list[TeamMember]
    scaffold: list[ScaffoldFile]
    readme: str
    maintenance_plan: dict[str, list[str]]
    created_at: str
    output_dir: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ─── IdeaAnalyzer ─────────────────────────────────────────────────────────────

class IdeaAnalyzer:
    """Analyzes a natural-language idea and returns detected domains + project type."""

    def analyze(self, idea: str) -> tuple[list[str], str]:
        """Returns (detected_domains, project_type)."""
        # HR-005 FIX: cap input to prevent regex DoS
        idea = idea.strip()[:MAX_IDEA_LENGTH]
        idea_lower = idea.lower()
        detected: dict[str, int] = {}

        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in idea_lower)
            if score > 0:
                detected[domain] = score

        # Sort by score, take top domains
        sorted_domains = [d for d, _ in sorted(detected.items(), key=lambda x: -x[1])]

        # Always include at least frontend + backend if nothing detected
        if not sorted_domains:
            sorted_domains = ["frontend", "backend"]
        elif len(sorted_domains) == 1 and "frontend" not in sorted_domains:
            sorted_domains.append("backend")

        # Detect project type
        project_type = self._detect_type(idea_lower)
        log.debug("IdeaAnalyzer: domains=%s type=%s", sorted_domains, project_type)
        return sorted_domains, project_type

    def _detect_type(self, idea_lower: str) -> str:
        type_keywords = {
            "saas": ["saas", "subscription", "platform", "tool", "service"],
            "ecommerce": ["shop", "store", "ecommerce", "e-commerce", "sell", "buy", "marketplace"],
            "mobile": ["mobile", "ios", "android", "app"],
            "data": ["data", "analytics", "ml", "ai", "machine learning"],
            "api": ["api", "backend", "microservice", "rest"],
            "landing": ["landing page", "marketing site", "product page"],
            "portfolio": ["portfolio", "personal site", "showcase"],
        }
        for ptype, kws in type_keywords.items():
            if any(kw in idea_lower for kw in kws):
                return ptype
        return "default"


# ─── AgentTeamBuilder ─────────────────────────────────────────────────────────

class AgentTeamBuilder:
    """Selects the optimal agent team for detected domains."""

    ROLE_DESCRIPTIONS: dict[str, str] = {
        "frontend": "Frontend Lead — builds UI components, handles responsive design and 3D interactions",
        "backend": "Backend Architect — designs APIs, database schemas, and business logic",
        "devops": "DevOps Engineer — sets up CI/CD, Docker, deployment pipelines",
        "data": "Data Engineer — designs data models, ETL pipelines, and analytics",
        "marketing": "Growth Lead — SEO, content strategy, and launch campaigns",
        "security": "Security Engineer — auth flows, pen testing, compliance",
        "testing": "QA Engineer — writes tests, sets up coverage, regression testing",
        "mobile": "Mobile Developer — builds iOS/Android apps with offline support",
    }

    RESPONSIBILITIES: dict[str, list[str]] = {
        "frontend": [
            "Build component library and design system",
            "Implement responsive layouts and animations",
            "Ensure 60fps performance and Lighthouse score > 90",
            "Handle state management and routing",
        ],
        "backend": [
            "Design RESTful / GraphQL API",
            "Implement database schema and migrations",
            "Handle authentication and authorization",
            "Write API documentation",
        ],
        "devops": [
            "Set up Docker containers and Compose files",
            "Configure CI/CD pipeline (GitHub Actions)",
            "Manage environment variables and secrets",
            "Set up monitoring and alerting",
        ],
        "data": [
            "Design data warehouse schema",
            "Build ETL pipelines",
            "Create analytics dashboards",
            "Implement ML models as needed",
        ],
        "marketing": [
            "Write SEO-optimized copy",
            "Set up analytics tracking (GA4, Hotjar)",
            "Create social media content calendar",
            "Design email sequences",
        ],
        "security": [
            "Audit authentication flows",
            "Run dependency vulnerability scans",
            "Implement OWASP top-10 mitigations",
            "Set up security headers and CSP",
        ],
        "testing": [
            "Write unit tests (>80% coverage)",
            "Set up E2E tests with Playwright/Cypress",
            "Create regression test suite",
            "Implement load testing",
        ],
        "mobile": [
            "Build native iOS and Android apps",
            "Implement offline-first architecture",
            "Handle push notifications",
            "Submit to App Store and Google Play",
        ],
    }

    MAINTENANCE: dict[str, tuple[str, list[str]]] = {
        "frontend": ("weekly", ["Review UX metrics", "Update dependencies", "A/B test new variants"]),
        "backend": ("weekly", ["Monitor API performance", "Review error logs", "Optimize slow queries"]),
        "devops": ("daily", ["Check deployment health", "Review resource usage", "Rotate secrets quarterly"]),
        "data": ("weekly", ["Validate data pipeline integrity", "Update dashboards", "Retrain models monthly"]),
        "marketing": ("weekly", ["Publish content", "Review SEO rankings", "Analyze conversion funnels"]),
        "security": ("monthly", ["Run security audit", "Update CVE scanner", "Review access logs"]),
        "testing": ("weekly", ["Run regression suite", "Review flaky tests", "Update E2E scenarios"]),
        "mobile": ("weekly", ["Monitor crash reports", "Review App Store reviews", "Push hotfixes"]),
    }

    def build_team(self, domains: list[str]) -> list[TeamMember]:
        team: list[TeamMember] = []
        for domain in domains:
            agents = DOMAIN_AGENTS.get(domain, ["senior-developer"])
            agent_name = agents[0]
            freq, tasks = self.MAINTENANCE.get(domain, ("weekly", ["Perform maintenance"]))
            member = TeamMember(
                agent_name=agent_name,
                domain=domain,
                role=self.ROLE_DESCRIPTIONS.get(domain, "Domain Specialist"),
                responsibilities=self.RESPONSIBILITIES.get(domain, ["Handle domain-specific tasks"]),
                maintenance_frequency=freq,
            )
            team.append(member)
            log.debug("AgentTeamBuilder: added %s for domain %s", agent_name, domain)
        return team


# ─── ProjectScaffolder ────────────────────────────────────────────────────────

class ProjectScaffolder:
    """Generates a production-ready project scaffold based on idea and project type."""

    TECH_STACKS: dict[str, dict] = {
        "saas_web_app": {
            "frontend": "Next.js 14 + TypeScript + Tailwind CSS",
            "backend": "FastAPI + Python 3.11",
            "database": "PostgreSQL 16 + Prisma ORM",
            "auth": "NextAuth.js / Clerk",
            "deploy": "Vercel (frontend) + Railway (backend)",
        },
        "ecommerce": {
            "frontend": "Next.js 14 + TypeScript",
            "backend": "Node.js + Express",
            "database": "MongoDB + Mongoose",
            "payments": "Stripe",
            "deploy": "Vercel + MongoDB Atlas",
        },
        "mobile_app": {
            "mobile": "React Native + Expo",
            "backend": "Node.js + Express",
            "database": "PostgreSQL + Supabase",
            "auth": "Supabase Auth",
            "deploy": "Expo EAS + Railway",
        },
        "data_pipeline": {
            "pipeline": "Apache Airflow + Python",
            "storage": "Google BigQuery / AWS S3",
            "processing": "Pandas + Spark",
            "visualization": "Metabase / Grafana",
            "deploy": "GCP / AWS",
        },
        "rest_api": {
            "backend": "FastAPI + Python 3.11",
            "database": "PostgreSQL 16",
            "auth": "JWT + OAuth2",
            "docs": "Swagger / Redoc",
            "deploy": "Docker + Railway",
        },
        "landing_page": {
            "frontend": "HTML + CSS + Vanilla JS",
            "hosting": "Vercel / Netlify",
            "analytics": "GA4 + Hotjar",
            "forms": "Formspree / Resend",
            "deploy": "GitHub Pages / Vercel",
        },
        "portfolio_site": {
            "frontend": "Next.js + Three.js",
            "hosting": "Vercel",
            "cms": "Contentful / Sanity",
            "deploy": "Vercel",
        },
    }

    def scaffold(self, idea: str, project_type: str, domains: list[str]) -> tuple[list[ScaffoldFile], str]:
        """Returns (scaffold_files, readme_content)."""
        template_name = PROJECT_TYPE_MAP.get(project_type, "saas_web_app")
        stack = self.TECH_STACKS.get(template_name, self.TECH_STACKS["saas_web_app"])
        files = self._generate_files(idea, template_name, stack, domains)
        readme = self._generate_readme(idea, project_type, stack, domains)
        return files, readme

    def _generate_files(self, idea: str, template: str, stack: dict, domains: list[str]) -> list[ScaffoldFile]:
        files: list[ScaffoldFile] = []

        # Always include these
        files.append(ScaffoldFile(
            path=".env.example",
            content=self._env_example(stack),
            description="Environment variables template",
        ))
        files.append(ScaffoldFile(
            path=".gitignore",
            content=self._gitignore(),
            description="Standard gitignore",
        ))
        files.append(ScaffoldFile(
            path="docker-compose.yml",
            content=self._docker_compose(stack),
            description="Local development Docker Compose",
        ))

        if "frontend" in domains or template in ("saas_web_app", "landing_page", "portfolio_site"):
            files.append(ScaffoldFile(
                path="frontend/package.json",
                content=self._package_json(idea, stack),
                description="Frontend package.json with dependencies",
            ))

        if "backend" in domains or template in ("saas_web_app", "rest_api"):
            files.append(ScaffoldFile(
                path="backend/requirements.txt",
                content=self._requirements_txt(stack),
                description="Python backend dependencies",
            ))
            files.append(ScaffoldFile(
                path="backend/main.py",
                content=self._fastapi_main(idea),
                description="FastAPI application entry point",
            ))

        if "devops" in domains:
            files.append(ScaffoldFile(
                path=".github/workflows/ci.yml",
                content=self._github_actions_ci(),
                description="GitHub Actions CI/CD pipeline",
            ))

        if "testing" in domains:
            files.append(ScaffoldFile(
                path="tests/test_api.py",
                content=self._test_template(idea),
                description="Starter test suite",
            ))

        return files

    def _env_example(self, stack: dict) -> str:
        lines = [
            "# Environment Variables — copy to .env and fill in values",
            "NODE_ENV=development",
            "DATABASE_URL=postgresql://user:password@localhost:5432/db",
            "SECRET_KEY=your-secret-key-here",
            "NEXTAUTH_SECRET=your-nextauth-secret",
            "NEXTAUTH_URL=http://localhost:3000",
        ]
        if "payments" in stack:
            lines += ["STRIPE_SECRET_KEY=sk_test_...", "STRIPE_PUBLISHABLE_KEY=pk_test_..."]
        return "\n".join(lines)

    def _gitignore(self) -> str:
        return "\n".join([
            "node_modules/", ".env", ".env.local", "__pycache__/", "*.pyc",
            ".venv/", "dist/", "build/", ".next/", ".DS_Store", "*.log",
            "coverage/", ".pytest_cache/",
        ])

    def _docker_compose(self, stack: dict) -> str:
        return """version: '3.9'
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
"""

    def _package_json(self, idea: str, stack: dict) -> str:
        name = re.sub(r"[^a-z0-9-]", "-", idea.lower()[:30]).strip("-")
        return json.dumps({
            "name": name,
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "start": "next start",
                "lint": "next lint",
                "test": "jest",
            },
            "dependencies": {
                "next": "14.2.0",
                "react": "^18.3.0",
                "react-dom": "^18.3.0",
                "typescript": "^5.4.0",
            },
        }, indent=2)

    def _requirements_txt(self, stack: dict) -> str:
        return "\n".join([
            "fastapi>=0.110.0",
            "uvicorn[standard]>=0.29.0",
            "pydantic>=2.7.0",
            "sqlalchemy>=2.0.0",
            "alembic>=1.13.0",
            "python-dotenv>=1.0.0",
            "httpx>=0.27.0",
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0",
        ])

    def _fastapi_main(self, idea: str) -> str:
        return f'''"""
{idea}
Auto-generated by JARVIS BRAINIAC IdeaToAgents Pipeline.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="{idea[:50]}",
    version="0.1.0",
    description="Auto-generated API — fill in your business logic here.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {{"status": "ok", "version": "0.1.0"}}

@app.get("/")
async def root():
    return {{"message": "Welcome to your JARVIS-generated API"}}
'''

    def _github_actions_ci(self) -> str:
        return """name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r backend/requirements.txt
      - run: pytest tests/ -v

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: cd frontend && npm ci && npm run lint
"""

    def _test_template(self, idea: str) -> str:
        return f'''"""Starter test suite for: {idea[:60]}"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
'''

    def _generate_readme(self, idea: str, project_type: str, stack: dict, domains: list[str]) -> str:
        stack_lines = "\n".join(f"- **{k.title()}**: {v}" for k, v in stack.items())
        domain_lines = "\n".join(f"- {d.title()}" for d in domains)
        return f"""# {idea}

> Auto-generated by **JARVIS BRAINIAC IdeaToAgents Pipeline**
> Project type: `{project_type}`

## Tech Stack
{stack_lines}

## Domains Covered
{domain_lines}

## Quick Start

```bash
# Clone and setup
git clone <your-repo>
cp .env.example .env
# Fill in .env values

# Start services
docker-compose up -d

# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload
```

## Project Structure

```
├── frontend/          # UI application
├── backend/           # API server
├── tests/             # Test suite
├── .github/workflows/ # CI/CD
├── docker-compose.yml # Local dev
└── README.md
```

## Generated by JARVIS BRAINIAC
This project was scaffolded automatically. Customize each section for your specific needs.
"""


# ─── IdeaPipeline (orchestrator) ─────────────────────────────────────────────

class IdeaPipeline:
    """
    Main entry point: takes an idea string, runs the full pipeline,
    optionally writes scaffold to disk, and returns a PipelineResult.
    """

    def __init__(self, output_base: Optional[Path] = None):
        self.output_base = output_base
        self.analyzer = IdeaAnalyzer()
        self.team_builder = AgentTeamBuilder()
        self.scaffolder = ProjectScaffolder()

    def run(self, idea: str, write_to_disk: bool = False) -> PipelineResult:
        """Run the full pipeline for the given idea."""
        # HR-005 FIX: cap idea length
        idea = idea.strip()[:MAX_IDEA_LENGTH]
        # LR-006 FIX: deterministic run_id based on idea hash (reproducible in tests)
        idea_hash = hashlib.md5(idea.encode(), usedforsecurity=False).hexdigest()[:8]
        run_id = idea_hash
        log.info("IdeaPipeline: starting run_id=%s idea=%r", run_id, idea[:60])

        # 1. Analyze
        domains, project_type = self.analyzer.analyze(idea)

        # 2. Build team
        team = self.team_builder.build_team(domains)

        # 3. Scaffold
        scaffold_files, readme = self.scaffolder.scaffold(idea, project_type, domains)

        # 4. Maintenance plan
        maintenance: dict[str, list[str]] = {}
        for member in team:
            freq, tasks = self.team_builder.MAINTENANCE.get(member.domain, ("weekly", []))
            key = f"{member.agent_name} ({freq})"
            maintenance[key] = tasks

        result = PipelineResult(
            run_id=run_id,
            idea=idea,
            project_type=project_type,
            domains=domains,
            team=team,
            scaffold=scaffold_files,
            readme=readme,
            maintenance_plan=maintenance,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 5. Write to disk (optional)
        if write_to_disk and self.output_base:
            result.output_dir = self._write_scaffold(result)

        log.info(
            "IdeaPipeline: done run_id=%s type=%s domains=%s agents=%d files=%d",
            run_id, project_type, domains, len(team), len(scaffold_files)
        )
        return result

    def _write_scaffold(self, result: PipelineResult) -> str:
        """Write scaffold files to disk under output_base/<run_id>/."""
        # HR-007 guard: sanitize project name to prevent path traversal
        project_name = re.sub(r"[^a-z0-9_-]", "_", result.idea.lower()[:30]).strip("_")
        project_dir = (self.output_base / f"{project_name}_{result.run_id}").resolve()
        # Ensure project_dir is inside output_base (path traversal guard)
        if not str(project_dir).startswith(str(self.output_base.resolve())):
            raise ValueError(f"Path traversal detected: {project_dir}")
        project_dir.mkdir(parents=True, exist_ok=True)

        for sf in result.scaffold:
            # LR-007 FIX: sanitize paths within scaffold to prevent traversal
            safe_path = Path(sf.path)
            if safe_path.is_absolute() or ".." in safe_path.parts:
                log.warning("IdeaPipeline: skipping unsafe scaffold path: %s", sf.path)
                continue
            fpath = project_dir / safe_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(sf.content, encoding="utf-8")

        (project_dir / "README.md").write_text(result.readme, encoding="utf-8")
        (project_dir / "jarvis_pipeline.json").write_text(result.to_json(), encoding="utf-8")

        # MR-011 FIX: git init the scaffolded project
        try:
            subprocess.run(
                ["git", "init", "--initial-branch=main"],
                cwd=str(project_dir), capture_output=True, timeout=10
            )
            # Create initial .gitignore-based commit
            subprocess.run(["git", "add", "-A"], cwd=str(project_dir),
                           capture_output=True, timeout=10)
            subprocess.run(
                ["git", "commit", "-m", f"feat: scaffold {project_name} via JARVIS IdeaToAgents"],
                cwd=str(project_dir), capture_output=True, timeout=10
            )
            log.info("IdeaPipeline: git repo initialized at %s", project_dir)
        except Exception as e:
            log.warning("IdeaPipeline: git init failed (non-fatal): %s", e)

        log.info("IdeaPipeline: scaffold written to %s", project_dir)
        return str(project_dir)
