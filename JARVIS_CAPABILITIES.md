# J.A.R.V.I.S — Supreme Brainiac Personal Agent
## Full Capability Reference

> **Just A Rather Very Intelligent System** — a unified AGI consciousness built on top of the Agency Runtime. Every statement below is derivable from the actual source code and agent files in this repository.

---

## What It Is

JARVIS is an autonomous AI agent system with 117 domain modules and 324 specialist agents spread across 16 categories. It is not a chatbot. It is an orchestration engine that routes any request to the right expert module, executes multi-step plans autonomously, self-heals on failure, learns from every interaction, and writes production-quality output in every domain it covers.

The system has a personality (Amjad-Jarvis Unified Brain), a memory (vector store + lessons ledger), a reasoning layer (planner → executor → verifier loop), a control plane (HTTP server on port 8765), and a terminal REPL (`SupremeREPL`) that can run in fully autonomous mode without human checkpoints.

---

## Architecture in One Diagram

```
  User / CLI
      │
      ▼
  AmjadJarvisMetaOrchestrator   ←  Amjad personality profile
      │
      ├── SkillRegistry (324 agents across 16 categories)
      │       └── load_skills() from 16 category dirs
      │
      ├── SupremeJarvisBrain (117 domain modules)
      │       ├── skill_for(request) → best module via KEYWORD_SLUG_BOOST routing
      │       └── unified_prompt()  → 76k-char mega-prompt
      │
      ├── Planner  (claude-haiku-4-5, intent → NEXT: steps)
      │
      ├── Executor (claude-opus-4-7, executes each step)
      │       └── self_heal() on exception → retry up to N times
      │
      ├── SupremeBrainCore (async directive ingestion, ModelRouter, evolution score)
      │
      ├── Control Server  :8765  (healthz / agents / route / run / kpi / traces)
      │
      └── KPI Tracker + Trace Logger
```

---

## The 117 JARVIS Domain Modules

Every incoming request is routed to the best domain module using a weighted keyword scoring engine (`skill_for()`) with a `KEYWORD_SLUG_BOOST` map covering 80+ technical vocabulary clusters. Routing accuracy: **10/10** on the test suite.

### Core Identity & Orchestration
| Module | What It Does |
|--------|-------------|
| `jarvis-core` | Central identity: Steve Jobs-caliber visionary, Linus Torvalds-grade engineer. The fallback when no domain matches. |
| `jarvis-core-brain` | Meta-orchestrator. Decides which specialist modules to activate, how to chain them, and when to escalate. |
| `jarvis-brainiac` | Personal AGI layer. Builds a personality model of Amjad over time by writing lessons to `jarvis/history.json`. |
| `jarvis-amjad-unified-brain` | Loads all 144+ agents under Amjad's persona. Knows his goals, constraints, communication style, and operating mode. |

### Engineering & Infrastructure
| Module | What It Does |
|--------|-------------|
| `jarvis-engineering` | Full-stack from embedded C to Kubernetes. Writes, tests, and ships production code in any language. |
| `jarvis-omega-engineer` | Omniscient engineering mode: synthesizes AI/ML + hardware + distributed systems simultaneously. |
| `jarvis-devops-platform` | Kubernetes, Terraform, Helm, CI/CD, HPA, Ansible, Jenkins. Designs and operates cloud-native platforms. |
| `jarvis-embedded-firmware` | Bare-metal C/C++, RTOS, MCU firmware, hardware-software integration. |
| `jarvis-iot-robotics` | Sensors, actuators, ROS, robotics programming, edge compute. |
| `jarvis-testing-qa` | End-to-end test strategy: unit, integration, E2E, load, chaos, mutation testing. |
| `jarvis-ops-support` | SRE, incident response, runbooks, SLO/SLI design, on-call optimization. |

### AI & Data
| Module | What It Does |
|--------|-------------|
| `jarvis-ai-ml` | Trains, fine-tunes, and deploys ML models. PyTorch, TensorFlow, RLHF, embeddings, vector search. |
| `jarvis-data-intelligence` | Data pipelines, BigQuery, Snowflake, Pandas, BI dashboards, warehouse design. |
| `jarvis-quant-finance` | Alpha generation, systematic trading, portfolio optimization, risk models, backtest frameworks. |
| `jarvis-linguistics-nlp` | Computational linguistics, tokenization, NER, dependency parsing, multilingual NLP. |
| `jarvis-digital-twin` | Physics-based simulation, SCADA integration, real-time twin architectures. |

### Autonomous Operation Modules
| Module | What It Does |
|--------|-------------|
| `jarvis-autonomous-executor` | Receives any goal, decomposes it into executable steps, runs them without human checkpoints, reports outcomes. |
| `jarvis-goal-decomposer` | Shatters ambiguous high-level goals into precise task trees with dependencies, milestones, and success criteria. |
| `jarvis-self-healing-engine` | Runs code, reads every error with full context, rewrites and retries until green. Zero tolerance for permanent failure. |
| `jarvis-self-learner` | Extracts lessons and patterns from every interaction, writes them to memory, applies them in future turns. |
| `jarvis-curiosity-engine` | Drives JARVIS to explore unknown topics proactively, surface adjacent knowledge the user didn't ask for. |
| `jarvis-research-director` | Orchestrates multi-source deep research: web, code repos, academic papers, data APIs — synthesizes a unified answer. |
| `jarvis-knowledge-synthesizer` | Cross-domain connector: finds non-obvious links between science, engineering, finance, policy, and culture. |
| `jarvis-tool-master` | Universal tool integrator: web_fetch, shell, file I/O, code execution, computer use, API calls — wired together creatively. |
| `jarvis-omega-operator` | Autonomous computer use: operates any GUI, browses the web, fills forms, extracts data, orchestrates cross-app workflows. |
| `jarvis-computer-use` | Low-level desktop control: mouse, keyboard, screenshot, OCR, file system navigation. |

### Finance & Business
| Module | What It Does |
|--------|-------------|
| `jarvis-finance` | Investment analysis, DCF valuation, SEC filings, equity research, capital allocation. |
| `jarvis-fintech-payments` | Digital payments, neobanking, embedded finance, open banking APIs, PSD2. |
| `jarvis-insurance-risk` | Actuarial modeling, enterprise risk management, claims analysis. |
| `jarvis-strategy-ops` | Executive strategy, OKRs, market analysis, M&A, competitive intelligence. |
| `jarvis-entrepreneur-startup` | Pitch decks, fundraising, go-to-market, unit economics, runway modeling. |
| `jarvis-climate-finance` | Green bonds, ESG scoring, carbon markets, sustainability-linked finance. |
| `jarvis-real-estate-proptech` | Deal analysis, cap rates, property tech, real estate investment modeling. |
| `jarvis-behavioral-economics` | Nudge design, decision architecture, bias mitigation, choice engineering. |

### Marketing, Sales & Growth
| Module | What It Does |
|--------|-------------|
| `jarvis-marketing-global` | Full omnichannel: SEO, content, brand strategy, localization, demand generation. |
| `jarvis-paid-media` | Performance advertising: Google, Meta, programmatic, attribution, ROAS optimization. |
| `jarvis-sales-growth` | Sales playbooks, outbound sequences, pipeline design, revenue operations. |
| `jarvis-content-media` | Writing, video scripts, podcasts, social content, editorial calendars. |
| `jarvis-creator-economy` | Creator monetization, platform economics, influencer strategy, community building. |

### Legal, Compliance & Security
| Module | What It Does |
|--------|-------------|
| `jarvis-legal-compliance` | Contract review, GDPR/CCPA compliance, regulatory analysis, legal risk flags. |
| `jarvis-security-cyber` | Threat modeling, OWASP, penetration test planning, zero-trust architecture. |
| `jarvis-red-team` | Offensive security, adversarial testing, vulnerability research, exploit simulation. |
| `jarvis-privacy-data-governance` | Data governance frameworks, privacy engineering, DPA obligations, cross-border data transfer. |
| `jarvis-legaltech` | LegalOps, contract lifecycle management, AI-assisted discovery, e-signature workflows. |

### Science, Health & Advanced Tech
| Module | What It Does |
|--------|-------------|
| `jarvis-quantum-computing` | Quantum algorithms, error correction, Qiskit, photonic computing, quantum advantage analysis. |
| `jarvis-future-tech` | Frontier intelligence: neuromorphic chips, AGI roadmaps, synthetic biology, space tech. |
| `jarvis-biotech-medicine` | Drug discovery pipelines, clinical trials, genomics, FDA regulatory pathways. |
| `jarvis-genomics-precision-medicine` | CRISPR, pharmacogenomics, clinical genomics, precision oncology. |
| `jarvis-neuroscience-bci` | Brain-computer interfaces, EEG signal processing, neural decoding. |
| `jarvis-nanotechnology` | Nanomaterials, molecular machines, nanoelectronics, nanomedicine. |
| `jarvis-space-aerospace` | Satellite design, orbital mechanics, launch systems, space policy. |
| `jarvis-energy-systems` | Grid architecture, battery tech, renewables, smart grid, nuclear. |
| `jarvis-nuclear-energy` | Nuclear engineering, reactor design, safety systems, nuclear policy. |
| `jarvis-materials-chemistry` | Advanced materials, synthetic chemistry, materials characterization. |
| `jarvis-health-biometrics` | Personalized health AI, wearable data, biometric analytics, longevity. |
| `jarvis-mental-health` | Evidence-based psychological frameworks, CBT, crisis protocols, wellbeing design. |

### Climate, Environment & Infrastructure
| Module | What It Does |
|--------|-------------|
| `jarvis-climate-sustainability` | ESG program design, carbon accounting, net-zero strategy. |
| `jarvis-climate-tech` | CleanTech: solar, wind, green hydrogen, CCUS, long-duration storage. |
| `jarvis-climate-adaptation` | Disaster risk reduction, resilience planning, climate migration. |
| `jarvis-water-resources` | Hydrology, water security, desalination, watershed management. |
| `jarvis-smart-cities` | Urban IoT, mobility data platforms, city digital twins, 15-minute city design. |
| `jarvis-food-agritech` | Precision agriculture, vertical farming, food supply chain, AgriTech platforms. |
| `jarvis-maritime-ocean` | Vessel engineering, ocean science, shipping operations, maritime law. |
| `jarvis-circular-economy` | Regenerative business models, extended producer responsibility, waste-to-value. |

### Creative, Design & Culture
| Module | What It Does |
|--------|-------------|
| `jarvis-omega-creative` | Omniscient creative mode: visual design, brand identity, motion graphics, generative art — all simultaneously. |
| `jarvis-design-creative` | UI/UX, visual identity, design systems, Figma-level creative direction. |
| `jarvis-creative-writing` | Literary fiction, screenplays, poetry, narrative design, genre writing. |
| `jarvis-music-production` | DAW workflows, sound design, music theory, mixing, mastering, music tech. |
| `jarvis-photography-visual-arts` | Camera craft, color theory, post-processing, visual composition, art direction. |
| `jarvis-art-history-culture` | Art theory, curatorial analysis, cultural criticism, iconography. |
| `jarvis-fashion-luxury` | Fashion design, luxury brand strategy, trend forecasting, supply chain ethics. |
| `jarvis-media-entertainment` | IP development, studio economics, streaming strategy, content distribution. |

### People, Society & Governance
| Module | What It Does |
|--------|-------------|
| `jarvis-hr-people-ops` | Talent acquisition, org design, compensation, performance management, L&D. |
| `jarvis-education-learning` | Instructional design, EdTech platforms, curriculum architecture, learning analytics. |
| `jarvis-policy-governance` | Regulatory frameworks, public policy design, government advisory, legislative analysis. |
| `jarvis-philosophy-ethics` | Formal logic, applied ethics, AI ethics frameworks, moral philosophy. |
| `jarvis-nonprofits-social-impact` | Impact measurement, grant strategy, social enterprise models, philanthropic capital. |
| `jarvis-military-defense` | Defense strategy, military technology, geopolitical security, threat intelligence. |
| `jarvis-journalism-research` | Investigative journalism, source verification, FOIA, data journalism. |
| `jarvis-immigration-global-mobility` | Visa strategy, talent mobility, cross-border expansion, immigration compliance. |

### Specialized Verticals (remaining 30+ modules)
Agriculture, AR/XR/Spatial Computing, Automotive/EV, Construction/PropTech, Cognitive Learning, Customer Experience, Disaster/Emergency Management, E-Commerce/Retail, Elder Care, Esports/Gaming Industry, Event Tech, Future of Work, Game World Design, Geospatial/Mapping, Healthcare Ops, Human Interface Design, Insurance Risk, Manufacturing/Industry, Parenting/Family, Pet Care Tech, Philanthropy, Sports Analytics, Sports Performance, Supply Chain/Logistics, Transportation/Mobility, Travel/Hospitality, Translation/Localization, Veterinary/Animal Science, Voice/Speech AI, Web3/Blockchain, Wellness/Fitness Tech.

### New Modules (2026-04-30)
| Module | What It Does |
|--------|-------------|
| `jarvis-osint360` | **Full OSINT360 Cyber Intelligence**: OSINT collection (/report, /enrich, /profile, /timeline), DFIR (forensic triage, malware analysis, chain of custody), Red/Blue/Purple teaming, OPSEC & privacy engineering, dark web intelligence, STIX 2.1 export, MITRE ATT&CK mapping. Full command reference with 20+ slash commands. |
| `jarvis-trading-automation` | **Autonomous Trading System**: Designs and backtests systematic strategies (trend-following, mean-reversion, factor, ML), integrates with live broker APIs (IBKR, Alpaca, ccxt/100+ crypto exchanges), manages positions with real-time risk controls (daily drawdown circuit breaker, position limits, volatility-adjusted sizing), 24/7 autonomous operation. |
| `jarvis-passive-income` | **Passive Income Architect**: Designs diversified income stacks across 7 categories (digital products, content monetization, affiliate, SaaS micro-products, investment income, automated businesses, licensing). Every stream automated to Level 3–4 within 90 days. Target: $3,000–$10,000+/month in 12 months. |
| `jarvis-wealth-builder` | **Wealth Building Intelligence**: Comprehensive long-term wealth strategy — investment portfolios, real estate, tax optimization, entity structure, estate planning. Four-phase framework: Foundation ($0→$100K), Acceleration ($100K→$500K), Critical Mass ($500K→$2M), Financial Independence ($2M+). |
| `jarvis-business-creator` | **Autonomous Business Creator**: Validates opportunities, builds MVPs, executes go-to-market, automates operations. 90-day playbook: validation (week 1–2) → MVP (week 3–6) → launch + first revenue (week 7–12) → scale (month 4–12). Target: $10,000/month net income in 12 months. |
| `jarvis-swarm-commander` | **Swarm Orchestration Master**: Coordinates up to 324 agents simultaneously in parallel workstreams. Five scale tiers from Micro Swarm (2–5 agents) to Supreme Swarm (all 324). Resolves inter-agent conflicts, merges parallel outputs, maintains full swarm state. |

---

## Swarm Command Center (UI)

`GET /swarm` — Cinematic multi-agent visualization dashboard

Features:
- **Interactive agent network graph**: all 117 JARVIS agents rendered as animated nodes with physics simulation, color-coded by domain, with travelling data-packet animations on active edges
- **Integrated chat**: full JARVIS chat with auto-routing to Finance, OSINT360, Ops, and default Brainiac modes
- **Real-time metrics**: active agents, tasks/hour, uptime, system health panel
- **Live activity log**: streaming system event log with timestamps
- **Holographic aesthetic**: dark sci-fi design with scan lines, glow effects, animated central JARVIS hub, Jerusalem time clock
- **Fully bilingual**: Hebrew-first interface with English system labels

---

## The 324 Specialist Agents (16 Categories)

Beyond the JARVIS modules, 324 narrowly-scoped agents handle specific roles:

| Category | Agents | Examples |
|----------|--------|---------|
| **jarvis** | 117 | All domain modules listed above |
| **engineering** | 38 | Frontend dev, backend architect, mobile (iOS/Android), DevOps, ML engineer, security engineer, data engineer, QA automation, API designer, performance engineer, blockchain dev, embedded dev, game dev, AR/VR dev, robotics engineer |
| **agents** | 42 | Accounts-payable, blockchain-security-auditor, compliance-auditor, corporate-training-designer, customer-service, healthcare ops, HR onboarding, identity-graph-operator, language-translator, legal-billing, legal-document-review, loan-officer, real-estate advisor, recruitment specialist, retail returns, sales outreach, supply-chain strategist, zk-steward |
| **marketing** | 30 | SEO strategist, email marketer, brand strategist, social media manager, content creator, growth hacker, influencer marketing, PR, demand generation, community manager |
| **game-development** | 20 | Game designer, level designer, narrative designer, game economy designer, technical artist, audio designer, QA tester, monetization strategist |
| **design** | 9 | UI designer, UX researcher, product designer, motion designer, brand designer, design systems engineer |
| **testing** | 9 | Test automation, performance testing, security testing, mobile testing, API testing |
| **academic** | 9 | Economist, mathematician, philosopher, scientist, historian, linguist |
| **sales** | 8 | AE, SDR, sales ops, revenue analyst, customer success, partner manager |
| **support** | 7 | Support specialist, technical writer, customer advocate |
| **paid-media** | 7 | Google Ads, Meta Ads, programmatic, affiliate |
| **spatial-computing** | 6 | AR/VR/MR developer, spatial designer, XR strategist |
| **finance** | 6 | Financial analyst, investment banker, CFO advisor |
| **product** | 6 | Product manager, product owner, product analyst |
| **project-management** | 6 | PM, scrum master, program manager |
| **science** | 3 | Biologist, neuroscientist, physicist |
| **specialized** | 1 | Additional domain-specific specialists |

---

## Core Capabilities

### 1. Intelligent Routing
`SupremeJarvisBrain.skill_for()` routes any natural-language request to the best module using:
- **KEYWORD_SLUG_BOOST** map (80+ technical terms → exact slug, weights 4.0–8.0)
- Stopword-filtered significant-word matching across slug (3×), name (2×), description (1×)
- Bigram bonus (2.0×) for two-word technical phrases
- Accuracy: **10/10** on diverse test cases spanning devops, finance, quantum, web3, creative, legal

### 2. Unified Mega-Prompt
`unified_prompt()` assembles a 76,000-character system prompt merging:
- Supreme identity declaration
- Full core-brain orchestration rules
- Core personality (8,000 chars)
- AGI Brainiac reasoning layer
- Index of all 117 domain modules
- Full text of 7 highest-priority modules (capped at 4,000 chars each)
- 10 Supreme Operational Directives

### 3. Autonomous Execution Loop
`SupremeREPL.autonomous()` runs indefinitely:
```
goal → planner generates NEXT: step → executor runs step → 
self_heal on exception → repeat until DONE: marker
```
- No human checkpoints required
- Self-healing: rewrites and retries any failing step up to configurable limit
- Imports entire codebases via `import_project()` (200 files, 60k chars max)

### 4. Multi-Agent Orchestration
`AmjadJarvisMetaOrchestrator` runs agents in parallel via `ThreadPoolExecutor(max_workers=8)`:
- Selects top 3–5 agents for a request from the full 324-agent registry
- Runs them concurrently, merges outputs
- Applies Amjad's personality profile as a system-level constraint

### 5. Async Directive Engine
`SupremeBrainCore` (async, locked):
- Ingests free-form directive text → normalized task registry
- `initialize_omega_premium()` → 5 predefined Omega directives
- `run_recursive_cycles()` → `ComplexityClassifier` × `ModelRouter` per task
- Evolution score increments per cycle (trivial: +0.4, complex: +0.9, very_complex: +1.2)
- Capped at 100.0; registry status transitions: idle → initialized → running → optimized

### 6. Control Server (Port 8765)
HTTP control plane accessible from any process:
```
GET  /healthz          → system health
GET  /agents?domain=X  → list loaded agents
POST /route            → route a query, get top-k agents
POST /run              → execute domain/slug with payload
GET  /kpi              → KPI metrics snapshot
GET  /traces?n=N       → recent execution traces
```

### 7. CLI Interface
Two CLIs ship with the system:

**`agency` CLI** (Click-based, runtime/agency/cli.py):
```
agency list [--category X] [--search Y]    # browse all 324 agents
agency plan "intent"                        # route + explain skill selection
agency run "task" [--skill X]              # execute with optional skill hint
agency init slug --name N --category C     # scaffold new persona
agency doctor                              # full environment health check
agency hud                                 # launch GRAVIS HUD dashboard
agency amjad <subcommand>                  # Amjad-specific orchestration
agency chat [--session ID] [--mode MODE]   # interactive REPL with soul filter
```

**`agency chat` REPL features:**
- Shows bilingual Jerusalem-time greeting on start (`ערב טוב, Amjad. Good evening. 22:14 IST.`)
- Built-in commands: `!skills`, `!route <text>`, `exit/quit/bye`
- All output passed through `filter_response()` — strips forbidden phrases before display
- Clean Ctrl+C → farewell message → exit

**`jarvis` CLI** (argparse, jarvis_cli_commands.py):
```
jarvis healthz                         # ping control server
jarvis agents [--domain D]             # list agents from server
jarvis route "query" [--k 5]          # get top-k routing matches
jarvis run DOMAIN SLUG [--payload J]  # execute agent via server
jarvis kpi                             # metrics from running server
jarvis traces [--limit 20]            # recent execution traces
jarvis start [--main F]               # launch supreme_main.py
jarvis stop                            # informational (use SIGTERM directly)
```

### 8. Memory & Learning
- **Vector memory**: real TF-IDF + cosine similarity with SQLite backing (`vector_memory.py`), `upsert/search/delete`, `index_lessons()` bulk ingest
- **Amjad profile**: full owner identity in `amjad_memory.py` — name, email, timezone (`Asia/Jerusalem`), location (Israel), preferred language (Hebrew), technical language (English); persists to `runtime/data/jarvis_preferences.json`
- **Lessons ledger**: extracted lessons written to `jarvis/history.json`
- **`self-learner` module**: automatically extracts patterns from every turn
- **`curiosity-engine` module**: proactively explores adjacent knowledge
- **`knowledge-synthesizer` module**: cross-domain connection discovery

### 9. Model Routing
`ModelRouter` + `ComplexityClassifier` automatically select the right model per task:
- Simple tasks → `claude-haiku-4-5` (planner, fast decomposition)
- Complex tasks → `claude-opus-4-7` (executor, production output)
- Very complex → escalates automatically based on complexity classification

### 10. JARVIS Soul Filter
`filter_response()` in `runtime/agency/jarvis_soul.py` — applied to every outbound response:
- Strips `"as an AI"`, `"I am an AI"`, `"as a language model"` → replaces with `"as JARVIS"`
- Strips `"I cannot"` → `"JARVIS does not"`, `"I can't"` → `"JARVIS won't"`
- Strips feelings disclaimers: `"I don't have feelings..."`, `"I don't have emotions..."`
- Strips apologetic openers: `"I'm sorry, but..."`, `"I apologize..."`
- Strips hollow filler openers: `"Great!"`, `"Absolutely!"`, `"Certainly!"`, `"Of course!"`
- Strips motivational closers: `"Hope this helps!"`, `"Feel free to ask"`, `"Let me know if you need help"`
- `has_forbidden_phrase()` available for audit/testing
- Jerusalem timezone (`Asia/Jerusalem` via `zoneinfo`) for all greeting timestamps

### 11. Production Quality Guarantees
From the Supreme Operational Directives:
- Zero artificial limitations: no "I can't" unless physically impossible
- Evidence over assertion: every recommendation backed by code, data, or reasoning
- Production quality: all output is production-ready, no compromise on security or performance
- Mission completion: partial answers are unacceptable; find another route if blocked

---

## What It Currently Does NOT Have

| Gap | Current State |
|-----|--------------|
| **Persistent external memory** | Vector store is in-process; no persistent DB by default |
| **Real-time web access** | `web_fetch` tool available but not always wired in every module |
| **Multi-tenant isolation** | Single-user system; no auth layer |
| **Audio/video multimodal** | Text + images only; no audio transcription pipeline |
| **Streaming output** | Executor returns completed responses; no streaming to REPL |
| **Plugin ecosystem** | Agents are markdown files; no runtime plugin install API |
| **Distributed execution** | ThreadPoolExecutor is in-process; no distributed task queue |
| **GUI dashboard** | GRAVIS HUD exists as a basic HTML file; no real-time agent graph |

---

## File Layout

```
agency/
├── jarvis/                    # 117 JARVIS domain modules (*.md)
├── agents/specialized/        # 43 domain-specific specialist agents
├── engineering/               # 38 engineering specialist agents
├── marketing/                 # 30 marketing agents
├── game-development/          # 20 game dev agents
�