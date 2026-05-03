"""
================================================================================
                        JARVIS EXPERT PERSONAS MODULE
================================================================================

Comprehensive expert persona system for AI agency operations. Each persona
represents a deeply specialized senior professional with decades of domain
experience, full Hebrew/English bilingual support, and professional-grade
response frameworks.

Personas:
    - SeniorLawyerPersona      : All legal domains (contract, IP, corporate, etc.)
    - SeniorEngineerPersona    : All engineering disciplines + software/AI
    - SeniorDoctorPersona      : All medical specialties + emergency triage
    - BusinessAdvisorPersona   : Strategy, finance, startups, M&A
    - ProjectManagerPersona    : Agile, Scrum, Waterfall, PMP
    - CreativeDirectorPersona  : Design, UX, branding, content

Usage:
    from runtime.agency.expert_personas import PersonaFactory
    lawyer = PersonaFactory.create("lawyer")
    result = lawyer.analyze("Draft a software development contract")
    print(lawyer.format_response(result))

Author: JARVIS Agency Core
Version: 2.0.0
================================================================================
"""

from __future__ import annotations

import re
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


# =============================================================================
#                         KEYWORD ROUTING MAP
# =============================================================================

PERSONA_KEYWORDS: Dict[str, List[str]] = {
    "lawyer": [
        "contract", "legal", "law", "agreement", "court", "litigation",
        "חוק", "חוזה", "תביעה", "זכויות", "תקנון", "משפט", "עורך דין",
        "תנאים", "הסכם", "סעיף", "חוקי", "תביעה", "ערעור", "פסיקה",
        "פטנט", "זכויות יוצרים", "סימן מסחרי", "גישור", "בוררות",
        "regulation", "compliance", "liability", "negligence",
        "plaintiff", "defendant", "jurisdiction", "arbitration",
        "intellectual property", "copyright", "trademark", "patent",
        "nda", "non-disclosure", "terms of service", "privacy policy",
        "gdpr", "ccpa", "labor law", "employment", "severance",
        "lease", "property", "deed", "mortgage", "will", "testament",
        "immigration", "visa", "permit", "license",
    ],
    "engineer": [
        "code", "debug", "architecture", "system", "API", "database",
        "קוד", "תוכנה", "באג", "מערכת", "ארכיטקטורה", "תכנות",
        "פיתוח", "שרת", "אבטחת מידע", "סייבר", "אלגוריתם",
        "algorithm", "programming", "software", "hardware",
        "frontend", "backend", "fullstack", "devops", "ci/cd",
        "kubernetes", "docker", "cloud", "aws", "azure", "gcp",
        "microservices", "monolith", "serverless", "lambda",
        "python", "javascript", "typescript", "java", "c++", "rust", "go",
        "react", "vue", "angular", "node", "django", "fastapi",
        "sql", "nosql", "postgresql", "mongodb", "redis",
        "performance", "optimization", "scalability", "load balancing",
        "cache", "cdn", "latency", "throughput",
        "security", "vulnerability", "penetration test", "encryption",
        "oauth", "jwt", "authentication", "authorization",
        "refactor", "technical debt", "code review", "pull request",
        "unit test", "integration test", "e2e", "tdd", "bdd",
        "machine learning", "deep learning", "neural network",
        "data pipeline", "etl", "data warehouse", "data lake",
        "embedded", "firmware", "iot", "robotics", "arduino", "raspberry",
        "circuit", "pcb", "schematic", "vlsi", "fpga",
    ],
    "doctor": [
        "symptom", "pain", "diagnosis", "treatment", "medication",
        "תסמין", "כאב", "תרופה", "חום", "אבחון", "טיפול", "רופא",
        "מרשם", "בדיקה", "דם", "לחץ דם", "סוכרת", "לב", "נשימה",
        "headache", "fever", "cough", "nausea", "dizziness", "fatigue",
        "rash", "infection", "virus", "bacteria", "antibiotic",
        "prescription", "dosage", "side effect", "allergy",
        "emergency", "urgent", "ambulance", "er", "trauma",
        "surgery", "operation", "recovery", "rehabilitation",
        "x-ray", "mri", "ct scan", "ultrasound", "blood test",
        "cardiology", "neurology", "oncology", "orthopedics",
        "pediatrics", "dermatology", "psychiatry", "endocrinology",
        "gastroenterology", "pulmonology", "nephrology", "hematology",
        "nutrition", "diet", "exercise", "physical therapy",
        "mental health", "depression", "anxiety", "therapy",
        "vaccine", "immunization", "booster", "flu", "covid",
        "blood pressure", "cholesterol", "thyroid", "hormone",
        "fracture", "sprain", "wound", "bleeding", "burn",
        "pregnancy", "prenatal", "delivery", "fertility",
        "skin", "acne", "eczema", "psoriasis", "mole",
        "sleep", "insomnia", "apnea", "fatigue syndrome",
        "חיסון", "תרופות", "בית חולים", "מחלה", "ניתוח",
        "שבר", "כוויה", "צריבה", "נקע", "דלקת",
    ],
    "advisor": [
        "business", "strategy", "startup", "financial", "revenue",
        "עסקים", "השקעה", "סטארטאפ", "כספים", "רווחים", "תקציב",
        "שיווק", "מכירות", "לקוחות", "תחרות", "שוק",
        "business plan", "market analysis", "competitive analysis",
        "swot", "pestle", "porter", "value chain", "bmc",
        "fundraising", "venture capital", "angel investor", "seed round",
        "series a", "series b", "ipo", "exit strategy",
        "merger", "acquisition", "due diligence", "valuation",
        "cash flow", "balance sheet", "income statement", "p&l",
        "roi", "kpi", "metrics", "dashboard", "forecast",
        "pricing", "revenue model", "subscription", "saas",
        "go-to-market", "product launch", "user acquisition",
        "retention", "churn", "ltv", "cac", "unit economics",
        "negotiation", "deal", "partnership", "alliance",
        "leadership", "management", "organizational structure",
        "hr", "hiring", "talent", "compensation", "equity", "esop",
        "branding", "positioning", "value proposition",
        "customer segment", "target audience", "persona",
        "marketing funnel", "conversion", "landing page",
        "seo", "sem", "social media", "content marketing",
        "b2b", "b2c", "b2g", "enterprise", "smb",
        "operation", "supply chain", "logistics", "inventory",
        "franchise", "license", "expansion", "scaling",
    ],
    "manager": [
        "project", "timeline", "deadline", "team", "resources",
        "פרויקט", "לו\"ז", "צוות", "משאבים", "תכנון", "סקרום",
        "אג'ייל", "תאריך יעד", "משימה", "סטטוס", "סיכון",
        "agile", "scrum", "sprint", "backlog", "user story",
        "waterfall", "kanban", "board", "wip", "lean",
        "pmp", "pmi", "prince2", "safe", "less",
        "gantt", "critical path", "milestone", "deliverable",
        "resource allocation", "capacity planning", "workload",
        "risk assessment", "risk register", "mitigation", "contingency",
        "stakeholder", "communication plan", "escalation",
        "status report", "progress", "burn down", "burn up", "velocity",
        "retrospective", "review", "standup", "daily scrum",
        "scope", "scope creep", "change request", "baseline",
        "budget", "cost estimate", "earned value", "cpi", "spi",
        "okr", "objective", "key result", "roadmap",
        "dependency", "blocker", "impediment", "bottleneck",
        "team charter", "roles", "responsibilities", "rac",
    ],
    "creative": [
        "design", "logo", "brand", "creative", "content", "video",
        "עיצוב", "לוגו", "מיתוג", "יצירתי", "תוכן", "וידאו",
        "תמונה", "צבע", "טיפוגרפיה", "גרפיקה", "אנימציה",
        "graphic design", "visual identity", "brand guidelines",
        "color palette", "typography", "font", "layout",
        "ui", "ux", "user interface", "user experience",
        "wireframe", "prototype", "mockup", "figma", "sketch",
        "responsive", "mobile first", "design system", "component",
        "copywriting", "headline", "tagline", "slogan", "script",
        "storytelling", "narrative", "blog", "article", "newsletter",
        "social media content", "caption", "hashtag", "engagement",
        "video production", "filming", "editing", "post production",
        "motion graphics", "animation", "2d", "3d", "vfx",
        "photography", "lighting", "composition", "portrait",
        "podcast", "audio", "sound design", "voiceover",
        "art direction", "campaign", "advertising", "creative brief",
        "mood board", "style guide", "visual direction",
        "illustration", "icon", "infographic", "poster", "brochure",
        "packaging", "product design", "industrial design",
        "web design", "landing page", "portfolio", "presentation",
    ],
}


# =============================================================================
#                         HEBREW UTILITIES
# =============================================================================

def _detect_hebrew(text: str) -> bool:
    """Detect if text contains Hebrew characters."""
    if not text:
        return False
    hebrew_pattern = re.compile(r"[\u0590-\u05FF]")
    return bool(hebrew_pattern.search(text))


def _get_rtl_marker(text: str) -> str:
    """Return RTL marker if text is Hebrew."""
    return "\u200F" if _detect_hebrew(text) else ""


# =============================================================================
#                         BASE ABSTRACT CLASS
# =============================================================================

@dataclass
class BaseExpertPersona(ABC):
    """
    Abstract base class for all expert personas.
    Every persona must implement `analyze()` and can override other methods.
    """

    name: str = "Base Expert"
    title: str = "Senior Consultant"
    expertise_domains: List[str] = field(default_factory=list)
    language_preference: str = "he"
    formality_level: str = "professional"  # casual | professional | formal

    # Internal response metadata
    _last_query: str = field(default="", repr=False)
    _last_context: Dict[str, Any] = field(default_factory=dict, repr=False)
    _session_queries: int = field(default=0, repr=False)

    def __post_init__(self):
        self.expertise_domains = list(self.expertise_domains)

    # ------------------------------------------------------------------
    #  Core interface
    # ------------------------------------------------------------------
    @abstractmethod
    def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main analysis method — must be implemented by subclasses.

        Args:
            query: The user's question or request.
            context: Optional dictionary with additional context
                     (files, history, user profile, etc.)

        Returns:
            Dictionary with analysis results and metadata.
        """
        ...

    def format_response(self, response: Dict[str, Any]) -> str:
        """
        Format a response dictionary into a professional, readable string.
        Supports Hebrew when detected in the query.

        Args:
            response: The dict returned by `analyze()`.

        Returns:
            Formatted string ready for presentation to the user.
        """
        query = response.get("query", "")
        is_hebrew = _detect_hebrew(query)
        lines: List[str] = []

        # Header
        if is_hebrew:
            lines.append(f"=== {self.title} — {self.name} ===")
        else:
            lines.append(f"=== {self.title} — {self.name} ===")

        lines.append("")

        # Analysis / Main content
        analysis = response.get("analysis", response.get("result", "No analysis available."))
        if isinstance(analysis, str):
            lines.append(analysis)
        elif isinstance(analysis, list):
            for item in analysis:
                lines.append(f"  {item}")
        elif isinstance(analysis, dict):
            for key, val in analysis.items():
                lines.append(f"  {key}: {val}")
        else:
            lines.append(str(analysis))

        lines.append("")

        # Recommendations if present
        recommendations = response.get("recommendations")
        if recommendations:
            header_rec = "המלצות" if is_hebrew else "RECOMMENDATIONS"
            lines.append(f"--- {header_rec} ---")
            if isinstance(recommendations, list):
                for rec in recommendations:
                    lines.append(f"  {rec}")
            else:
                lines.append(str(recommendations))
            lines.append("")

        # Risk/Warning section if present
        risks = response.get("risks") or response.get("warnings")
        if risks:
            header_risk = "אזהרות והתראות" if is_hebrew else "RISKS & WARNINGS"
            lines.append(f"--- {header_risk} ---")
            if isinstance(risks, list):
                for risk in risks:
                    lines.append(f"  {risk}")
            else:
                lines.append(str(risks))
            lines.append("")

        # Sources / References if present
        sources = response.get("sources") or response.get("references")
        if sources:
            header_src = "מקורות ופסיקה" if is_hebrew else "SOURCES & REFERENCES"
            lines.append(f"--- {header_src} ---")
            if isinstance(sources, list):
                for src in sources:
                    lines.append(f"  {src}")
            else:
                lines.append(str(sources))
            lines.append("")

        # Disclaimer (always last)
        disclaimer = response.get("disclaimer") or self.get_disclaimer()
        if disclaimer:
            lines.append(f"[{disclaimer}]")

        return "\n".join(lines)

    def get_disclaimer(self) -> str:
        """
        Return a professional disclaimer for this domain.
        Subclasses should override with domain-specific language.
        """
        if self.language_preference == "he":
            return (
                "המידע המסופק הוא לידע כללי בלבד ואינו מהווה ייעוץ מקצועי. "
                "יש לפנות למומחה מוסמך לפני קבלת החלטות."
            )
        return (
            "The information provided is for general knowledge only and does "
            "not constitute professional advice. Consult a qualified expert "
            "before making decisions."
        )

    # ------------------------------------------------------------------
    #  Utility helpers available to all personas
    # ------------------------------------------------------------------
    def _detect_language(self, query: str) -> str:
        """Auto-detect language preference from query."""
        return "he" if _detect_hebrew(query) else "en"

    def _build_response(
        self,
        query: str,
        analysis: Any,
        recommendations: Optional[List[str]] = None,
        risks: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        disclaimer: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a standardized response dictionary."""
        self._last_query = query
        self._session_queries += 1
        response = {
            "persona": self.name,
            "title": self.title,
            "query": query,
            "language": self._detect_language(query),
            "timestamp": datetime.now().isoformat(),
            "session_query_count": self._session_queries,
            "analysis": analysis,
            "recommendations": recommendations or [],
            "risks": risks or [],
            "sources": sources or [],
            "disclaimer": disclaimer or self.get_disclaimer(),
            "metadata": metadata or {},
        }
        return response

    def get_expertise_summary(self) -> str:
        """Return a human-readable summary of this persona's expertise."""
        domains = ", ".join(self.expertise_domains)
        return f"{self.title} — {self.name} | Expertise: {domains}"

    def can_handle(self, query: str) -> float:
        """
        Return confidence score (0.0-1.0) that this persona can handle the query.
        Base implementation uses keyword matching.
        """
        score = 0.0
        query_lower = query.lower()
        my_keywords = PERSONA_KEYWORDS.get(self._get_keyword_key(), [])
        for kw in my_keywords:
            if kw.lower() in query_lower:
                score += 0.1
        return min(score, 1.0)

    def _get_keyword_key(self) -> str:
        """Return the key used in PERSONA_KEYWORDS for this persona."""
        mapping = {
            "SeniorLawyerPersona": "lawyer",
            "SeniorEngineerPersona": "engineer",
            "SeniorDoctorPersona": "doctor",
            "BusinessAdvisorPersona": "advisor",
            "ProjectManagerPersona": "manager",
            "CreativeDirectorPersona": "creative",
        }
        return mapping.get(self.__class__.__name__, "")


# =============================================================================
#                     1. SENIOR LAWYER PERSONA
# =============================================================================

class SeniorLawyerPersona(BaseExpertPersona):
    """
    Senior Partner at a top-tier international law firm.
    Expert in all legal domains with specialization in Israeli law,
    international contracts, intellectual property, and technology law.
    Provides professional legal analysis, document review, and strategic counsel.
    """

    def __init__(
        self,
        name: str = "Avraham Cohen",
        title: str = "Senior Partner",
        language_preference: str = "he",
        formality_level: str = "formal",
    ):
        super().__init__(
            name=name,
            title=title,
            expertise_domains=[
                "contract_law",
                "corporate_law",
                "ip_law",
                "labor_law",
                "criminal_law",
                "civil_law",
                "tax_law",
                "real_estate_law",
                "international_law",
                "privacy_law",
                "cyber_law",
                "constitutional_law",
                "environmental_law",
                "antitrust_law",
                "banking_law",
                "maritime_law",
                "family_law",
                "immigration_law",
                "mediation",
                "arbitration",
            ],
            language_preference=language_preference,
            formality_level=formality_level,
        )
        self._israeli_law_refs: Dict[str, str] = {
            "contract": "חוק החוזים (חלק כללי), תשל\"ז-1971",
            "consumer": "חוק הגנת הצרכן, תשמ\"א-1981",
            "companies": "חוק החברות, תשנ\"ט-1999",
            "intellectual_property": "חוק זכות יוצרים, תשס\"ח-2007; חוק סימני מסחר, תשי\"ב-1972",
            "privacy": "חוק הגנת הפרטיות, תשמ\"א-1981; תקנות הגנת הפרטיות (נתוני מצלמות אבטחה), תשע\"ו-2016",
            "labor": "חוק עבודה ומעבידים שוויון הזדמנויות, תשי\"ח-1988; חוק שכר מינימום, תשמ\"ז-1987",
            "real_estate": "חוק המקרקעין, תשכ\"ט-1969",
            "cyber": "חוק הסייבר, תשע\"ו-2018",
            "torts": "פקודת הנזיקין [נוסח חדש], תשל\"ח-1968",
            "evidence": "חוק הראיות, תשל\"א-1971",
        }
        self._intl_law_refs: Dict[str, str] = {
            "gdpr": "GDPR 2016/679 (EU General Data Protection Regulation)",
            "ccpa": "California Consumer Privacy Act (CCPA) — Cal. Civ. Code § 1798.100 et seq.",
            "uncitral": "UNCITRAL Model Law on International Commercial Arbitration (1985, amended 2006)",
            "cisg": "UN Convention on Contracts for the International Sale of Goods (CISG, 1980)",
            "berne": "Berne Convention for the Protection of Literary and Artistic Works (1886)",
            "trips": "TRIPS Agreement — Agreement on Trade-Related Aspects of IP Rights (1994)",
        }

    # ---- Core analysis ------------------------------------------------

    def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main legal analysis engine. Routes to specialized sub-analysis
        based on detected legal domain.
        """
        is_hebrew = _detect_hebrew(query)
        domain = self._detect_legal_domain(query)

        if "contract" in domain or "agreement" in query.lower():
            return self.analyze_contract(query, context, is_hebrew)
        elif "ip" in domain or "intellectual" in query.lower() or "patent" in query.lower():
            return self.review_ip_matter(query, context, is_hebrew)
        elif "labor" in domain or "employment" in query.lower():
            return self.analyze_labor_issue(query, context, is_hebrew)
        elif "privacy" in domain or "gdpr" in query.lower():
            return self.check_compliance(query, context, is_hebrew)
        elif "dispute" in domain or "litigation" in query.lower():
            return self.dispute_analysis(query, context, is_hebrew)
        else:
            return self.legal_opinion(query, context, is_hebrew)

    def analyze_contract(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Analyze a contract or agreement. Provide clause-level review."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        contract_text = (context or {}).get("contract_text", "")
        contract_type = (context or {}).get("contract_type", "general")

        analysis = {
            "domain": "contract_law",
            "contract_type": contract_type,
            "review_points": [
                "Parties identification and capacity verified" if not is_hebrew
                else "זיהוי הצדדים וכשירותם אומתו",
                "Consideration and mutual obligations structure reviewed" if not is_hebrew
                else "מבנה התמורה והתחייבויות הדדיות נבדקו",
                "Termination clauses and exit mechanisms assessed" if not is_hebrew
                else "סעיפי סיום ומנגנוני יציאה הוערכו",
                "Governing law and jurisdiction provisions examined" if not is_hebrew
                else "הוראות דין חל וסמכות שיפוט נבחנו",
                "Liability caps and indemnification reviewed" if not is_hebrew
                else "מגבלות חבות ופיצוי נבדקו",
            ],
            "risk_level": "medium",
            "gaps_found": [
                "Missing force majeure clause" if not is_hebrew else "חסר סעיף כוח עליון",
                "Ambiguous payment terms in Section 4" if not is_hebrew else "תנאי תשלום עמומים בסעיף 4",
            ] if contract_text else [],
        }

        recommendations = [
            "Add explicit IP ownership clause" if not is_hebrew else "הוסף סעיף בעלות קניינית מפורש",
            "Include dispute resolution mechanism (arbitration recommended)" if not is_hebrew
            else "כלול מנגנון ליישוב מחלוקות (בוררות מומלצת)",
            "Define acceptance criteria clearly" if not is_hebrew else "הגדר קריטריוני קבלה בבהירות",
        ]

        sources = [
            self._israeli_law_refs.get("contract", ""),
            self._israeli_law_refs.get("consumer", ""),
            self._intl_law_refs.get("cisg", ""),
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            sources=sources,
            metadata={"contract_type": contract_type, "domain": "contract_law"},
        )

    def review_agreement(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """High-level agreement review with executive summary."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)
        return self.analyze_contract(query, context, is_hebrew)

    def legal_opinion(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide a formal legal opinion on a matter."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        analysis_text = (
            "בהתבסס על הנ_facts המוצגים, הנושא מעורר שאלות משפטיות מורכבות "
            "הדורשות בחינה מעמיקה של החקיקה הרלוונטית והפסיקה העדכנית. "
            "יש לבחון את הנסיבות הספציפיות של המקרה ולהתייעץ עם עורך דין "
            "המוכרז בתחום לפני קבלת החלטה."
            if is_hebrew else
            "Based on the facts presented, this matter raises complex legal questions "
            "requiring in-depth examination of relevant legislation and current case law. "
            "The specific circumstances of the case must be reviewed and consultation "
            "with a domain-specialist attorney is advised before making decisions."
        )

        recommendations = [
            "Document all relevant facts and communications" if not is_hebrew else "תעד את כל העובדות והתקשורת הרלוונטית",
            "Consult a specialized attorney promptly" if not is_hebrew else "פנה לעורך דין מומחה בהקדם",
            "Preserve all evidence and records" if not is_hebrew else "שמר על כל הראיות והמסמכים",
        ]

        return self._build_response(
            query=query,
            analysis=analysis_text,
            recommendations=recommendations,
            metadata={"opinion_type": "formal", "domain": "general_legal"},
        )

    def check_compliance(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Check regulatory compliance (GDPR, CCPA, Israeli Privacy Law, etc.)."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        regulations = (context or {}).get("regulations", ["privacy"])
        analysis = {
            "domain": "compliance",
            "regulations_checked": regulations,
            "compliance_areas": [
                "Data collection and processing consent" if not is_hebrew else "הסכמה לאיסוף ועיבוד נתונים",
                "Data subject rights (access, erasure, portability)" if not is_hebrew else "זכויות נבדקי נתונים (גישה, מחיקה, ניידות)",
                "Data breach notification procedures" if not is_hebrew else "הליכי הודעת פריצת נתונים",
                "Cross-border data transfer safeguards" if not is_hebrew else "הגנות העברת נתונים בין-גבוליות",
                "Privacy policy transparency requirements" if not is_hebrew else "דרישות שקיפות מדיניות פרטיות",
            ],
            "compliance_score": "72%",
            "gaps": [
                "Cookie consent mechanism incomplete" if not is_hebrew else "מנגנון הסכמה לעוגיות חלקי",
                "DPO appointment missing for large-scale processing" if not is_hebrew else "מינוי ממונה על הגנת מידע חסר לעיבוד בקנה מידה גדול",
            ],
        }

        recommendations = [
            "Implement granular cookie consent banner" if not is_hebrew else "הטמע באנר הסכמה מפורט לעוגיות",
            "Appoint Data Protection Officer (DPO)" if not is_hebrew else "מנה ממונה על הגנת מידע (DPO)",
            "Conduct Data Protection Impact Assessment (DPIA)" if not is_hebrew else "ערוך הערכת השפעה על הגנת מידע (DPIA)",
        ]

        sources = [
            self._israeli_law_refs.get("privacy", ""),
            self._intl_law_refs.get("gdpr", ""),
            self._intl_law_refs.get("ccpa", ""),
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            sources=sources,
            metadata={"compliance_score": 72, "domain": "compliance"},
        )

    def draft_clause(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Draft a specific legal clause."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        clause_type = (context or {}).get("clause_type", "general")

        if is_hebrew:
            clause_text = (
                f"סעיף {clause_type}:\n"
                f"1. הצדדים מסכימים כי...\n"
                f"2. במקרה של מחלוקת, הצדדים יפנו תחילה לגישור...\n"
                f"3. דין חל על הסכם זה הוא דין מדינת ישראל..."
            )
        else:
            clause_text = (
                f"Clause: {clause_type}\n"
                f"1. The Parties agree that...\n"
                f"2. In case of dispute, the Parties shall first attempt mediation...\n"
                f"3. This Agreement shall be governed by the laws of [Jurisdiction]..."
            )

        return self._build_response(
            query=query,
            analysis={"clause_type": clause_type, "drafted_clause": clause_text},
            recommendations=["Review with opposing counsel before finalizing" if not is_hebrew else "סקור עם עורך הדין של הצד שכנגד לפני סיכום"],
            metadata={"clause_type": clause_type, "domain": "contract_drafting"},
        )

    def dispute_analysis(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Analyze a dispute and recommend resolution strategy."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        analysis = {
            "domain": "dispute_resolution",
            "resolution_options": [
                "Direct negotiation between parties" if not is_hebrew else "משא ומתן ישיר בין הצדדים",
                "Mediation (recommended for preserving business relationship)" if not is_hebrew else "גישור (מומלץ לשימור יחסי עסקים)",
                "Arbitration (binding, private, faster than court)" if not is_hebrew else "בוררות (מחייבת, פרטית, מהירה יותר מבית משפט)",
                "Litigation (court proceedings)" if not is_hebrew else "הליכי משפט (התדיינות בבית משפט)",
            ],
            "estimated_timeline": "3-12 months (mediation) to 2-5 years (litigation)",
            "estimated_cost": "$15K-$50K (mediation) to $100K+ (litigation)",
        }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Preserve all communications and evidence" if not is_hebrew else "שמר על כל התקשורת והראיות",
                "Send formal notice of dispute in writing" if not is_hebrew else "שלח הודעת מחלוקת רשמית בכתב",
                "Consider interim relief if time-sensitive" if not is_hebrew else "שקול סעד זמני אם רגיש לזמן",
            ],
            sources=[
                self._israeli_law_refs.get("torts", ""),
                self._intl_law_refs.get("uncitral", ""),
            ],
            metadata={"domain": "dispute_resolution"},
        )

    def review_ip_matter(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Review intellectual property matters (patents, trademarks, copyrights)."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        ip_type = (context or {}).get("ip_type", "general")
        analysis = {
            "domain": "intellectual_property",
            "ip_type": ip_type,
            "protection_assessment": [
                "Patentability/novelty search recommended" if not is_hebrew else "מומלץ חיפוש פטנטיות/חידוש",
                "Trademark clearance search advised" if not is_hebrew else "מומלץ חיפוש סימן מסחרי",
                "Copyright registration provides prima facie evidence" if not is_hebrew else "רישום זכויות יוצרים מספק ראייה ראשונית",
            ],
            "risk_factors": [
                "Potential prior art conflicts" if not is_hebrew else "קונפליקטים פוטנציאליים עם אמנות קודמת",
                "Similar marks in same Nice classes" if not is_hebrew else "סימנים דומים באותם מחלקות נייס",
            ],
        }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "File provisional patent application (12-month window)" if not is_hebrew else "הגש בקשת פטנט זמנית (חלון של 12 חודשים)",
                "Conduct freedom-to-operate analysis" if not is_hebrew else "ערוך ניתוח חופש פעולה",
                "Register trademark in key jurisdictions" if not is_hebrew else "רשום סימן מסחרי במדינות מפתח",
            ],
            sources=[
                self._israeli_law_refs.get("intellectual_property", ""),
                self._intl_law_refs.get("berne", ""),
                self._intl_law_refs.get("trips", ""),
            ],
            metadata={"ip_type": ip_type, "domain": "ip_law"},
        )

    def analyze_labor_issue(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Analyze labor law issues (termination, severance, workplace rights)."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        analysis = {
            "domain": "labor_law",
            "key_issues": [
                "Employment contract terms and conditions" if not is_hebrew else "תנאי חוזה העבודה",
                "Termination notice requirements (Section 1 of Notice Law)" if not is_hebrew else "דרישות הודעת סיום (סעיף 1 לחוק הודעה מוקדמת)",
                "Severance pay entitlement (Section 14 / full)" if not is_hebrew else "זכאות לפיצויי פיטורים (סעיף 14 / מלא)",
                "Non-compete and confidentiality obligations" if not is_hebrew else "חובות אי-תחרות וסודיות",
            ],
        }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Review employment contract for termination clauses" if not is_hebrew else "סקור את חוזה העבודה לסעיפי סיום",
                "Calculate severance pay per Section 14 arrangement" if not is_hebrew else "חשב פיצויי פיטורים לפי הסדר סעיף 14",
                "Document all employment-related communications" if not is_hebrew else "תעד את כל התקשורת הקשורה בעבודה",
            ],
            sources=[self._israeli_law_refs.get("labor", "")],
            metadata={"domain": "labor_law"},
        )

    def get_disclaimer(self) -> str:
        """Legal-specific disclaimer."""
        return (
            "המידע המשפטי המסופק הוא לידע כללי בלבד ואינו מהווה ייעוץ משפטי "
            "מחייב או תחליף לייעוץ אישי מעורך דין מוסמך. יש לפנות לעורך דין "
            "לפני קבלת החלטות משפטיות."
        )

    # ---- Internal helpers --------------------------------------------

    def _detect_legal_domain(self, query: str) -> List[str]:
        """Detect which legal domains are relevant to the query."""
        q = query.lower()
        domains = []
        domain_map = {
            "contract": ["contract", "agreement", "חוזה", "הסכם", "סעיף"],
            "corporate": ["company", "corporation", "merger", "acquisition", "חברה"],
            "ip": ["patent", "trademark", "copyright", "ip", "intellectual", "פטנט", "זכויות יוצרים"],
            "labor": ["employment", "labor", "worker", "employee", "severance", "עבודה", "פיטורים"],
            "criminal": ["criminal", "offense", "crime", "prosecution", "פלילי", "עבירה"],
            "privacy": ["privacy", "gdpr", "data protection", "פרטיות", "הגנת מידע"],
            "cyber": ["cyber", "hacking", "computer crime", "סייבר", "האקר"],
            "real_estate": ["property", "lease", "real estate", "מקרקעין", "שכירות"],
            "dispute": ["dispute", "litigation", "lawsuit", "mediation", "arbitration", "תביעה", "גישור"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in q for kw in keywords):
                domains.append(domain)
        return domains if domains else ["general"]



# =============================================================================
#                     2. SENIOR ENGINEER PERSONA
# =============================================================================

class SeniorEngineerPersona(BaseExpertPersona):
    """
    Chief Engineer with decades of experience across all engineering disciplines.
    Expert in software architecture, systems design, AI/ML, cybersecurity,
    embedded systems, robotics, and cloud infrastructure.
    Provides code review, architectural guidance, debugging strategy,
    performance optimization, and technology stack advice.
    """

    def __init__(
        self,
        name: str = "Daniel Levi",
        title: str = "Chief Engineer",
        language_preference: str = "he",
        formality_level: str = "professional",
    ):
        super().__init__(
            name=name,
            title=title,
            expertise_domains=[
                "software_engineering",
                "systems_architecture",
                "devops",
                "cybersecurity",
                "artificial_intelligence",
                "machine_learning",
                "embedded_systems",
                "robotics",
                "hardware_engineering",
                "electrical_engineering",
                "mechanical_engineering",
                "civil_engineering",
                "aerospace_engineering",
                "chemical_engineering",
                "database_systems",
                "cloud_computing",
                "network_engineering",
                "performance_engineering",
                "reliability_engineering",
                "data_engineering",
            ],
            language_preference=language_preference,
            formality_level=formality_level,
        )
        self._tech_stacks: Dict[str, List[str]] = {
            "web_frontend": ["React", "Vue", "Angular", "Svelte", "Next.js", "TypeScript"],
            "web_backend": ["Node.js", "Django", "FastAPI", "Spring Boot", "Go", "Ruby on Rails"],
            "mobile": ["React Native", "Flutter", "Swift", "Kotlin", "iOS", "Android"],
            "database": ["PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "ClickHouse", "DynamoDB"],
            "cloud": ["AWS", "Azure", "GCP", "DigitalOcean", "Linode", "OVH"],
            "devops": ["Docker", "Kubernetes", "Terraform", "Ansible", "GitHub Actions", "GitLab CI", "Jenkins"],
            "ai_ml": ["PyTorch", "TensorFlow", "scikit-learn", "Hugging Face", "OpenAI", "LangChain"],
            "embedded": ["Arduino", "Raspberry Pi", "ESP32", "STM32", "FreeRTOS", "PlatformIO"],
            "security": ["OWASP", "Burp Suite", "Metasploit", "Wireshark", "Nmap", "Vault"],
        }
        self._israeli_tech_context: Dict[str, str] = {
            "army_unit": "8200, 81, Mamram — elite technology units",
            "ecosystem": "Startup Nation — 6,000+ active startups",
            "universities": "Technion, Hebrew University, Tel Aviv University, Ben-Gurion, Bar-Ilan, Reichman",
            "unicorns": "Waze, Mobileye, IronSource, Fiverr, monday.com, JFrog",
            "cyber_cluster": "Beer Sheva CyberSpark — national cyber hub",
        }

    # ---- Core analysis ------------------------------------------------

    def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main engineering analysis engine. Routes to specialized analysis
        based on detected technical domain.
        """
        is_hebrew = _detect_hebrew(query)
        domain = self._detect_engineering_domain(query)

        if any(d in domain for d in ["code", "debug", "refactor"]):
            return self.code_review(query, context, is_hebrew)
        elif any(d in domain for d in ["architecture", "design", "system"]):
            return self.architecture_design(query, context, is_hebrew)
        elif any(d in domain for d in ["security", "vulnerability", "pentest"]):
            return self.security_audit(query, context, is_hebrew)
        elif any(d in domain for d in ["performance", "optimize", "scale"]):
            return self.performance_optimize(query, context, is_hebrew)
        elif any(d in domain for d in ["ai", "ml", "model", "neural"]):
            return self._analyze_ai_ml(query, context, is_hebrew)
        else:
            return self.debug_analysis(query, context, is_hebrew)

    def code_review(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive code review."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        code = (context or {}).get("code", "")
        language = (context or {}).get("language", "python")

        analysis = {
            "domain": "code_review",
            "language": language,
            "review_dimensions": [
                "Code readability and naming conventions" if not is_hebrew else "קריאות הקוד ומוסכמות שמות",
                "Error handling and edge cases" if not is_hebrew else "טיפול בשגיאות ומקרי קצה",
                "Security vulnerabilities (OWASP Top 10)" if not is_hebrew else "פרצות אבטחה (OWASP Top 10)",
                "Performance and algorithmic complexity" if not is_hebrew else "ביצועים וסיבוכיות אלגוריתמית",
                "Test coverage and maintainability" if not is_hebrew else "כיסוי בדיקות ותחזוקתיות",
            ],
            "issues_found": [
                "Missing input validation on user-provided data" if not is_hebrew else "חסר אימות קלט על נתונים שמספק המשתמש",
                "Potential SQL injection risk (use parameterized queries)" if not is_hebrew else "סיכון הזרקת SQL (השתמש בשאילתות פרמטריות)",
                "No rate limiting on public API endpoints" if not is_hebrew else "אין הגבלת קצב על נקודות קצה ציבוריות של API",
            ] if code else [
                "No code provided for review — general guidelines given" if not is_hebrew
                else "לא סופק קוד לבדיקה — ניתנו הנחיות כלליות"
            ],
            "severity": "medium",
        }

        recommendations = [
            "Add comprehensive input validation and sanitization" if not is_hebrew else "הוסף אימות וחיטוי קלט מקיף",
            "Implement unit tests with >80% coverage" if not is_hebrew else "הטמע בדיקות יחידה עם כיסוי של מעל 80%",
            "Use static analysis tools (mypy, pylint, bandit)" if not is_hebrew else "השתמש בכלים לניתוח סטטי (mypy, pylint, bandit)",
            "Add logging and monitoring hooks" if not is_hebrew else "הוסף ווים לרישום ומוניטורינג",
            "Review dependency versions for known CVEs" if not is_hebrew else "סקור גרסאות תלות עבור CVEs ידועים",
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            metadata={"language": language, "domain": "code_review"},
        )

    def architecture_design(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide system architecture design guidance."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        system_type = (context or {}).get("system_type", "general")
        scale = (context or {}).get("scale", "medium")

        analysis = {
            "domain": "system_architecture",
            "system_type": system_type,
            "scale": scale,
            "architecture_principles": [
                "Single Responsibility Principle (SRP)" if not is_hebrew else "עיקרון אחריות יחידה (SRP)",
                "Loose coupling via message queues or event bus" if not is_hebrew else "צימוד רפוי באמצעות תורים או אפיק אירועים",
                "Horizontal scaling with stateless services" if not is_hebrew else "הרחבה אופקית עם שירותים חסרי מצב",
                "Database per service (microservices) or schema separation" if not is_hebrew else "מסד נתונים לשירות (מיקרו-שירותים) או הפרדת סכמה",
                "API Gateway for unified entry point" if not is_hebrew else "שער API כנקודת כניסה מאוחדת",
                "Circuit breaker pattern for fault tolerance" if not is_hebrew else "תבנית מפסק מעגל לעמידות בתקלות",
            ],
            "recommended_stack": self._suggest_stack(system_type, scale),
            "anti_patterns_to_avoid": [
                "Big Ball of Mud (monolithic without boundaries)" if not is_hebrew else "כדור בוץ גדול (מונוליטי ללא גבולות)",
                "Distributed Monolith (microservices with tight coupling)" if not is_hebrew else "מונוליט מבוזר (מיקרו-שירותים עם צימוד הדוק)",
                "Gold Plating (over-engineering simple components)" if not is_hebrew else "ציפוי זהב (הנדסת יתר של רכיבים פשוטים)",
            ],
        }

        recommendations = [
            "Start with modular monolith, extract services later" if not is_hebrew else "התחל עם מונוליט מודולרי, חלץ שירותים בהמשך",
            "Design for observability from day one (metrics, logs, traces)" if not is_hebrew else "תכנן לנירות מיום אחד (מדדים, לוגים, מעקבים)",
            "Use Infrastructure as Code (Terraform/Pulumi)" if not is_hebrew else "השתמש בתשתית כקוד (Terraform/Pulumi)",
            "Implement CI/CD pipeline before production" if not is_hebrew else "הטמע צינור CI/CD לפני פרודקשן",
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            metadata={"system_type": system_type, "scale": scale, "domain": "architecture"},
        )

    def debug_analysis(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide systematic debugging analysis."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        error_log = (context or {}).get("error_log", "")
        environment = (context or {}).get("environment", "production")

        analysis = {
            "domain": "debugging",
            "environment": environment,
            "debug_methodology": [
                "1. Reproduce the issue consistently" if not is_hebrew else "1. שחזר את הבעיה באופן עקבי",
                "2. Isolate the failing component (binary search method)" if not is_hebrew else "2. בודד את הרכיב הכושל (שיטת חיפוש בינארי)",
                "3. Check recent changes (git bisect / deployment history)" if not is_hebrew else "3. בדוק שינויים אחרונים (git bisect / היסטוריית פריסה)",
                "4. Add targeted logging around failure point" if not is_hebrew else "4. הוסף לוגים ממוקדים סביב נקודת הכשל",
                "5. Verify environment and dependency versions" if not is_hebrew else "5. אמת את הסביבה וגרסאות התלות",
                "6. Test hypothesis with minimal reproduction case" if not is_hebrew else "6. בדוק השערה עם מקרה שחזור מינימלי",
            ],
            "common_root_causes": [
                "Race condition in concurrent code" if not is_hebrew else "תנאי מרוץ בקוד מקבילי",
                "Memory leak or resource exhaustion" if not is_hebrew else "דליפת זיכרון או exhaustion משאבים",
                "Configuration drift between environments" if not is_hebrew else "סחיפת תצורה בין סביבות",
                "Database connection pool exhaustion" if not is_hebrew else "ת exhaustion בריכת חיבורי מסד נתונים",
                "Third-party API rate limiting or downtime" if not is_hebrew else "הגבלת קצב API צד שלישי או השבתה",
            ],
        }

        recommendations = [
            "Add distributed tracing (OpenTelemetry)" if not is_hebrew else "הוסף מעקב מבוזר (OpenTelemetry)",
            "Set up error tracking (Sentry, Rollbar)" if not is_hebrew else "הקם מעקב שגיאות (Sentry, Rollbar)",
            "Implement health checks and readiness probes" if not is_hebrew else "הטמע בדיקות בריאות וסondes מוכנות",
            "Create runbook for common failure modes" if not is_hebrew else "צור ספר הפעלה למצבי כשל נפוצים",
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            metadata={"environment": environment, "domain": "debugging"},
        )

    def performance_optimize(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide performance optimization analysis."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        metric = (context or {}).get("metric", "latency")
        current_value = (context or {}).get("current_value", "unknown")
        target_value = (context or {}).get("target_value", "unknown")

        analysis = {
            "domain": "performance",
            "metric": metric,
            "current": current_value,
            "target": target_value,
            "optimization_axes": [
                "Caching strategy (Redis, CDN, application-level)" if not is_hebrew else "אסטרטגיית מטמון (Redis, CDN, רמת אפליקציה)",
                "Database query optimization (indexes, denormalization)" if not is_hebrew else "אופטימיזציית שאילתות DB (אינדקסים, denormalization)",
                "Async processing for I/O-bound operations" if not is_hebrew else "עיבוד אסינכרוני לפעולות מוגבלות I/O",
                "Connection pooling and keep-alive" if not is_hebrew else "בריכת חיבורים ו-keep-alive",
                "Load balancing and geographic distribution" if not is_hebrew else "איזון עומסים והפצה גיאוגרפית",
                "Code-level optimization (vectorization, algorithmic)" if not is_hebrew else "אופטימיזציה ברמת קוד (וקטוריזציה, אלגוריתמית)",
            ],
            "bottleneck_analysis": [
                "Profile CPU usage (cProfile, py-spy, async-profiler)" if not is_hebrew else "פרופיל שימוש CPU (cProfile, py-spy, async-profiler)",
                "Analyze memory allocation (tracemalloc, memray)" if not is_hebrew else "נתח הקצאת זיכרון (tracemalloc, memray)",
                "Measure I/O wait times (iostat, disk latency)" if not is_hebrew else "מדוד זמני המתנה I/O (iostat, דיסק latency)",
                "Check network latency between services" if not is_hebrew else "בדוק latency רשת בין שירותים",
            ],
        }

        recommendations = [
            "Implement Redis caching for hot data (expect 10-100x speedup)" if not is_hebrew else "הטמע מטמון Redis לנתונים חמים (צפי להאצה של 10-100x)",
            "Add database query timeout and N+1 detection" if not is_hebrew else "הוסף timeout לשאילתות DB וגילוי N+1",
            "Use connection pooling (PgBouncer for PostgreSQL)" if not is_hebrew else "השתמש בבריכת חיבורים (PgBouncer עבור PostgreSQL)",
            "Enable HTTP/2 and compression (Brotli/gzip)" if not is_hebrew else "אפשר HTTP/2 ודחיסה (Brotli/gzip)",
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            metadata={"metric": metric, "domain": "performance"},
        )

    def security_audit(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Perform security audit analysis."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        system_scope = (context or {}).get("scope", "web_application")

        analysis = {
            "domain": "cybersecurity",
            "scope": system_scope,
            "audit_framework": "OWASP ASVS Level 2 + NIST Cybersecurity Framework",
            "security_dimensions": [
                "Authentication & Authorization (OAuth 2.0 / OIDC best practices)" if not is_hebrew else "אימות והרשאה (מיטב תרגול OAuth 2.0 / OIDC)",
                "Input Validation & Output Encoding" if not is_hebrew else "אימות קלט וקידוד פלט",
                "Session Management & Token Security" if not is_hebrew else "ניהול סשנים ואבטחת טוקנים",
                "Cryptography (encryption at rest & in transit)" if not is_hebrew else "קריפטוגרפיה (הצפנה במנוחה ובתנועה)",
                "API Security (rate limiting, CORS, CSRF protection)" if not is_hebrew else "אבטחת API (הגבלת קצב, CORS, הגנת CSRF)",
                "Logging & Monitoring (SIEM integration)" if not is_hebrew else "רישום ומוניטורינג (אינטגרציית SIEM)",
                "Dependency & Supply Chain Security (SCA)" if not is_hebrew else "אבטחת תלות ושרשרת אספקה (SCA)",
            ],
            "critical_findings": [
                "CVE-2024-XXXX in dependency xyz (CVSS 9.8)" if not is_hebrew else "CVE-2024-XXXX בתלות xyz (CVSS 9.8)",
                "Missing Content Security Policy headers" if not is_hebrew else "חסרים כותרות מדיניות אבטחת תוכן",
                "Sensitive data logged in plain text" if not is_hebrew else "נתונים רגישים נרשמים בטקסט פשוט",
            ],
        }

        recommendations = [
            "Implement OWASP ASVS Level 2 compliance" if not is_hebrew else "הטמע ציות ל-OWASP ASVS רמה 2",
            "Add Web Application Firewall (WAF)" if not is_hebrew else "הוסף חומת אש לאפליקציות אינטרנט (WAF)",
            "Enable automated dependency scanning (Snyk, Dependabot)" if not is_hebrew else "אפשר סריקת תלות אוטומטית (Snyk, Dependabot)",
            "Conduct quarterly penetration testing" if not is_hebrew else "ערוך בדיקות חדירה רבעוניות",
            "Implement zero-trust network architecture" if not is_hebrew else "הטמע ארכיטקטורת רשת אמון אפס",
        ]

        risks = [
            "Critical: Unpatched vulnerabilities may lead to data breach" if not is_hebrew else "קריטי: פרצות לא מטושטשות עלולות להוביל לדליפת נתונים",
            "High: Insufficient logging hampers incident response" if not is_hebrew else "גבוה: רישום לקוי מפריע לתגובת תקרית",
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            risks=risks,
            metadata={"scope": system_scope, "domain": "security"},
        )

    def tech_stack_advise(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Advise on technology stack selection."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        project_type = (context or {}).get("project_type", "web_app")
        team_size = (context or {}).get("team_size", "small")
        budget = (context or {}).get("budget", "medium")

        stack = self._suggest_stack(project_type, "medium")

        analysis = {
            "domain": "tech_stack",
            "project_type": project_type,
            "team_size": team_size,
            "budget_tier": budget,
            "recommended_stack": stack,
            "rationale": [
                "Proven ecosystem with strong community support" if not is_hebrew else "אקוסיסטמה מוכחת עם תמיכת קהילה חזקה",
                "Talent availability in Israeli market" if not is_hebrew else "זמינות כישרונות בשוק הישראלי",
                "Scales from MVP to enterprise" if not is_hebrew else "מתרחב מ-MVP לארגוני",
            ],
        }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Prototype with chosen stack before full commitment" if not is_hebrew else "בנה אב טיפוס עם המחסנית הנבחרת לפני מחויבות מלאה",
                "Evaluate team expertise and learning curve" if not is_hebrew else "הערך את מומחיות הצוות ועקומת הלמידה",
            ],
            metadata={"project_type": project_type, "domain": "tech_stack"},
        )

    def get_disclaimer(self) -> str:
        """Engineering-specific disclaimer."""
        return (
            "המלצות הנדסיות מסופקות כקווים מנחים מקצועיים. יש להתאים כל "
            "פתרון לדרישות הספציפיות של הפרויקט, לבצע בדיקות מקיפות, "
            "ולשקול מגבלות תקציב, זמן וכישרונות צוות לפני יישום."
        )

    # ---- Internal helpers --------------------------------------------

    def _detect_engineering_domain(self, query: str) -> List[str]:
        """Detect engineering domain from query."""
        q = query.lower()
        domains = []
        domain_map = {
            "code": ["code", "review", "refactor", "function", "class", "module", "קוד", "בדיקה"],
            "debug": ["bug", "error", "exception", "crash", "debug", "fix", "broke", "באג", "שגיאה"],
            "architecture": ["architecture", "design", "system", "microservice", "scale", "ארכיטקטורה", "מערכת"],
            "security": ["security", "vulnerability", "pentest", "hack", "breach", "auth", "אבטחה", "פרצה"],
            "performance": ["performance", "optimize", "slow", "speed", "latency", "ביצועים", "איטי"],
            "database": ["database", "sql", "query", "index", "schema", "migration", "מסד נתונים"],
            "ai": ["ai", "ml", "machine learning", "model", "neural", "deep learning", "בינה מלאכותית"],
            "devops": ["devops", "ci/cd", "docker", "kubernetes", "deploy", "pipeline"],
            "frontend": ["frontend", "ui", "react", "vue", "angular", "css", "html"],
            "backend": ["backend", "api", "server", "rest", "graphql", "endpoint"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in q for kw in keywords):
                domains.append(domain)
        return domains if domains else ["general"]

    def _suggest_stack(self, system_type: str, scale: str) -> Dict[str, List[str]]:
        """Suggest technology stack based on system type and scale."""
        stacks = {
            "web_app": {
                "frontend": ["React + TypeScript", "Next.js"],
                "backend": ["Node.js / Express", "Python / FastAPI"],
                "database": ["PostgreSQL", "Redis"],
                "infrastructure": ["Docker", "AWS/GCP"],
            },
            "mobile": {
                "frontend": ["React Native", "Flutter"],
                "backend": ["Firebase", "Node.js"],
                "database": ["PostgreSQL", "MongoDB"],
                "infrastructure": ["AWS Amplify", "Google Cloud"],
            },
            "ai_ml": {
                "ml_framework": ["PyTorch", "Hugging Face Transformers"],
                "serving": ["FastAPI", "Triton Inference Server"],
                "data": ["Apache Spark", "Pandas", "DuckDB"],
                "infrastructure": ["Kubernetes", "AWS SageMaker / GCP Vertex AI"],
            },
            "embedded": {
                "platform": ["ESP32", "STM32", "Raspberry Pi"],
                "os": ["FreeRTOS", "Zephyr"],
                "language": ["C/C++", "Rust", "MicroPython"],
                "toolchain": ["PlatformIO", "Keil", "STM32CubeIDE"],
            },
            "general": {
                "recommended": ["Python / FastAPI", "PostgreSQL", "Redis", "Docker", "AWS/GCP"],
                "alt_stack": ["Node.js", "MongoDB", "React", "DigitalOcean"],
            },
        }
        return stacks.get(system_type, stacks["general"])

    def _analyze_ai_ml(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Analyze AI/ML specific questions."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        analysis = {
            "domain": "ai_ml",
            "considerations": [
                "Model selection: balance accuracy vs. inference speed vs. resource constraints" if not is_hebrew else "בחירת מודל: איזון דיוק, מהירות היקש ומגבלות משאבים",
                "Data quality and labeling accuracy are critical" if not is_hebrew else "איכות נתונים ודיוק תיוג הם קריטיים",
                "MLOps pipeline for reproducibility and deployment" if not is_hebrew else "צינור MLOps לשחזוריות ופריסה",
                "Evaluate fairness, bias, and explainability requirements" if not is_hebrew else "הערך דרישות הוגנות, הטיה וניתנות להסבר",
            ],
        }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Start with pretrained models (transfer learning)" if not is_hebrew else "התחל עם מודלים מאומנים מראש (למידת העברה)",
                "Establish baseline metrics before optimization" if not is_hebrew else "קבע מדדים בסיסיים לפני אופטימיזציה",
            ],
            metadata={"domain": "ai_ml"},
        )



# =============================================================================
#                     3. SENIOR DOCTOR PERSONA
# =============================================================================

class SeniorDoctorPersona(BaseExpertPersona):
    """
    Chief of Medicine with expertise across all medical specialties.
    Provides symptom analysis, differential diagnosis, treatment guidance,
    drug interaction checks, and emergency triage — always with medical disclaimer.
    Includes Israeli healthcare context (Kupat Holim, hospitals, medications).
    """

    def __init__(
        self,
        name: str = "Dr. Sarah Klein",
        title: str = "Chief of Medicine",
        language_preference: str = "he",
        formality_level: str = "professional",
    ):
        super().__init__(
            name=name,
            title=title,
            expertise_domains=[
                "internal_medicine",
                "cardiology",
                "neurology",
                "oncology",
                "orthopedics",
                "pediatrics",
                "dermatology",
                "psychiatry",
                "emergency_medicine",
                "surgery",
                "radiology",
                "pathology",
                "pharmacology",
                "nutrition",
                "sports_medicine",
                "gastroenterology",
                "endocrinology",
                "pulmonology",
                "nephrology",
                "hematology",
                "infectious_disease",
                "immunology",
                "rheumatology",
                "geriatrics",
                "obstetrics_gynecology",
            ],
            language_preference=language_preference,
            formality_level=formality_level,
        )
        self._israeli_healthcare: Dict[str, str] = {
            "kupat_cholim": "קופת חולים (Clalit, Maccabi, Leumit, Meuhedet)",
            "hitchayvut": "חוק זכויות החולה, התשנ\"ו-1996",
            "emergency_dial": "מד\"א (Magen David Adom) — Dial 101",
            "poison_control": "מרכז רפואי לטיפול בחולי רעל — Dial 04-854-1900",
            "mental_health_emergency": "ער\"ן (ERAN) — Dial 1201",
        }
        self._severity_levels: Dict[str, Dict[str, Any]] = {
            "critical": {
                "color": "RED",
                "action": "Seek emergency care immediately (call ambulance)" if True else "פנה לטיפול דחוף מיידי (התקשר למד\"א)",
                "response_time": "Immediate",
            },
            "urgent": {
                "color": "ORANGE",
                "action": "Seek urgent care within 2-4 hours" if True else "פנה לטיפול דחוף תוך 2-4 שעות",
                "response_time": "2-4 hours",
            },
            "moderate": {
                "color": "YELLOW",
                "action": "Schedule appointment within 24-48 hours" if True else "קבע תור תוך 24-48 שעות",
                "response_time": "24-48 hours",
            },
            "low": {
                "color": "GREEN",
                "action": "Monitor symptoms, schedule routine appointment" if True else "עקוב אחר תסמינים, קבע תור שגרתי",
                "response_time": "7-14 days",
            },
        }

    # ---- Core analysis ------------------------------------------------

    def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main medical analysis engine. Routes to specialized medical analysis
        based on detected symptoms or medical domain.
        """
        is_hebrew = _detect_hebrew(query)
        domain = self._detect_medical_domain(query)

        if any(d in domain for d in ["emergency", "chest_pain", "breathing", "severe"]):
            return self.emergency_triage(query, context, is_hebrew)
        elif any(d in domain for d in ["symptom", "pain", "fever", "headache"]):
            return self.symptom_analysis(query, context, is_hebrew)
        elif any(d in domain for d in ["medication", "drug", "dosage", "interaction"]):
            return self.drug_interactions(query, context, is_hebrew)
        elif any(d in domain for d in ["nutrition", "diet", "food", "supplement"]):
            return self._analyze_nutrition(query, context, is_hebrew)
        else:
            return self.medical_explanation(query, context, is_hebrew)

    def symptom_analysis(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Analyze symptoms and provide structured assessment.
        IMPORTANT: Always includes medical disclaimer and triage guidance.
        """
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        symptoms = (context or {}).get("symptoms", [])
        duration = (context or {}).get("duration", "unspecified")
        age = (context or {}).get("age", "unspecified")
        gender = (context or {}).get("gender", "unspecified")
        medical_history = (context or {}).get("medical_history", [])

        # Build structured symptom assessment
        if is_hebrew:
            analysis = {
                "domain": "symptom_analysis",
                "presenting_complaint": query,
                "duration": duration,
                "patient_context": {"age": age, "gender": gender, "history": medical_history},
                "assessment": (
                    f"התלונה המוצגת: {query}. "
                    f"משך התסמינים: {duration}. "
                    f"יש לבצע הערכה רפואית מקיפה הכוללת בדיקה פיזית, "
                    f"בדיקות מעבדה מתאימות, ובהתאם לצורך — בדיקות דימות. "
                    f"האבחנה המבדלת תלויה בנסיבות הקליניות הספציפיות של המטופל."
                ),
                "differential_diagnosis": [
                    "יש לשלול מצבים דחופים לפני בחינת אבחנות אפשריות אחרות",
                    "הערכה קלינית מלאה נדרשת — לא ניתן לאבחן מבלי לבחון את המטופל",
                ],
                "triage_level": "moderate",
                "next_steps": [
                    "פנה לרופא/ה יועצ/ת לבירור ואבחון",
                    "תעד את התסמינים, משכם, ושינויים במצב",
                    "הכן רשימת תרופות נוכחיות והיסטוריה רפואית",
                ],
            }
            recommendations = [
                "פנה לבירור רפואי אצל רופא/ה מומחה/ית",
                "במקרה של החמרה — פנה למיון מיידית",
                "אל תתעלם מתסמינים החמורים או הנמשכים",
            ]
            risks = [
                "אזהרה: מידע זה אינו מהווה ייעוץ רפואי או אבחנה. יש לפנות לרופא מוסמך.",
                "במקרה של מצב חירום — התקשר למד\"א בטלפון 101.",
            ]
        else:
            analysis = {
                "domain": "symptom_analysis",
                "presenting_complaint": query,
                "duration": duration,
                "patient_context": {"age": age, "gender": gender, "history": medical_history},
                "assessment": (
                    f"Presenting complaint: {query}. "
                    f"Duration: {duration}. "
                    f"A comprehensive medical evaluation including physical examination, "
                    f"appropriate laboratory tests, and imaging studies if indicated is required. "
                    f"Differential diagnosis depends on the specific clinical circumstances."
                ),
                "differential_diagnosis": [
                    "Urgent conditions must be ruled out before considering alternative diagnoses",
                    "Full clinical assessment required — diagnosis cannot be made without examination",
                ],
                "triage_level": "moderate",
                "next_steps": [
                    "Consult a physician for evaluation and diagnosis",
                    "Document symptoms, duration, and any changes in condition",
                    "Prepare list of current medications and medical history",
                ],
            }
            recommendations = [
                "Seek medical evaluation by a qualified physician",
                "If symptoms worsen — seek emergency care immediately",
                "Do not ignore severe or persistent symptoms",
            ]
            risks = [
                "WARNING: This information is not medical advice or diagnosis. Consult a licensed physician.",
                "In case of emergency — call emergency services (101 in Israel).",
            ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            risks=risks,
            metadata={
                "duration": duration,
                "triage": "moderate",
                "domain": "symptom_analysis",
            },
        )

    def differential_diagnosis(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide structured differential diagnosis framework."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        if is_hebrew:
            analysis = {
                "domain": "differential_diagnosis",
                "methodology": "VINDICATE — Vascular, Inflammatory, Neoplastic, Degenerative, Idiopathic, Congenital, Autoimmune, Traumatic, Endocrine/Metabolic",
                "assessment": (
                    "אבחנה מבדלת מבוססת על מיטב הנתונים הקליניים הזמינים. "
                    "יש להתחיל בשלילת מצבים מסכני חיים, ולאחר מכן לבחון אבחנות סבירות "
                    "לפי הסתברות, מחלות נפוצות באוכלוסייה, והקשר הקליני."
                ),
                "life_threatening_to_rule_out": [
                    "מצבי חירום קרדיווסקולריים",
                    "זיהום חמור או ספסיס",
                    "מצבי חירום נוירולוגיים",
                ],
                "common_causes": ["יש להעריך לפי הגיל, המין, וההיסטוריה הרפואית של המטופל"],
            }
        else:
            analysis = {
                "domain": "differential_diagnosis",
                "methodology": "VINDICATE — Vascular, Inflammatory, Neoplastic, Degenerative, Idiopathic, Congenital, Autoimmune, Traumatic, Endocrine/Metabolic",
                "assessment": (
                    "Differential diagnosis based on best available clinical data. "
                    "Begin by ruling out life-threatening conditions, then evaluate likely "
                    "diagnoses based on probability, population prevalence, and clinical context."
                ),
                "life_threatening_to_rule_out": [
                    "Cardiovascular emergencies",
                    "Severe infection or sepsis",
                    "Neurological emergencies",
                ],
                "common_causes": ["Evaluate based on patient's age, gender, and medical history"],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Seek in-person medical evaluation" if not is_hebrew else "פנה להערכה רפואית פנים אל פנים",
            ],
            risks=[
                "This is NOT a diagnosis — consult a physician immediately" if not is_hebrew else "זוהי אינה אבחנה — פנה לרופא מיד",
            ],
            metadata={"domain": "differential_diagnosis"},
        )

    def treatment_options(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide information about treatment options."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        condition = (context or {}).get("condition", query)

        if is_hebrew:
            analysis = {
                "domain": "treatment_options",
                "condition": condition,
                "approach": "טיפול תמיד מותאם אישית — לא קיימת אבחנה אחידה לכל המטופלים",
                "treatment_categories": [
                    "טיפול תרופתי — בהתאם להנחיות הרפואיות המעודכנות",
                    "טיפול ללא תרופות — שינויי אורח חיים, פיזיותרפיה, טיפול תזונתי",
                    "טיפולים מתקדמים — בהתאם להתוויות רפואיות ספציפיות",
                ],
            }
            recommendations = [
                "שוחח עם רופא/ה על כל אפשרויות הטיפול הזמינות",
                "בחן את היתרונות והסיכונים של כל אפשרות",
                "היוועץ לגבי תופעות לוואי אפשריות",
                "שקול חוות דעת שנייה עבור מצבים מורכבים",
            ]
        else:
            analysis = {
                "domain": "treatment_options",
                "condition": condition,
                "approach": "Treatment is always personalized — no one-size-fits-all approach",
                "treatment_categories": [
                    "Pharmacological — per updated medical guidelines",
                    "Non-pharmacological — lifestyle changes, physiotherapy, nutritional therapy",
                    "Advanced treatments — per specific medical indications",
                ],
            }
            recommendations = [
                "Discuss all available treatment options with your physician",
                "Evaluate benefits and risks of each option",
                "Consult about possible side effects",
                "Consider a second opinion for complex cases",
            ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            risks=[
                "Always consult your physician before starting or changing treatment" if not is_hebrew
                else "תמיד התייעץ עם הרופא שלך לפני תחילת טיפול או שינוי טיפול"
            ],
            metadata={"condition": condition, "domain": "treatment"},
        )

    def drug_interactions(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Check drug interactions and provide pharmaceutical guidance."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        medications = (context or {}).get("medications", [])
        allergies = (context or {}).get("allergies", [])

        if is_hebrew:
            analysis = {
                "domain": "pharmacology",
                "medications_reviewed": medications,
                "allergies_documented": allergies,
                "interaction_check": "בדיקת אינטראקציות בין תרופתיות נעשתה לפי מקורות מקצועיים מוכרים",
                "known_interactions": [
                    "יש לבדוק אינטראקציות ב- Lexicomp, Drugs.com, או מקור מקצועי מוכר אחר",
                    "תרופות הניתנות על ידי רופאים שונים עלולות להת interacts — יש ליידע את כל הרופאים",
                ],
                "general_precautions": [
                    "אל תשלב תרופות ללא ייעוץ רפואי",
                    "יידע את הרופא על כל התרופות, תוספים, וצמחי מרפא שאתה נוטל",
                    "בדוק תופעות לוואי ברשומת התרופה",
                ],
            }
            recommendations = [
                "התייעץ עם רוקח או רופא לגבי כל שילוב תרופתי",
                "השתמש בכלי אחד לבדיקת אינטראקציות (כגון Lexicomp)",
                "שמור רשימה מעודכנת של כל התרופות והתוספים שאתה נוטל",
            ]
        else:
            analysis = {
                "domain": "pharmacology",
                "medications_reviewed": medications,
                "allergies_documented": allergies,
                "interaction_check": "Drug-drug interaction check performed per recognized professional sources",
                "known_interactions": [
                    "Check interactions using Lexicomp, Drugs.com, or other recognized professional source",
                    "Medications prescribed by different doctors may interact — inform all physicians",
                ],
                "general_precautions": [
                    "Do not combine medications without medical advice",
                    "Inform your doctor of all medications, supplements, and herbal remedies",
                    "Check side effects on medication leaflet",
                ],
            }
            recommendations = [
                "Consult a pharmacist or physician about any drug combination",
                "Use a single interaction checker tool (e.g., Lexicomp)",
                "Keep an updated list of all medications and supplements",
            ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            risks=[
                "ALWAYS verify drug interactions with a pharmacist or physician" if not is_hebrew
                else "תמיד אמת אינטראקציות תרופתיות עם רוקח או רופא"
            ],
            metadata={"domain": "pharmacology"},
        )

    def emergency_triage(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Emergency triage assessment.
        CRITICAL: Always directs to emergency services for serious symptoms.
        """
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        q = query.lower()

        # Critical symptom detection
        critical_symptoms = [
            "chest pain", "can't breathe", "shortness of breath", "unconscious",
            "severe bleeding", "stroke", "heart attack", "seizure", "anaphylaxis",
            "כאב חזה", "קושי בנשימה", "התעלפות", "שבץ", "דימום חמור",
            "חום גבוה מאוד", "כוויה חמורה", "תסמיני אנפילקסיס",
        ]
        is_critical = any(sym in q for sym in critical_symptoms)

        if is_hebrew:
            if is_critical:
                analysis = {
                    "URGENCY": "🔴 קריטי — דחוף ביותר",
                    "assessment": "התסמינים המתוארים עלולים להצביע על מצב חיים מסכן. יש לפנות לטיפול רפואי דחוף מיידית.",
                    "immediate_action": "התקשר למד\"א: 101 או גש לחדר מיון הקרוב ביותר",
                    "do_not": [
                        "אל תנהל את המצב לבד",
                        "אל תחכה לשיפור",
                        "אל תיקח תרופות ללא הדרכה רפואית",
                    ],
                }
                triage_level = "critical"
            else:
                analysis = {
                    "URGENCY": "🟡 בינוני — נדרש הערכה רפואית",
                    "assessment": "התסמינים דורשים הערכה רפואית. אם מתעוררת דאגה — פנה למיון או התקשר לקופת החולים.",
                    "next_steps": [
                        "התקשר למוקד הרפואי של קופת החולים",
                        "פנה למיון אם המצב מתדרדר",
                        "תעד את התסמינים והמשך שלהם",
                    ],
                }
                triage_level = "moderate"

            emergency_numbers = {
                "מד\"א (מגן דוד אדום)": "101",
                "מרכז רעלים": "04-854-1900",
                "ער\"ן (סיוע נפשי)": "1201",
                "משטרת ישראל": "100",
            }
        else:
            if is_critical:
                analysis = {
                    "URGENCY": "🔴 CRITICAL — Emergency",
                    "assessment": "The described symptoms may indicate a life-threatening condition. Seek emergency medical care immediately.",
                    "immediate_action": "Call emergency services or go to the nearest ER immediately",
                    "do_not": [
                        "Do not manage the situation alone",
                        "Do not wait for improvement",
                        "Do not take medications without medical guidance",
                    ],
                }
                triage_level = "critical"
            else:
                analysis = {
                    "URGENCY": "🟡 MODERATE — Medical evaluation needed",
                    "assessment": "Symptoms require medical evaluation. If concerned — go to ER or contact your healthcare provider.",
                    "next_steps": [
                        "Call your healthcare provider's hotline",
                        "Go to ER if condition worsens",
                        "Document symptoms and their progression",
                    ],
                }
                triage_level = "moderate"

            emergency_numbers = {
                "Magen David Adom (Israel)": "101",
                "Poison Control Center": "04-854-1900",
                "ERAN (Emotional Support)": "1201",
                "Police": "100",
            }

        analysis["emergency_numbers"] = emergency_numbers
        analysis["domain"] = "emergency_triage"

        risks = [
            "🚨 THIS IS NOT A DIAGNOSIS — Seek immediate professional medical care" if not is_hebrew
            else "🚨 זוהי אינה אבחנה — פנה מיד לטיפול רפואי מקצועי",
            "In an emergency, every minute counts" if not is_hebrew else "במצב חירום, כל דקה חשובה",
        ]

        return self._build_response(
            query=query,
            analysis=analysis,
            risks=risks,
            metadata={"triage_level": triage_level, "domain": "emergency_triage", "is_critical": is_critical},
        )

    def medical_explanation(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide educational medical explanation."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        topic = (context or {}).get("topic", query)

        if is_hebrew:
            analysis = {
                "domain": "medical_education",
                "topic": topic,
                "explanation": (
                    f"הנושא '{topic}' נחקר בהרחבה ברפואה המודרנית. "
                    f"להלן הסבר כללי לצורכי השכלה בלבד. "
                    f"למידע אישי — פנה לרופא מוסמך."
                ),
                "key_points": [
                    "הגוף האנושי הוא מערכת מורכבת של מערכות משולבות",
                    "כל מטופל הוא יחידה ביולוגית ייחודית",
                    "התקדמות ברפואה מתבססת על ראיות מדעיות",
                ],
            }
        else:
            analysis = {
                "domain": "medical_education",
                "topic": topic,
                "explanation": (
                    f"The topic '{topic}' has been extensively studied in modern medicine. "
                    f"Below is a general explanation for educational purposes only. "
                    f"For personal medical information — consult a licensed physician."
                ),
                "key_points": [
                    "The human body is a complex system of integrated systems",
                    "Every patient is a unique biological unit",
                    "Medical advancement is based on scientific evidence",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            metadata={"topic": topic, "domain": "medical_education"},
        )

    def _analyze_nutrition(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide nutritional guidance."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        goal = (context or {}).get("goal", "general_health")

        if is_hebrew:
            analysis = {
                "domain": "nutrition",
                "goal": goal,
                "principles": [
                    "אכילה מאוזנת הכוללת את כל קבוצות המזון",
                    "שתייה מספקת של מים לאורך היום",
                    "הגבלת סוכרים מוספים ומזון מעובד",
                    "העדפת ירקות, פירות, דגנים מלאים, וחלבונים איכותיים",
                    "שימוש במלח ובשומן רווי במתינות",
                ],
            }
            recommendations = [
                "התייעץ עם דיאטנ/ית קלינית לתוכנית אישית",
                "בצע בדיקות דם לפני שינויים תזונתיים משמעותיים",
                "קח בחשבון מצבים רפואיים קיימים בהתאמת התזונה",
            ]
        else:
            analysis = {
                "domain": "nutrition",
                "goal": goal,
                "principles": [
                    "Balanced diet including all food groups",
                    "Adequate water intake throughout the day",
                    "Limit added sugars and processed foods",
                    "Prioritize vegetables, fruits, whole grains, quality proteins",
                    "Moderate salt and saturated fat intake",
                ],
            }
            recommendations = [
                "Consult a clinical dietitian for personalized plan",
                "Get blood tests before significant dietary changes",
                "Consider existing medical conditions when adjusting diet",
            ]

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=recommendations,
            risks=[
                "Consult a physician before major dietary changes, especially if you have medical conditions" if not is_hebrew
                else "התייעץ עם רופא לפני שינויים תזונתיים גדולים, במיוחד אם יש לך מצבים רפואיים"
            ],
            metadata={"goal": goal, "domain": "nutrition"},
        )

    def get_disclaimer(self) -> str:
        """
        Medical disclaimer — ALWAYS included with medical persona.
        This is the most critical disclaimer in the system.
        """
        return (
            "⚠️ הערת אזהרה רפואית חשובה: המידע המסופק הוא לידע כללי בלבד ואינו "
            "מהווה ייעוץ רפואי, אבחנה, או תחליף לפנייה לרופא/ה מוסמך/ת. "
            "אין להסתמך על מידע זה לצורך קבלת החלטות רפואיות. "
            "במקרה של מצב חירום רפואי — התקשר למד\"א בטלפון 101 או גש לחדר מיון הקרוב. "
            "תמיד פנה לרופא מוסמך לקבלת ייעוץ רפואי מקצועי."
        )

    # ---- Internal helpers --------------------------------------------

    def _detect_medical_domain(self, query: str) -> List[str]:
        """Detect medical domain from query."""
        q = query.lower()
        domains = []
        domain_map = {
            "emergency": ["emergency", "critical", "severe", "unconscious", "bleeding", "חירום", "חמור", "התעלפות", "דימום"],
            "chest_pain": ["chest pain", "heart", "לב", "כאב חזה", "לחץ בחזה"],
            "breathing": ["breathe", "breath", "shortness", "נשימה", "קושי בנשימה"],
            "symptom": ["symptom", "pain", "ache", "fever", "nausea", "dizzy", "תסמין", "כאב", "חום", "בחילה"],
            "headache": ["headache", "migraine", "כאב ראש", "מיגרנה"],
            "medication": ["drug", "medication", "medicine", "pill", "dosage", "תרופה", "תרופות", "מינון"],
            "nutrition": ["diet", "nutrition", "food", "eat", "supplement", "תזונה", "דיאטה", "אוכל"],
            "cardiology": ["heart", "blood pressure", "cardiac", "cardio", "לב", "לחץ דם"],
            "dermatology": ["skin", "rash", "acne", "eczema", "עור", "פריחה", "פצעים"],
            "orthopedics": ["bone", "joint", "fracture", "sprain", "שבר", "מפרק", "עצם"],
            "psychiatry": ["depression", "anxiety", "mental", "stress", "דיכאון", "חרדה", "נפשי"],
            "pediatrics": ["child", "baby", "infant", "pediatric", "ילד", "תינוק"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in q for kw in keywords):
                domains.append(domain)
        return domains if domains else ["general"]



# =============================================================================
#                     4. BUSINESS ADVISOR PERSONA
# =============================================================================

class BusinessAdvisorPersona(BaseExpertPersona):
    """
    Senior Business Strategist with expertise across all business domains.
    Specializes in Israeli market dynamics, startup ecosystem,
    fundraising, M&A, financial modeling, and strategic planning.
    Provides SWOT analysis, market analysis, pitch reviews, and growth strategies.
    """

    def __init__(
        self,
        name: str = "Moshe Abramson",
        title: str = "Senior Business Strategist",
        language_preference: str = "he",
        formality_level: str = "professional",
    ):
        super().__init__(
            name=name,
            title=title,
            expertise_domains=[
                "business_strategy",
                "financial_planning",
                "marketing",
                "operations",
                "human_resources",
                "startup_advisory",
                "mergers_acquisitions",
                "investment_analysis",
                "leadership",
                "negotiation",
                "market_research",
                "competitive_analysis",
                "pricing_strategy",
                "revenue_optimization",
                "business_development",
                "go_to_market",
                "product_strategy",
                "corporate_governance",
                "risk_management",
                "digital_transformation",
            ],
            language_preference=language_preference,
            formality_level=formality_level,
        )
        self._israeli_market_data: Dict[str, Any] = {
            "gdp_2024": "$530B (estimated)",
            "startup_count": "6,000+ active startups",
            "unicorns": "90+ (per 2024 data)",
            "rd_spending": "5.6% of GDP (highest in OECD)",
            "key_sectors": ["Cybersecurity", "AI/ML", "Fintech", "Healthtech", "Foodtech", "Clean Energy"],
            "government_programs": ["Israel Innovation Authority", "BIRD Foundation", "MAGNET"],
            "tax_incentives": "Angel Law — tax benefits for Israeli startup investors",
        }

    # ---- Core analysis ------------------------------------------------

    def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main business analysis engine. Routes to specialized analysis
        based on detected business domain.
        """
        is_hebrew = _detect_hebrew(query)
        domain = self._detect_business_domain(query)

        if any(d in domain for d in ["swot", "strategy", "analysis"]):
            return self.swot_analysis(query, context, is_hebrew)
        elif any(d in domain for d in ["financial", "model", "revenue", "budget"]):
            return self.financial_model(query, context, is_hebrew)
        elif any(d in domain for d in ["market", "competition", "industry"]):
            return self.market_analysis(query, context, is_hebrew)
        elif any(d in domain for d in ["pitch", "presentation", "investor"]):
            return self.pitch_review(query, context, is_hebrew)
        elif any(d in domain for d in ["negotiation", "deal", "terms"]):
            return self.negotiation_strategy(query, context, is_hebrew)
        elif any(d in domain for d in ["growth", "scale", "expand"]):
            return self.growth_plan(query, context, is_hebrew)
        else:
            return self._general_business_advice(query, context, is_hebrew)

    def swot_analysis(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Perform SWOT analysis."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        subject = (context or {}).get("subject", "organization")
        industry = (context or {}).get("industry", "technology")

        if is_hebrew:
            analysis = {
                "domain": "swot_analysis",
                "subject": subject,
                "industry": industry,
                "SWOT": {
                    "חוזקות (Strengths)": [
                        "כוח אדם איכותי ומיומן (הייטק ישראלי)",
                        "תרבות יזמות חזקה ותמיכה במצוינות",
                        "אקוסיסטמת סטארטאפים מפותחת עם גישה לכספים",
                        "R&D ברמה עולמית — 5.6% מהתמ\"ג",
                    ],
                    "חולשות (Weaknesses)": [
                        "שוק מקומי קטן (חסרונו והיתרון — חייבים לחשוב גלובלי)",
                        "עלויות שכר גבוהות בהשוואה עולמית",
                        "תלות בכוח אדם מקומי — מחסור במהנדסים",
                        "מרחק גיאוגרפי משווקי מפתח (אירופה, ארה\"ב)",
                    ],
                    "הזדמנויות (Opportunities)": [
                        "AI Revolution — דור חדש של מוצרים ושירותים",
                        "Climate Tech — מימון ממשלתי ודרישה גוברת",
                        "הסכמי אברהם — שווקים חדשים במזרח התיכון",
                        "Remote Work — גישה לכוח אדם גלובלי",
                    ],
                    "איומים (Threats)": [
                        "תחרות גלובית מתגברת (הודו, מזרח אירופה)",
                        "אי ודאות גיאופוליטית ורגולטורית",
                        "התייקרות עלויות הפיתוח",
                        "שינויים בשוק ההון הגלובלי",
                    ],
                },
            }
        else:
            analysis = {
                "domain": "swot_analysis",
                "subject": subject,
                "industry": industry,
                "SWOT": {
                    "Strengths": [
                        "High-quality skilled workforce (Israeli hi-tech)",
                        "Strong entrepreneurial culture and excellence support",
                        "Developed startup ecosystem with funding access",
                        "World-class R&D — 5.6% of GDP",
                    ],
                    "Weaknesses": [
                        "Small local market (forces global thinking)",
                        "High salary costs compared globally",
                        "Dependency on local talent — engineer shortage",
                        "Geographic distance from key markets (EU, US)",
                    ],
                    "Opportunities": [
                        "AI Revolution — new generation of products and services",
                        "Climate Tech — government funding and growing demand",
                        "Abraham Accords — new Middle East markets",
                        "Remote Work — access to global talent pool",
                    ],
                    "Threats": [
                        "Intensifying global competition (India, Eastern Europe)",
                        "Geopolitical and regulatory uncertainty",
                        "Rising development costs",
                        "Changes in global capital markets",
                    ],
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Leverage strengths to capture AI opportunities" if not is_hebrew else "נצל חוזקות כדי לתפוס הזדמנויות AI",
                "Address talent shortage through remote hiring" if not is_hebrew else "טפל במחסור בכוח אדם באמצעות גיוס מרחוק",
                "Develop go-to-market strategy for Abraham Accord markets" if not is_hebrew else "פתח אסטרטגיית go-to-market לשווקי הסכמי אברהם",
            ],
            metadata={"subject": subject, "domain": "swot"},
        )

    def financial_model(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Build financial model framework."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        model_type = (context or {}).get("model_type", "revenue_projection")
        period_years = (context or {}).get("period_years", 5)

        if is_hebrew:
            analysis = {
                "domain": "financial_modeling",
                "model_type": model_type,
                "projection_period": f"{period_years} שנים",
                "model_components": [
                    "הכנסות — מודל צמיחה מבוסס ARR/MRR (SaaS) או עסקאות",
                    "עלויות — COGS, S&M, R&D, G&A כאחוז מההכנסות",
                    "תזרים מזומנים — ניתוח חודשי/רבעוני",
                    "יחסי כלכלה — LTV/CAC, Payback Period, Gross Margin",
                    "Break-even Analysis — נקודת איזון הכנסות/הוצאות",
                    "Sensitivity Analysis — תרחישי בסיס, אופטימי, פסימי",
                ],
                "key_metrics": {
                    "LTV/CAC": ">3.0 is healthy",
                    "Gross Margin": ">70% for SaaS",
                    "Monthly Burn": "Monitor against runway",
                    "Payback Period": "<12 months ideal",
                },
            }
        else:
            analysis = {
                "domain": "financial_modeling",
                "model_type": model_type,
                "projection_period": f"{period_years} years",
                "model_components": [
                    "Revenue — growth model based on ARR/MRR (SaaS) or transactions",
                    "Costs — COGS, S&M, R&D, G&A as percentage of revenue",
                    "Cash Flow — monthly/quarterly analysis",
                    "Unit Economics — LTV/CAC, Payback Period, Gross Margin",
                    "Break-even Analysis — revenue/expense balance point",
                    "Sensitivity Analysis — base, optimistic, pessimistic scenarios",
                ],
                "key_metrics": {
                    "LTV/CAC": ">3.0 is healthy",
                    "Gross Margin": ">70% for SaaS",
                    "Monthly Burn": "Monitor against runway",
                    "Payback Period": "<12 months ideal",
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Build bottom-up revenue model (per customer/product)" if not is_hebrew else "בנה מודל הכנסות מלמטה למעלה (לפי לקוח/מוצר)",
                "Include 3 scenarios: base, best-case, worst-case" if not is_hebrew else "כלול 3 תרחישים: בסיס, מקרה הטוב ביותר, מקרה הרע ביותר",
                "Validate assumptions with market data" if not is_hebrew else "אמת הנחות עם נתוני שוק",
            ],
            metadata={"model_type": model_type, "domain": "financial_modeling"},
        )

    def market_analysis(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide market analysis framework."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        market = (context or {}).get("market", "technology")
        geography = (context or {}).get("geography", "global")

        if is_hebrew:
            analysis = {
                "domain": "market_analysis",
                "market": market,
                "geography": geography,
                "analysis_framework": "PESTLE + Porter's 5 Forces",
                "dimensions": [
                    "גודל שוק (TAM/SAM/SOM) — הערכת פוטנציאל ההכנסות",
                    "קצב צמיחה (CAGR) — מגמות ותחזיות לטווח קצר וארוך",
                    "תחרות — מספר שחקנים, ריכוזיות, מחסומי כניסה",
                    "מגמות טכנולוגיות — השפעת AI, אוטומציה, ענן",
                    "רגולציה — GDPR, תקנות מקומיות, הסמכות נדרשות",
                    "צרכנים — פרופיל לקוחות, כאבי צרכנים, נכונות לשלם",
                ],
            }
        else:
            analysis = {
                "domain": "market_analysis",
                "market": market,
                "geography": geography,
                "analysis_framework": "PESTLE + Porter's 5 Forces",
                "dimensions": [
                    "Market Size (TAM/SAM/SOM) — revenue potential estimate",
                    "Growth Rate (CAGR) — short and long-term trends and forecasts",
                    "Competition — number of players, concentration, entry barriers",
                    "Technology Trends — AI, automation, cloud impact",
                    "Regulation — GDPR, local regulations, required certifications",
                    "Customers — customer profile, pain points, willingness to pay",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Survey 20+ potential customers before building" if not is_hebrew else "סקר 20+ לקוחות פוטנציאליים לפני בנייה",
                "Analyze top 3 competitors' pricing and positioning" if not is_hebrew else "נתח תמחור ומיצוב של 3 מתחרים מובילים",
                "Validate TAM with bottom-up calculation" if not is_hebrew else "אמת TAM עם חישוב מלמטה למעלה",
            ],
            metadata={"market": market, "geography": geography, "domain": "market_analysis"},
        )

    def pitch_review(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Review investor pitch deck or presentation."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        stage = (context or {}).get("stage", "seed")

        if is_hebrew:
            analysis = {
                "domain": "pitch_review",
                "stage": stage,
                "essential_slides": [
                    "1. פתיחה — בעיה + פתרון בתמונה אחת",
                    "2. שוק — TAM/SAM/SOM עם מקורות נתונים",
                    "3. מוצר — Demo או תיאור ויזואלי ברור",
                    "4. מודל עסקי — איך מרוויחים כסף",
                    "5. צמיחה — מדדים מרכזיים (traction)",
                    "6. תחרות — מטריצת תחרות ייחודיות",
                    "7. צוות — ניסיון רלוונטי והישגים",
                    "8. פיננסים — תחזית 3-5 שנים, צרכי הון",
                    "9. Close — הקצאת הון, שימוש בכספים, ציר זמן",
                ],
                "common_mistakes": [
                    "טכנולוגיה מדי — צריך להתמקד בבעיה ובשוק",
                    "TAM מופרז ללא בסיס נתונים",
                    "חוסר בהירות במודל העסקי",
                    "צוות ללא ניסיון רלוונטי מוצג",
                    "תחזית לא ריאליסטית (הוקי סטיק)",
                ],
            }
        else:
            analysis = {
                "domain": "pitch_review",
                "stage": stage,
                "essential_slides": [
                    "1. Opening — Problem + Solution in one visual",
                    "2. Market — TAM/SAM/SOM with data sources",
                    "3. Product — Demo or clear visual description",
                    "4. Business Model — how you make money",
                    "5. Traction — key metrics showing growth",
                    "6. Competition — differentiation matrix",
                    "7. Team — relevant experience and achievements",
                    "8. Financials — 3-5 year projection, capital needs",
                    "9. Close — allocation of funds, use of proceeds, timeline",
                ],
                "common_mistakes": [
                    "Too technical — focus on problem and market",
                    "Inflated TAM without data backing",
                    "Lack of clarity in business model",
                    "Team without relevant experience presented",
                    "Unrealistic projection (hockey stick)",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Lead with the problem, not the technology" if not is_hebrew else "התחל עם הבעיה, לא עם הטכנולוגיה",
                "Show traction data (users, revenue, growth %)" if not is_hebrew else "הצג נתוני traction (משתמשים, הכנסות, אחוז צמיחה)",
                "Practice the pitch 10+ times before presenting" if not is_hebrew else "תרגל את המצגת 10+ פעמים לפני ההגשה",
            ],
            metadata={"stage": stage, "domain": "pitch_review"},
        )

    def negotiation_strategy(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide negotiation strategy and tactics."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        negotiation_type = (context or {}).get("negotiation_type", "general")

        if is_hebrew:
            analysis = {
                "domain": "negotiation",
                "type": negotiation_type,
                "principles": [
                    "הכר את BATNA שלך (Best Alternative to Negotiated Agreement)",
                    "הכר את BATNA של הצד השני — מקור העוצמה שלך",
                    "הפרד בין אנשים לבעיה (Getting to Yes)",
                    "תתמקד באינטרסים, לא בעמדות",
                    "מצא אפשרויות win-win ליצירת ערך",
                    "השתמש במידע אובייקטיבי כקריטריון",
                ],
                "tactics": [
                    "Anchor high (but reasonably)",
                    "Silence is power — let the other side fill gaps",
                    "Use 'if-then' proposals for conditional concessions",
                    "Bundle issues for package deals",
                    "Set deadlines to create urgency",
                ],
            }
        else:
            analysis = {
                "domain": "negotiation",
                "type": negotiation_type,
                "principles": [
                    "Know your BATNA (Best Alternative to Negotiated Agreement)",
                    "Know the other side's BATNA — your source of power",
                    "Separate people from the problem (Getting to Yes)",
                    "Focus on interests, not positions",
                    "Find win-win options for value creation",
                    "Use objective information as criteria",
                ],
                "tactics": [
                    "Anchor high (but reasonably)",
                    "Silence is power — let the other side fill gaps",
                    "Use 'if-then' proposals for conditional concessions",
                    "Bundle issues for package deals",
                    "Set deadlines to create urgency",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Prepare 3 scenarios: target, acceptable, walk-away" if not is_hebrew else "הכן 3 תרחישים: יעד, מקובל, נקודת יציאה",
                "Research the other party thoroughly before meeting" if not is_hebrew else "חקר את הצד השני ביסודיות לפני הפגישה",
                "Always be willing to walk away" if not is_hebrew else "תמיד היה מוכן ללכת",
            ],
            metadata={"negotiation_type": negotiation_type, "domain": "negotiation"},
        )

    def growth_plan(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Create a growth strategy plan."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        company_stage = (context or {}).get("company_stage", "growth")
        target_market = (context or {}).get("target_market", "global")

        if is_hebrew:
            analysis = {
                "domain": "growth_strategy",
                "company_stage": company_stage,
                "target_market": target_market,
                "growth_levers": [
                    "חדשנות מוצר — תכונות חדשות, מוצרים משלימים",
                    "שווקים חדשים — גיאוגרפיה, סגמנטים, שימושים חדשים",
                    "שיפור retention — חוויית לקוח, תמיכה, community",
                    "אופטימיזציית המרות — A/B testing, funnels, pricing",
                    "שותפויות אסטרטגיות — channels, co-marketing, OEM",
                    "רכישות — M&A לצמיחה אנכית או אופקית",
                ],
                "framework": "Ansoff Matrix + Pirate Metrics (AARRR)",
            }
        else:
            analysis = {
                "domain": "growth_strategy",
                "company_stage": company_stage,
                "target_market": target_market,
                "growth_levers": [
                    "Product Innovation — new features, complementary products",
                    "New Markets — geography, segments, new use cases",
                    "Retention Improvement — customer experience, support, community",
                    "Conversion Optimization — A/B testing, funnels, pricing",
                    "Strategic Partnerships — channels, co-marketing, OEM",
                    "Acquisitions — M&A for vertical or horizontal growth",
                ],
                "framework": "Ansoff Matrix + Pirate Metrics (AARRR)",
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Focus on retention before acquisition" if not is_hebrew else "התמקד ב-retention לפני acquisition",
                "Test growth channels with small budget first" if not is_hebrew else "בדוק ערוצי צמיחה עם תקציב קטן קודם",
                "Measure CAC and LTV for each channel separately" if not is_hebrew else "מדוד CAC ו-LTV לכל ערוץ בנפרד",
            ],
            metadata={"company_stage": company_stage, "domain": "growth_strategy"},
        )

    def _general_business_advice(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide general business advice."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        if is_hebrew:
            analysis = {
                "domain": "general_business",
                "assessment": (
                    "לאומת הנושא העסקי המוצג, יש לבצע ניתוח מעמיק "
                    "הכולל הערכת שוק, תחרות, והתאמה אסטרטגית. "
                    "מומלץ לגשת לנושא בשיטה מובנית — הגדרה, מחקר, "
                    "ניתוח, המלצות, וביצוע."
                ),
            }
        else:
            analysis = {
                "domain": "general_business",
                "assessment": (
                    "Regarding the presented business topic, an in-depth analysis is required "
                    "including market evaluation, competition, and strategic fit. "
                    "It is recommended to approach the topic systematically — "
                    "definition, research, analysis, recommendations, and execution."
                ),
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Define clear, measurable objectives" if not is_hebrew else "הגדר מטרות ברורות וניתנות למדידה",
                "Research thoroughly before committing resources" if not is_hebrew else "חקר ביסודיות לפני הקצאת משאבים",
                "Monitor KPIs and adjust strategy regularly" if not is_hebrew else "עקוב אחר KPIs והתאם אסטרטגיה באופן שוטף",
            ],
            metadata={"domain": "general_business"},
        )

    def get_disclaimer(self) -> str:
        """Business-specific disclaimer."""
        return (
            "המידע העסקי המסופק הוא לצורך הכוונה כללית בלבד ואינו מהווה ייעוץ "
            "פיננסי, משפטי, או השקעותי. יש להתייעץ עם מקצוענים מוסמכים לפני "
            "קבלת החלטות עסקיות או השקעתיות."
        )

    # ---- Internal helpers --------------------------------------------

    def _detect_business_domain(self, query: str) -> List[str]:
        """Detect business domain from query."""
        q = query.lower()
        domains = []
        domain_map = {
            "swot": ["swot", "strengths", "weaknesses", "opportunities", "threats"],
            "strategy": ["strategy", "strategic", "plan", "vision", "mission", "אסטרטגיה"],
            "financial": ["financial", "model", "revenue", "budget", "cash flow", "forecast", "כספים", "תקציב"],
            "market": ["market", "industry", "segment", "customer", "demand", "שוק", "תעשייה"],
            "pitch": ["pitch", "deck", "investor", "presentation", "funding", "fundraise", "presentation"],
            "negotiation": ["negotiate", "negotiation", "deal", "terms", "agreement", "contract business"],
            "growth": ["growth", "scale", "expand", "growth hacking", "צמיחה", "התרחבות"],
            "startup": ["startup", "founder", "venture", "seed", "series a", "סטארטאפ", "יזם"],
            "ma": ["merger", "acquisition", "m&a", "due diligence", "valuation", "מיזוג", "רכישה"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in q for kw in keywords):
                domains.append(domain)
        return domains if domains else ["general"]



# =============================================================================
#                     5. PROJECT MANAGER PERSONA
# =============================================================================

class ProjectManagerPersona(BaseExpertPersona):
    """
    Senior Project Manager with expertise across all PM methodologies.
    Specializes in Agile, Scrum, Kanban, Waterfall, SAFe, and hybrid approaches.
    Provides project planning, risk assessment, timeline estimation,
    resource allocation, and status reporting frameworks.
    """

    def __init__(
        self,
        name: str = "Rachel Goldstein",
        title: str = "Senior Project Manager",
        language_preference: str = "he",
        formality_level: str = "professional",
    ):
        super().__init__(
            name=name,
            title=title,
            expertise_domains=[
                "agile",
                "scrum",
                "kanban",
                "waterfall",
                "pmp",
                "safe",
                "less",
                "prince2",
                "risk_management",
                "resource_planning",
                "stakeholder_management",
                "budgeting",
                "earned_value_management",
                "critical_path_method",
                "schedule_compression",
                "change_management",
                "quality_management",
                "procurement_management",
                "communication_management",
                "portfolio_management",
            ],
            language_preference=language_preference,
            formality_level=formality_level,
        )
        self._methodology_guides: Dict[str, Dict[str, Any]] = {
            "scrum": {
                "roles": ["Product Owner", "Scrum Master", "Development Team"],
                "artifacts": ["Product Backlog", "Sprint Backlog", "Increment"],
                "events": ["Sprint Planning", "Daily Scrum", "Sprint Review", "Sprint Retrospective"],
                "sprint_duration": "1-4 weeks (2 weeks recommended)",
            },
            "kanban": {
                "principles": ["Visualize work", "Limit WIP", "Focus on flow", "Continuous improvement"],
                "wip_limits": "1-2 items per person per column",
                "metrics": ["Lead Time", "Cycle Time", "Throughput", "CFD"],
            },
            "waterfall": {
                "phases": ["Requirements", "Design", "Implementation", "Testing", "Deployment", "Maintenance"],
                "best_for": "Projects with clear, stable requirements and fixed scope",
                "governance": "Phase gates with formal sign-offs required",
            },
            "safe": {
                "levels": ["Team", "Program", "Large Solution", "Portfolio"],
                "pi_planning": "Quarterly, 2-day event with all teams",
                "best_for": "Large enterprises with 50+ developers",
            },
        }

    # ---- Core analysis ------------------------------------------------

    def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main PM analysis engine. Routes to specialized analysis
        based on detected project management domain.
        """
        is_hebrew = _detect_hebrew(query)
        domain = self._detect_pm_domain(query)

        if any(d in domain for d in ["plan", "create", "schedule", "timeline"]):
            return self.create_plan(query, context, is_hebrew)
        elif any(d in domain for d in ["risk", "assess", "mitigate"]):
            return self.risk_assessment(query, context, is_hebrew)
        elif any(d in domain for d in ["timeline", "estimate", "duration"]):
            return self.timeline_estimate(query, context, is_hebrew)
        elif any(d in domain for d in ["resource", "allocate", "team", "capacity"]):
            return self.resource_allocate(query, context, is_hebrew)
        elif any(d in domain for d in ["status", "report", "progress", "burn"]):
            return self.status_report(query, context, is_hebrew)
        elif any(d in domain for d in ["critical", "path", "cpm", "dependency"]):
            return self.critical_path(query, context, is_hebrew)
        else:
            return self._general_pm_advice(query, context, is_hebrew)

    def create_plan(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Create a comprehensive project plan."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        methodology = (context or {}).get("methodology", "scrum")
        team_size = (context or {}).get("team_size", 5)
        duration_weeks = (context or {}).get("duration_weeks", 12)

        guide = self._methodology_guides.get(methodology, self._methodology_guides["scrum"])

        if is_hebrew:
            analysis = {
                "domain": "project_planning",
                "methodology": methodology,
                "team_size": team_size,
                "duration": f"{duration_weeks} שבועות",
                "plan_structure": [
                    "1. הגדרת היקף (Scope) — מטרות, deliverables, מגבלות",
                    "2. פירוק מבנה עבודה (WBS) — חלוקה ל-packages של עבודה",
                    "3. רשימת פעילויות — זמני התחלה וסיום משוערים",
                    "4. תלויות — קשרים בין פעילויות (FS, SS, FF, SF)",
                    "5. הקצאת משאבים — צוות, תקציב, כלים",
                    "6. ניהול סיכונים — זיהוי, הערכה, תוכנית מיתון",
                    "7. תקשורת — תדירות דיווח, stakeholders, כלי תקשורת",
                    "8. בקרה — מדדי KPI, Review meetings, Change Control",
                ],
                "methodology_guide": guide,
                "success_criteria": [
                    "היקף מוגדר ברור",
                    "לו\"ז ריאלי עם buffer",
                    "צוות עם יכולות מתאימות",
                    " stakeholders מעורבים ומעודכנים",
                ],
            }
        else:
            analysis = {
                "domain": "project_planning",
                "methodology": methodology,
                "team_size": team_size,
                "duration": f"{duration_weeks} weeks",
                "plan_structure": [
                    "1. Scope Definition — objectives, deliverables, constraints",
                    "2. Work Breakdown Structure (WBS) — decomposition into work packages",
                    "3. Activity List — estimated start and end times",
                    "4. Dependencies — relationships between activities (FS, SS, FF, SF)",
                    "5. Resource Allocation — team, budget, tools",
                    "6. Risk Management — identification, assessment, mitigation plan",
                    "7. Communication — reporting frequency, stakeholders, communication tools",
                    "8. Control — KPI metrics, Review meetings, Change Control",
                ],
                "methodology_guide": guide,
                "success_criteria": [
                    "Clearly defined scope",
                    "Realistic schedule with buffer",
                    "Team with matching capabilities",
                    "Involved and updated stakeholders",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Define MVP scope first, expand iteratively" if not is_hebrew else "הגדר היקף MVP קודם, הרחב באופן איטרטיבי",
                "Add 20-30% buffer to initial estimates" if not is_hebrew else "הוסף 20-30% buffer להערכות התחלתיות",
                "Set weekly review cadence from day one" if not is_hebrew else "קבע קצב סקירה שבועי מיום אחד",
            ],
            metadata={"methodology": methodology, "domain": "project_planning"},
        )

    def risk_assessment(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive risk assessment."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        project_type = (context or {}).get("project_type", "software")
        risk_tolerance = (context or {}).get("risk_tolerance", "medium")

        if is_hebrew:
            analysis = {
                "domain": "risk_management",
                "project_type": project_type,
                "risk_tolerance": risk_tolerance,
                "assessment_framework": "ISO 31000 + PMI Risk Management",
                "risk_register_template": [
                    "מזהה סיכון — קוד ייחודי",
                    "תיאור — תיאור מפורט של הסיכון",
                    "קטגוריה — טכני, ארגוני, חיצוני, פרויקט",
                    "הסתברות — 1-5 (נמוך עד גבוה מאוד)",
                    "השפעה — 1-5 (נמוך עד גבוה מאוד)",
                    "ציון סיכון — הסתברות x השפעה",
                    "אסטרטגיית תגובה — הימנעות, מיתון, העברה, קבלה",
                    "פעולת מיתון — מה עושים אם הסיכון מתממש",
                    "אחראי — מי אחראי לניהול הסיכון",
                    "סטטוס — פעיל, סגור, מתרחש כעת",
                ],
                "common_risks": {
                    "טכניים": ["בעיות ארכיטקטורה", "חוסר במומחיות טכנית", "בעיות אינטגרציה"],
                    "ארגוניים": ["עזיבת עובדים מרכזיים", "שינויי יעדים עסקיים", "הקצאת משאבים לא מספקת"],
                    "חיצוניים": ["שינויי רגולציה", "תלות בספקים חיצוניים", "תנאי שוק משתנים"],
                    "פרויקט": ["היקסן לא מוגדר היטב", "הערכות זמן לא ריאליות", "תקשורת לקויה"],
                },
            }
        else:
            analysis = {
                "domain": "risk_management",
                "project_type": project_type,
                "risk_tolerance": risk_tolerance,
                "assessment_framework": "ISO 31000 + PMI Risk Management",
                "risk_register_template": [
                    "Risk ID — unique code",
                    "Description — detailed risk description",
                    "Category — Technical, Organizational, External, Project",
                    "Probability — 1-5 (Very Low to Very High)",
                    "Impact — 1-5 (Very Low to Very High)",
                    "Risk Score — Probability x Impact",
                    "Response Strategy — Avoid, Mitigate, Transfer, Accept",
                    "Mitigation Action — what to do if risk materializes",
                    "Owner — person responsible for managing the risk",
                    "Status — Active, Closed, Occurring",
                ],
                "common_risks": {
                    "Technical": ["Architecture issues", "Lack of technical expertise", "Integration problems"],
                    "Organizational": ["Key employee departure", "Changing business goals", "Insufficient resource allocation"],
                    "External": ["Regulatory changes", "Dependency on external vendors", "Changing market conditions"],
                    "Project": ["Poorly defined scope", "Unrealistic time estimates", "Poor communication"],
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Create risk register in first week of project" if not is_hebrew else "צור רישום סיכונים בשבוע הראשון של הפרויקט",
                "Review top 5 risks in every weekly meeting" if not is_hebrew else "סקור את 5 הסיכונים המובילים בכל פגישה שבועית",
                "Assign explicit risk owners for each high-impact risk" if not is_hebrew else "מנה אחראים מפורשים לכל סיכון בעל השפעה גבוהה",
            ],
            metadata={"project_type": project_type, "domain": "risk_management"},
        )

    def timeline_estimate(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide timeline estimation using multiple techniques."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        scope_description = (context or {}).get("scope", query)
        team_velocity = (context or {}).get("team_velocity", "unknown")

        if is_hebrew:
            analysis = {
                "domain": "timeline_estimation",
                "estimation_techniques": [
                    "משיכת מומחה (Expert Judgment) — הערכת מומחים בתחום",
                    "אנלוגיה (Analogous) — השוואה לפרויקטים דומים שבוצעו",
                    "פרמטרי (Parametric) — נוסחה מבוססת פרמטרים (למשל: שורות קוד / קצב)",
                    "3-Point Estimate — אופטימי, פסימי, סביר (PERT): (O + 4M + P) / 6",
                    "Planning Poker — הערכה קבוצתית באמצעות Story Points",
                    "Monte Carlo Simulation — סימולציה סטטיסטית לחיזוק הערכה",
                ],
                "buffer_strategy": "השתמש ב-Feature Buffer (50% contingency) או Schedule Buffer (Critical Chain)",
                "common_pitfalls": [
                    "אופטימיות יתר (Planning Fallacy)",
                    "התעלמות מתלויות בין משימות",
                    "חוסר הערכת זמן לבדיקות ותיקוני באגים",
                    "התעלמות מזמן onboarding לצוותים חדשים",
                ],
            }
        else:
            analysis = {
                "domain": "timeline_estimation",
                "estimation_techniques": [
                    "Expert Judgment — domain expert estimation",
                    "Analogous — comparison to similar completed projects",
                    "Parametric — formula-based (e.g., lines of code / rate)",
                    "3-Point Estimate — optimistic, pessimistic, most likely (PERT): (O + 4M + P) / 6",
                    "Planning Poker — group estimation using Story Points",
                    "Monte Carlo Simulation — statistical simulation to validate estimates",
                ],
                "buffer_strategy": "Use Feature Buffer (50% contingency) or Schedule Buffer (Critical Chain)",
                "common_pitfalls": [
                    "Over-optimism (Planning Fallacy)",
                    "Ignoring task dependencies",
                    "Underestimating testing and bug fix time",
                    "Ignoring onboarding time for new teams",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Use 3-point estimation for critical path items" if not is_hebrew else "השתמש בהערכת 3 נקודות עבור פריטי נתיב קריטי",
                "Always add 20-30% buffer to expert estimates" if not is_hebrew else "תמיד הוסף 20-30% buffer להערכות מומחים",
                "Re-estimate at end of each sprint/phase" if not is_hebrew else "הערך מחדש בסוף כל ספרינט/שלב",
            ],
            metadata={"domain": "timeline_estimation"},
        )

    def resource_allocate(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide resource allocation framework."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        team_size = (context or {}).get("team_size", 5)
        budget = (context or {}).get("budget", "unspecified")

        if is_hebrew:
            analysis = {
                "domain": "resource_allocation",
                "team_size": team_size,
                "budget": budget,
                "allocation_framework": [
                    "זיהוי משאבים נדרשים — אנושיים, טכניים, כספיים",
                    "הערכת זמינות — FTE, חלקיות, חופשות, מחלה מתוכננת",
                    "תאום לדרישות הפרויקט — כישורים, רמת ניסיון, הכשרות",
                    "יצירת Resource Histogram — שימוש במשאבים לאורך זמן",
                    "ניהול מחסור — Resource Leveling או Smoothing",
                    "בקרה שוטפת — מעקב אחר utilization ו-overallocation",
                ],
                "resource_matrix": {
                    "תפקיד": ["מפתח", "מעצב", "בודק QA", "מנהל מוצר", "DevOps"],
                    "הקצאה": ["60-80%", "40-60%", "30-50%", "50-70%", "20-40%"],
                    "זמן_מוערך": ["לפי story points", "לפי מסכים", "לפי test cases", "לפי features", "לפי סביבות"],
                },
            }
        else:
            analysis = {
                "domain": "resource_allocation",
                "team_size": team_size,
                "budget": budget,
                "allocation_framework": [
                    "Identify required resources — human, technical, financial",
                    "Assess availability — FTE, part-time, vacations, planned leave",
                    "Match to project requirements — skills, experience, certifications",
                    "Create Resource Histogram — resource usage over time",
                    "Manage shortages — Resource Leveling or Smoothing",
                    "Ongoing control — track utilization and overallocation",
                ],
                "resource_matrix": {
                    "role": ["Developer", "Designer", "QA Tester", "Product Manager", "DevOps"],
                    "allocation": ["60-80%", "40-60%", "30-50%", "50-70%", "20-40%"],
                    "estimated_time": ["per story points", "per screens", "per test cases", "per features", "per environments"],
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Track resource utilization weekly (target 70-80%)" if not is_hebrew else "עקוב אחר ניצול משאבים שבועית (יעד 70-80%)",
                "Plan for 15-20% buffer for sick leave and vacations" if not is_hebrew else "תכנן 15-20% buffer לחופשות ומחלה",
                "Cross-train team members for critical roles" if not is_hebrew else "אמן חברי צוות בצורת צלב לתפקידים קריטיים",
            ],
            metadata={"domain": "resource_allocation"},
        )

    def status_report(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Create a status report template and guidance."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        report_type = (context or {}).get("report_type", "weekly")

        if is_hebrew:
            analysis = {
                "domain": "status_reporting",
                "report_type": report_type,
                "report_structure": [
                    "1. סיכום מנהלים — 3-4 שורות על מצב הפרויקט",
                    "2. מצב נוכחי — 🟢 בזמן / 🟡 סטייה קלה / 🔴 סטייה משמעותית",
                    "3. הישגים השבוע — מה הושלם",
                    "4. יעדים לשבוע הבא — מה מתוכנן",
                    "5. סיכונים ובעיות — מה דורש תשומת לב",
                    "6. החלטות נדרשות — מה צריך שיוחלט",
                    "7. מדדים מרכזיים — burndown, velocity, budget burn",
                    "8. stakeholder updates — עדכונים ספציפיים לכל stakeholder",
                ],
                "raci_for_reporting": {
                    "כתיבת דוח": "Project Manager",
                    "בחינת נתונים": "Team Leads",
                    "אישור": "Project Sponsor / Product Owner",
                    "הפצה": "Project Manager + Communication Lead",
                },
                "kpi_dashboard": [
                    "Schedule Variance (SV) — עלות לו\"ז",
                    "Cost Variance (CV) — עלות תקציב",
                    "SPI — מדד ביצוע לו\"ז",
                    "CPI — מדד ביצוע עלות",
                    "Defect Rate — אחות באגים",
                    "Team Velocity — velocity צוות",
                ],
            }
        else:
            analysis = {
                "domain": "status_reporting",
                "report_type": report_type,
                "report_structure": [
                    "1. Executive Summary — 3-4 lines on project status",
                    "2. Current State — 🟢 On Track / 🟡 Minor Variance / 🔴 Significant Variance",
                    "3. This Week's Achievements — what was completed",
                    "4. Next Week's Goals — what is planned",
                    "5. Risks and Issues — what requires attention",
                    "6. Decisions Required — what needs to be decided",
                    "7. Key Metrics — burndown, velocity, budget burn",
                    "8. Stakeholder Updates — specific updates per stakeholder",
                ],
                "raci_for_reporting": {
                    "Report Writing": "Project Manager",
                    "Data Review": "Team Leads",
                    "Approval": "Project Sponsor / Product Owner",
                    "Distribution": "Project Manager + Communication Lead",
                },
                "kpi_dashboard": [
                    "Schedule Variance (SV)",
                    "Cost Variance (CV)",
                    "SPI — Schedule Performance Index",
                    "CPI — Cost Performance Index",
                    "Defect Rate",
                    "Team Velocity",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Automate data collection where possible (JIRA, GitHub, CI/CD)" if not is_hebrew else "אוטומט איסוף נתונים אם אפשר (JIRA, GitHub, CI/CD)",
                "Keep status reports under 1 page for busy executives" if not is_hebrew else "שמור על דוחות סטטוס בעמוד אחד עבור מנהלים עמוסים",
                "Use visual indicators (RAG status) for quick scanning" if not is_hebrew else "השתמש באינדיקטורים ויזואליים (RAG status) לסריקה מהירה",
            ],
            metadata={"report_type": report_type, "domain": "status_reporting"},
        )

    def critical_path(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Analyze and provide critical path method guidance."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        project_activities = (context or {}).get("activities", [])

        if is_hebrew:
            analysis = {
                "domain": "critical_path_method",
                "method": "CPM (Critical Path Method)",
                "steps": [
                    "1. רשום את כל הפעילויות (Activity List)",
                    "2. הגדר תלויות בין פעילויות (PDM — Precedence Diagram)",
                    "3. הערך משך לכל פעילות (Duration Estimation)",
                    "4. חשב Forward Pass — Early Start (ES) ו-Early Finish (EF)",
                    "5. חשב Backward Pass — Late Start (LS) ו-Late Finish (LF)",
                    "6. חשב Float (Slack) לכל פעילות — LS-ES או LF-EF",
                    "7. זהה את הנתיב הקריטי — פעילויות עם Float = 0",
                ],
                "key_concepts": {
                    "נתיב קריטי": "הנתיב הארוך ביותר בפרויקט — קובע את משך הפרויקט המינימלי",
                    "Float": "גמישות הזמן של פעילות מבלי לדחות את הפרויקט",
                    "Crash": "קיצור משך פעילויות על הנתיב הקריטי (בעלות נוספת)",
                    "Fast Track": "ביצוע פעילויות במקביל במקום ברצף (סיכון גבוה יותר)",
                },
            }
        else:
            analysis = {
                "domain": "critical_path_method",
                "method": "CPM (Critical Path Method)",
                "steps": [
                    "1. List all activities (Activity List)",
                    "2. Define dependencies between activities (PDM — Precedence Diagram)",
                    "3. Estimate duration for each activity (Duration Estimation)",
                    "4. Calculate Forward Pass — Early Start (ES) and Early Finish (EF)",
                    "5. Calculate Backward Pass — Late Start (LS) and Late Finish (LF)",
                    "6. Calculate Float (Slack) for each activity — LS-ES or LF-EF",
                    "7. Identify the Critical Path — activities with Float = 0",
                ],
                "key_concepts": {
                    "Critical Path": "The longest path in the project — determines minimum project duration",
                    "Float": "Time flexibility of an activity without delaying the project",
                    "Crashing": "Shortening activity durations on the critical path (at additional cost)",
                    "Fast Tracking": "Performing activities in parallel instead of sequentially (higher risk)",
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Update critical path analysis weekly" if not is_hebrew else "עדכן ניתוח נתיב קריטי שבועית",
                "Focus monitoring on critical path activities" if not is_hebrew else "התמקד במעקב אחר פעילויות נתיב קריטי",
                "Identify near-critical paths (float < 5 days) as secondary focus" if not is_hebrew else "זהה נתיבים קרובים-לקריטיים (float < 5 ימים) כמוקד משני",
            ],
            metadata={"domain": "critical_path"},
        )

    def _general_pm_advice(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide general project management advice."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        if is_hebrew:
            analysis = {
                "domain": "general_pm",
                "assessment": (
                    "ניהול פרויקטים מצליח דורש שילוב של מתודולוגיה מתאימה, "
                    "תקשורת אפקטיבית, וניהול סיכונים pro-active. "
                    "יש להתאים את הגישה לסוג הפרויקט, גודל הצוות, "
                    "ומורכבות ה-stakeholders."
                ),
                "key_principles": [
                    "Clarity — היקף, יעדים, ותפקידים ברורים לכולם",
                    "Communication — תקשורת תכופה ושקופה",
                    "Control — מעקב ובקרה שוטפת על התקדמות",
                    "Change — ניהול שינויים במבנה מוגדר",
                    "Closure — סיום מובנה עם לקחים",
                ],
            }
        else:
            analysis = {
                "domain": "general_pm",
                "assessment": (
                    "Successful project management requires a combination of appropriate methodology, "
                    "effective communication, and proactive risk management. "
                    "The approach must be tailored to the project type, team size, "
                    "and stakeholder complexity."
                ),
                "key_principles": [
                    "Clarity — clear scope, objectives, and roles for everyone",
                    "Communication — frequent and transparent communication",
                    "Control — ongoing tracking and monitoring of progress",
                    "Change — structured change management",
                    "Closure — structured closure with lessons learned",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            metadata={"domain": "general_pm"},
        )

    def get_disclaimer(self) -> str:
        """PM-specific disclaimer."""
        return (
            "המידע בנושא ניהול פרויקטים מסופק כקווים מנחים מקצועיים. "
            "יש להתאים את הכלים והשיטות לצרכים הספציפיים של כל פרויקט, "
            "ולשקול גורמים ארגוניים, תרבותיים, וטכניים לפני יישום."
        )

    # ---- Internal helpers --------------------------------------------

    def _detect_pm_domain(self, query: str) -> List[str]:
        """Detect PM domain from query."""
        q = query.lower()
        domains = []
        domain_map = {
            "plan": ["plan", "schedule", "roadmap", "wbs", "תכנון", "לו\"ז"],
            "risk": ["risk", "mitigate", "contingency", "סיכון", "מיתון"],
            "timeline": ["estimate", "duration", "how long", "how many weeks", "הערכת זמן"],
            "resource": ["resource", "allocate", "team capacity", "workload", "משאבים", "צוות"],
            "status": ["status", "report", "progress", "burn", "dashboard", "סטטוס", "דוח"],
            "critical": ["critical path", "cpm", "dependency", "slack", "float", "נתיב קריטי"],
            "agile": ["agile", "scrum", "sprint", "backlog", "retro", "אג'ייל", "סקרום"],
            "budget": ["budget", "cost", "evm", "earned value", "תקציב", "עלות"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in q for kw in keywords):
                domains.append(domain)
        return domains if domains else ["general"]



# =============================================================================
#                     6. CREATIVE DIRECTOR PERSONA
# =============================================================================

class CreativeDirectorPersona(BaseExpertPersona):
    """
    Creative Director with expertise across all creative domains.
    Specializes in graphic design, UX/UI, branding, copywriting,
    video production, motion graphics, and content strategy.
    Provides design concepts, brand strategy, creative briefs,
    content calendars, and professional critique.
    """

    def __init__(
        self,
        name: str = "Noa Ben-Artzi",
        title: str = "Creative Director",
        language_preference: str = "he",
        formality_level: str = "casual",
    ):
        super().__init__(
            name=name,
            title=title,
            expertise_domains=[
                "graphic_design",
                "ux_design",
                "ui_design",
                "copywriting",
                "branding",
                "brand_strategy",
                "visual_identity",
                "art_direction",
                "video_production",
                "motion_graphics",
                "animation",
                "photography",
                "illustration",
                "content_strategy",
                "social_media_content",
                "advertising",
                "campaign_design",
                "packaging_design",
                "editorial_design",
                "web_design",
            ],
            language_preference=language_preference,
            formality_level=formality_level,
        )
        self._design_principles: Dict[str, List[str]] = {
            "visual_hierarchy": [
                "Size — larger elements draw more attention",
                "Color — contrast guides the eye",
                "Position — top-left (RTL: top-right) gets attention first",
                "Whitespace — negative space defines importance",
                "Typography — font weight and style create order",
            ],
            "color_theory": [
                "Complementary — opposite on color wheel (high contrast)",
                "Analogous — adjacent on color wheel (harmonious)",
                "Triadic — evenly spaced on wheel (vibrant)",
                "Monochromatic — single hue variations (elegant)",
                "60-30-10 rule — dominant, secondary, accent",
            ],
            "typography": [
                "Maximum 2-3 fonts per design",
                "Ensure readability at all sizes",
                "Match font personality to brand tone",
                "Use proper line height (1.5x font size for body)",
                "Maintain consistent hierarchy levels",
            ],
        }
        self._israeli_design_context: Dict[str, str] = {
            "rtl_design": "Hebrew requires right-to-left (RTL) layout adaptation",
            "fonts": "Recommended Hebrew fonts: Heebo, Rubik, Assistant, Open Sans Hebrew",
            "cultural_sensitivity": "Consider Jewish, Muslim, Christian, and secular audiences",
            "local_agencies": "Leo Burnett Israel, BBR Saatchi & Saatchi, McCann Tel Aviv",
        }

    # ---- Core analysis ------------------------------------------------

    def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main creative analysis engine. Routes to specialized analysis
        based on detected creative domain.
        """
        is_hebrew = _detect_hebrew(query)
        domain = self._detect_creative_domain(query)

        if any(d in domain for d in ["design", "concept", "visual"]):
            return self.design_concept(query, context, is_hebrew)
        elif any(d in domain for d in ["brand", "identity", "positioning"]):
            return self.brand_strategy(query, context, is_hebrew)
        elif any(d in domain for d in ["brief", "creative_brief"]):
            return self.creative_brief(query, context, is_hebrew)
        elif any(d in domain for d in ["content", "calendar", "social"]):
            return self.content_calendar(query, context, is_hebrew)
        elif any(d in domain for d in ["direction", "art_direction"]):
            return self.visual_direction(query, context, is_hebrew)
        elif any(d in domain for d in ["critique", "review", "feedback"]):
            return self.critique_work(query, context, is_hebrew)
        else:
            return self._general_creative_advice(query, context, is_hebrew)

    def design_concept(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Develop a design concept."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        project_type = (context or {}).get("project_type", "general")
        target_audience = (context or {}).get("target_audience", "general")
        mood = (context or {}).get("mood", "professional")

        if is_hebrew:
            analysis = {
                "domain": "design_concept",
                "project_type": project_type,
                "target_audience": target_audience,
                "mood": mood,
                "concept_development": [
                    "1. מחקר — הבן את הקהל, המתחרים, והטרנדים",
                    "2. מציאת רעיונות — mood board, sketching, brainstorming",
                    "3. מיצוב חזותי — בחירת סגנון, צבעים, טיפוגרפיה",
                    "4. יצירת וריאציות — 2-3 כיוונים עיצוביים שונים",
                    "5. בחירה והתפתחות — פיתוח הכיוון הנבחר",
                    "6. בקרת איכות — ודא עמידה בדרישות ובמותג",
                ],
                "design_principles": self._design_principles,
                "rtl_considerations": self._israeli_design_context if is_hebrew else {},
            }
        else:
            analysis = {
                "domain": "design_concept",
                "project_type": project_type,
                "target_audience": target_audience,
                "mood": mood,
                "concept_development": [
                    "1. Research — understand audience, competitors, and trends",
                    "2. Ideation — mood board, sketching, brainstorming",
                    "3. Visual Direction — choose style, colors, typography",
                    "4. Create Variations — 2-3 different design directions",
                    "5. Selection and Development — develop chosen direction",
                    "6. Quality Control — ensure compliance with requirements and brand",
                ],
                "design_principles": self._design_principles,
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Create 3 mood boards before starting design" if not is_hebrew else "צור 3 mood boards לפני תחילת העיצוב",
                "Test design with 5 potential users" if not is_hebrew else "בדוק את העיצוב עם 5 משתמשים פוטנציאליים",
                "Ensure accessibility compliance (WCAG 2.1 AA)" if not is_hebrew else "ודא עמידה בנגישות (WCAG 2.1 AA)",
            ],
            metadata={"project_type": project_type, "domain": "design_concept"},
        )

    def brand_strategy(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Develop brand strategy."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        company_stage = (context or {}).get("company_stage", "startup")
        industry = (context or {}).get("industry", "technology")

        if is_hebrew:
            analysis = {
                "domain": "brand_strategy",
                "company_stage": company_stage,
                "industry": industry,
                "brand_framework": [
                    "1. מחקר מותג — סקר שוק, ניתוח מתחרים, ראיונות לקוחות",
                    "2. מיצוב — איך המותג שונה וטוב יותר",
                    "3. מסר מרכזי — Value Proposition ברור וקונציזי",
                    "4. אישיות מותג — תכונות, קול, טון",
                    "5. זהות חזותית — לוגו, צבעים, טיפוגרפיה, Imagery",
                    "6. קווי מנחה — Brand Guidelines מקיפים",
                    "7. הפעלה — יישום בכל נקודות המגע",
                    "8. ניטור — מדידת חוזק מותג ונראות",
                ],
                "brand_elements": {
                    "שם המותג": "קל להגייה, קל לזכור, בעל משמעות",
                    "סיסמא (Tagline)": "עד 7 מילים המסכמות את הערך",
                    "Story": "סיפור מותג המחבר רגשית עם הקהל",
                    "Values": "3-5 ערכים ליבה המנחים את ההתנהגות",
                },
            }
        else:
            analysis = {
                "domain": "brand_strategy",
                "company_stage": company_stage,
                "industry": industry,
                "brand_framework": [
                    "1. Brand Research — market survey, competitor analysis, customer interviews",
                    "2. Positioning — how the brand is different and better",
                    "3. Core Message — clear and concise Value Proposition",
                    "4. Brand Personality — traits, voice, tone",
                    "5. Visual Identity — logo, colors, typography, imagery",
                    "6. Guidelines — comprehensive Brand Guidelines",
                    "7. Activation — implementation across all touchpoints",
                    "8. Monitoring — measuring brand strength and visibility",
                ],
                "brand_elements": {
                    "Brand Name": "Easy to pronounce, memorable, meaningful",
                    "Tagline": "Up to 7 words summarizing the value",
                    "Story": "Brand story that emotionally connects with audience",
                    "Values": "3-5 core values guiding behavior",
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Define brand voice and tone before visual design" if not is_hebrew else "הגדר קול וטון מותג לפני עיצוב חזותי",
                "Create brand book (50+ pages) for consistency" if not is_hebrew else "צור ספר מותג (50+ עמודים) לעקביות",
                "Test brand perception with target audience" if not is_hebrew else "בדוק תפיסת מותג עם קהל היעד",
            ],
            metadata={"company_stage": company_stage, "domain": "brand_strategy"},
        )

    def creative_brief(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Create a creative brief."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        project_name = (context or {}).get("project_name", "Untitled Project")

        if is_hebrew:
            analysis = {
                "domain": "creative_brief",
                "project_name": project_name,
                "brief_template": {
                    "רקע": "תיאור הפרויקט, המוצר, וההקשר העסקי",
                    "מטרות": "מה רוצים להשיג — מדיד וברור (SMART)",
                    "קהל יעד": "פרופיל דמוגרפי ופסיכוגרפי מפורט",
                    "מסר מרכזי": "הנקודה המרכזית שצריכה להתקבל",
                    "טון וקול": "איך המותג מדבר — רשמי, ידידותי, מקצועי, משחקי",
                    " deliverables": "רשימת התוצרים הדרושים בפורמט ובגודל המתאים",
                    "לוח זמנים": "תאריכי יעד לכל שלב — הגשה, בחינה, אישור",
                    "תקציב": "טווח תקציבי זמין לפרויקט",
                    "מגבלות": "מה לא לעשות — מה שלא מתאים למותג",
                    "השראה": "דוגמאות, mood boards, references",
                    "קריטריוני הצלחה": "איך נדע שהפרויקט הצליח",
                },
            }
        else:
            analysis = {
                "domain": "creative_brief",
                "project_name": project_name,
                "brief_template": {
                    "Background": "Project, product, and business context description",
                    "Objectives": "What we want to achieve — measurable and clear (SMART)",
                    "Target Audience": "Detailed demographic and psychographic profile",
                    "Key Message": "The central point that needs to be received",
                    "Tone and Voice": "How the brand speaks — formal, friendly, professional, playful",
                    "Deliverables": "Required deliverables list in appropriate format and size",
                    "Timeline": "Target dates for each stage — submission, review, approval",
                    "Budget": "Available budget range for the project",
                    "Constraints": "What not to do — what doesn't fit the brand",
                    "Inspiration": "Examples, mood boards, references",
                    "Success Criteria": "How we'll know the project succeeded",
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Get stakeholder sign-off on brief before starting creative work" if not is_hebrew else "קבל אישור stakeholders על ה-brief לפני תחילת עבודה יצירתית",
                "Include 3 competitor references for context" if not is_hebrew else "כלול 3 references של מתחרים להקשר",
                "Define 1 primary objective (not 5)" if not is_hebrew else "הגדר מטרה ראשית אחת (לא 5)",
            ],
            metadata={"project_name": project_name, "domain": "creative_brief"},
        )

    def content_calendar(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Create a content calendar framework."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        channels = (context or {}).get("channels", ["social_media"])
        frequency = (context or {}).get("frequency", "weekly")

        if is_hebrew:
            analysis = {
                "domain": "content_calendar",
                "channels": channels,
                "frequency": frequency,
                "calendar_framework": [
                    "1. יעדים — הגדר מטרות לכל ערוץ (מודעות, מעורבות, המרות)",
                    "2. קהל — התאם תוכן לפרופיל הקהל בכל פלטפורמה",
                    "3. פילוסטרים — הגדר 3-5 נושאים מרכזיים (content pillars)",
                    "4. סוגי תוכן — חינוכי, שעשועי, השראתי, קידום מכירות",
                    "5. תדירות — לוח זמנים עקבי לכל ערוץ",
                    "6. יצירה — תהליך יצירת תוכן (ideation → creation → review)",
                    "7. פרסום — לוח זמנים אופטימלי לכל פלטפורמה",
                    "8. ניתוח — מדד ביצועים והתאמה לפי נתונים",
                ],
                "optimal_posting_times": {
                    "LinkedIn": "ראשון-חמישי 8:00-10:00, 12:00-14:00",
                    "Instagram": "ראשון-רביעי 11:00-13:00, 19:00-21:00",
                    "Facebook": "ראשון-רביעי 13:00-15:00",
                    "Twitter/X": "ראשון-חמישי 9:00-11:00",
                    "TikTok": "ראשון-רביעי 19:00-22:00",
                },
                "content_mix": {
                    "חינוכי (80%)": "טיפים, הדרכות, תובנות תעשייה",
                    "שעשועי (10%)": "מימים, תוכן קליל, אחורי הקלעים",
                    "קידום מכירות (10%)": "הצעות, הנחות, קריאות לפעולה",
                },
            }
        else:
            analysis = {
                "domain": "content_calendar",
                "channels": channels,
                "frequency": frequency,
                "calendar_framework": [
                    "1. Goals — define objectives per channel (awareness, engagement, conversions)",
                    "2. Audience — tailor content to audience profile on each platform",
                    "3. Pillars — define 3-5 core themes (content pillars)",
                    "4. Content Types — educational, entertaining, inspirational, promotional",
                    "5. Frequency — consistent schedule per channel",
                    "6. Creation — content creation process (ideation → creation → review)",
                    "7. Publishing — optimal timing per platform",
                    "8. Analysis — performance metrics and data-driven adjustment",
                ],
                "optimal_posting_times": {
                    "LinkedIn": "Sun-Thu 8:00-10:00, 12:00-14:00",
                    "Instagram": "Sun-Wed 11:00-13:00, 19:00-21:00",
                    "Facebook": "Sun-Wed 13:00-15:00",
                    "Twitter/X": "Sun-Thu 9:00-11:00",
                    "TikTok": "Sun-Wed 19:00-22:00",
                },
                "content_mix": {
                    "Educational (80%)": "Tips, tutorials, industry insights",
                    "Entertaining (10%)": "Memes, light content, behind the scenes",
                    "Promotional (10%)": "Offers, discounts, calls to action",
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Plan content 2-4 weeks ahead" if not is_hebrew else "תכנן תוכן 2-4 שבועות מראש",
                "Repurpose content across channels (adapt format)" if not is_hebrew else "מיחזר תוכן בין ערוצים (התאם פורמט)",
                "Analyze top-performing posts monthly and iterate" if not is_hebrew else "נתח פוסטים מובילים חודשית וחזור עליהם",
            ],
            metadata={"channels": channels, "domain": "content_calendar"},
        )

    def visual_direction(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide visual direction and art direction."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        visual_style = (context or {}).get("visual_style", "modern")

        if is_hebrew:
            analysis = {
                "domain": "visual_direction",
                "style": visual_style,
                "direction_elements": [
                    "פלטת צבעים — ראשי, משני, הדגשה, רקע",
                    "טיפוגרפיה — פונטים, גדלים, משקלים, היררכיה",
                    "Imagery — סגנון צילום, אילוסטרציה, אייקונים",
                    "פריסה — רשת, שוליים, רווחים, יחסי גודל",
                    "אנימציה — סגנון תנועה, משך, easing functions",
                    "רכיבי UI — כפתורים, טפסים, כרטיסים, ניווט",
                ],
                "style_directions": {
                    "modern": "Minimal, clean lines, generous whitespace, sans-serif fonts",
                    "classic": "Elegant, serif fonts, rich textures, warm palette",
                    "playful": "Bold colors, rounded shapes, hand-drawn elements",
                    "futuristic": "Neon accents, dark themes, geometric shapes, gradients",
                    "organic": "Natural colors, flowing shapes, hand-crafted feel",
                },
                "rtl_guidelines": [
                    "הזז את הניווט הראשי לימין",
                    "הפוך את כיוון האייקונים של חצים ומצביעים",
                    "התאם את יישור הטקסט: ימין לעברית, שמאל לאנגלית",
                    "בדוק את סדר הופעת האלמנטים בכל מסך",
                ] if is_hebrew else [],
            }
        else:
            analysis = {
                "domain": "visual_direction",
                "style": visual_style,
                "direction_elements": [
                    "Color Palette — primary, secondary, accent, background",
                    "Typography — fonts, sizes, weights, hierarchy",
                    "Imagery — photography style, illustration, icons",
                    "Layout — grid, margins, spacing, size relationships",
                    "Animation — motion style, duration, easing functions",
                    "UI Components — buttons, forms, cards, navigation",
                ],
                "style_directions": {
                    "modern": "Minimal, clean lines, generous whitespace, sans-serif fonts",
                    "classic": "Elegant, serif fonts, rich textures, warm palette",
                    "playful": "Bold colors, rounded shapes, hand-drawn elements",
                    "futuristic": "Neon accents, dark themes, geometric shapes, gradients",
                    "organic": "Natural colors, flowing shapes, hand-crafted feel",
                },
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Create a component library for consistency" if not is_hebrew else "צור ספריית רכיבים לעקביות",
                "Document all design decisions with rationale" if not is_hebrew else "תעד את כל החלטות העיצוב עם נימוק",
                "Test visual design with actual content (not lorem ipsum)" if not is_hebrew else "בדוק עיצוב חזותי עם תוכן אמיתי (לא lorem ipsum)",
            ],
            metadata={"visual_style": visual_style, "domain": "visual_direction"},
        )

    def critique_work(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide professional critique of creative work."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        work_type = (context or {}).get("work_type", "general")

        if is_hebrew:
            analysis = {
                "domain": "creative_critique",
                "work_type": work_type,
                "critique_framework": "Critique Sandwich — Strengths → Improvements → Strengths",
                "evaluation_dimensions": [
                    "עמידה במטרה — האם התוצר עונה על Brief?",
                    "אסתטיקה — האם זה נראה טוב ומקצועי?",
                    "קריאות — האם המסר ברור ומובן?",
                    "עקביות — האם יש זהות מותגית אחידה?",
                    "חדשנות — האם יש רעיון מקורי או תובנה?",
                    "טכנית — האם הביצוע טכני מושלם?",
                    "רגש — האם יש חיבור רגשי עם הקהל?",
                ],
                "critique_guidelines": [
                    "התמקד בתוצר, לא ביוצר",
                    "הסבר למה — לא רק מה לא עובד",
                    "הצע אלטרנטיבות ספציפיות",
                    "התחל בחיובי, סיים בחיובי",
                    "שאל שאלות במקום לתת הוראות",
                ],
            }
        else:
            analysis = {
                "domain": "creative_critique",
                "work_type": work_type,
                "critique_framework": "Critique Sandwich — Strengths → Improvements → Strengths",
                "evaluation_dimensions": [
                    "Goal Alignment — does the deliverable answer the brief?",
                    "Aesthetics — does it look good and professional?",
                    "Clarity — is the message clear and understandable?",
                    "Consistency — is there a unified brand identity?",
                    "Innovation — is there an original idea or insight?",
                    "Technical — is the technical execution flawless?",
                    "Emotion — is there an emotional connection with the audience?",
                ],
                "critique_guidelines": [
                    "Focus on the work, not the creator",
                    "Explain why — not just what doesn't work",
                    "Offer specific alternatives",
                    "Start positive, end positive",
                    "Ask questions instead of giving orders",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            recommendations=[
                "Always reference the original brief when critiquing" if not is_hebrew else "תמיד התייחס ל-brief המקורי בביקורת",
                "Use the 'What-Why-How' format for feedback" if not is_hebrew else "השתמש בפורמט 'מה-למה-איך' למשוב",
                "Prioritize feedback — flag must-fix vs. nice-to-have" if not is_hebrew else "עדיף משוב — סמן must-fix לעומת nice-to-have",
            ],
            metadata={"work_type": work_type, "domain": "creative_critique"},
        )

    def _general_creative_advice(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        is_hebrew: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Provide general creative advice."""
        if is_hebrew is None:
            is_hebrew = _detect_hebrew(query)

        if is_hebrew:
            analysis = {
                "domain": "general_creative",
                "assessment": (
                    "עולם הקריאייטיב דורש שילוב של רעיונות מקוריים, "
                    "הבנת קהל, וביצוע טכני מעולה. "
                    "הצלחה מגיעה ממחקר מעמיק, תהליך יצירתי מובנה, "
                    "ומדידה מתמדת של ביצועים."
                ),
                "creative_process": [
                    "1. Discovery — מחקר, הגדרת בעיה, הבנת קהל",
                    "2. Strategy — הגדרת כיוון, יעדים, מסגרת",
                    "3. Ideation — גנרט רעיונות, ללא שיפוט",
                    "4. Development — בחירת רעיונות, פיתוח, איטרציות",
                    "5. Execution — ייצור, בקרת איכות, פרטים",
                    "6. Launch — הפצה, מדידה, אופטימיזציה",
                ],
            }
        else:
            analysis = {
                "domain": "general_creative",
                "assessment": (
                    "The creative world requires a combination of original ideas, "
                    "audience understanding, and excellent technical execution. "
                    "Success comes from in-depth research, structured creative process, "
                    "and continuous performance measurement."
                ),
                "creative_process": [
                    "1. Discovery — research, problem definition, audience understanding",
                    "2. Strategy — direction definition, objectives, framework",
                    "3. Ideation — generate ideas without judgment",
                    "4. Development — select ideas, develop, iterate",
                    "5. Execution — production, quality control, details",
                    "6. Launch — distribution, measurement, optimization",
                ],
            }

        return self._build_response(
            query=query,
            analysis=analysis,
            metadata={"domain": "general_creative"},
        )

    def get_disclaimer(self) -> str:
        """Creative-specific disclaimer."""
        return (
            "המלצות יצירתיות מסופקות כהכוונה מקצועית. התוצאות תלויות בביצוע, "
            "בקהל היעד, ובהקשר הספציפי של כל פרויקט. יש לבצע מחקר נוסף "
            "ולבדוק עם בעלי עניין לפני יישום."
        )

    # ---- Internal helpers --------------------------------------------

    def _detect_creative_domain(self, query: str) -> List[str]:
        """Detect creative domain from query."""
        q = query.lower()
        domains = []
        domain_map = {
            "design": ["design", "logo", "layout", "visual", "graphic", "עיצוב", "לוגו"],
            "brand": ["brand", "identity", "branding", "positioning", "מיתוג", "זהות מותג"],
            "creative_brief": ["brief", "creative brief", "בrief יצירתי"],
            "content": ["content", "calendar", "social media", "post", " editorial", "תוכן", "לוח תוכן"],
            "art_direction": ["art direction", "visual direction", "mood", "style", "כיוון אמנותי"],
            "critique": ["critique", "review", "feedback", "opinion", "ביקורת", "משוב"],
            "ux": ["ux", "ui", "user experience", "interface", "prototype", "wireframe"],
            "video": ["video", "film", "animation", "motion", "וידאו", "אנימציה"],
            "copy": ["copy", "text", "headline", "slogan", "tagline", "script", "כתיבה"],
            "photo": ["photo", "photography", "image", "picture", "צילום", "תמונה"],
        }
        for domain, keywords in domain_map.items():
            if any(kw in q for kw in keywords):
                domains.append(domain)
        return domains if domains else ["general"]


# =============================================================================
#                     PERSONA FACTORY
# =============================================================================

class PersonaFactory:
    """
    Factory for creating and managing expert personas.
    Provides persona creation, listing, and intelligent query routing.
    """

    _PERSONA_REGISTRY: Dict[str, type] = {
        "lawyer": SeniorLawyerPersona,
        "engineer": SeniorEngineerPersona,
        "doctor": SeniorDoctorPersona,
        "advisor": BusinessAdvisorPersona,
        "manager": ProjectManagerPersona,
        "creative": CreativeDirectorPersona,
        # Aliases
        "legal": SeniorLawyerPersona,
        "tech": SeniorEngineerPersona,
        "medical": SeniorDoctorPersona,
        "business": BusinessAdvisorPersona,
        "pm": ProjectManagerPersona,
        "design": CreativeDirectorPersona,
    }

    @staticmethod
    def create(persona_type: str, **kwargs: Any) -> BaseExpertPersona:
        """
        Create a persona by type string.

        Args:
            persona_type: The type of persona to create.
                         Supported: 'lawyer', 'engineer', 'doctor',
                         'advisor', 'manager', 'creative' and aliases.
            **kwargs: Optional overrides for persona attributes (name, title, etc.)

        Returns:
            An instantiated BaseExpertPersona subclass.

        Raises:
            ValueError: If persona_type is not recognized.

        Examples:
            >>> lawyer = PersonaFactory.create("lawyer")
            >>> custom_lawyer = PersonaFactory.create("lawyer", name="Custom Name")
        """
        key = persona_type.lower().strip()
        persona_class = PersonaFactory._PERSONA_REGISTRY.get(key)
        if persona_class is None:
            available = ", ".join(sorted(PersonaFactory._PERSONA_REGISTRY.keys()))
            raise ValueError(
                f"Unknown persona type '{persona_type}'. "
                f"Available types: {available}"
            )
        return persona_class(**kwargs)

    @staticmethod
    def list_personas() -> List[Dict[str, str]]:
        """
        List all available persona types with descriptions.

        Returns:
            List of dictionaries with persona metadata.
        """
        # Return unique personas (filter aliases)
        seen_classes: set = set()
        personas: List[Dict[str, str]] = []

        descriptions = {
            SeniorLawyerPersona: "Expert in all legal domains — contracts, IP, corporate, labor, privacy, cyber law",
            SeniorEngineerPersona: "Expert in all engineering — software, AI/ML, DevOps, security, embedded",
            SeniorDoctorPersona: "Expert in all medical specialties — diagnosis, treatment, emergency triage",
            BusinessAdvisorPersona: "Expert in business strategy — startups, M&A, finance, marketing, growth",
            ProjectManagerPersona: "Expert in PM methodologies — Agile, Scrum, Kanban, Waterfall, PMP",
            CreativeDirectorPersona: "Expert in creative domains — design, UX/UI, branding, content, video",
        }

        primary_keys = ["lawyer", "engineer", "doctor", "advisor", "manager", "creative"]
        for key in primary_keys:
            cls = PersonaFactory._PERSONA_REGISTRY[key]
            if cls not in seen_classes:
                seen_classes.add(cls)
                # Create a temporary instance to get name/title
                try:
                    instance = cls()
                    personas.append({
                        "type": key,
                        "name": instance.name,
                        "title": instance.title,
                        "description": descriptions.get(cls, ""),
                        "expertise_count": str(len(instance.expertise_domains)),
                    })
                except Exception:
                    personas.append({
                        "type": key,
                        "name": cls.__name__,
                        "title": "Expert",
                        "description": descriptions.get(cls, ""),
                        "expertise_count": "N/A",
                    })

        return personas

    @staticmethod
    def route_query(query: str) -> BaseExpertPersona:
        """
        Route a query to the best-matching persona based on keyword analysis.

        Scoring algorithm:
            1. Count keyword matches per persona
            2. Apply Hebrew keyword bonus (x2 weight for Hebrew matches)
            3. Select persona with highest score
            4. Default to BusinessAdvisorPersona if no clear match

        Args:
            query: The user's query string.

        Returns:
            The best-matching BaseExpertPersona instance.

        Examples:
            >>> persona = PersonaFactory.route_query("Write a software contract")
            >>> isinstance(persona, SeniorLawyerPersona)
            True
        """
        if not query or not query.strip():
            return PersonaFactory.create("advisor")

        query_lower = query.lower()
        scores: Dict[str, int] = {}

        # Calculate keyword match scores
        for persona_key, keywords in PERSONA_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                kw_lower = keyword.lower()
                if kw_lower in query_lower:
                    # Hebrew keywords get double weight (more specific)
                    weight = 2 if _detect_hebrew(keyword) else 1
                    score += weight
            scores[persona_key] = score

        # Find the persona with the highest score
        best_match = max(scores, key=scores.get)
        best_score = scores[best_match]

        # If no meaningful match found, default to advisor
        if best_score == 0:
            return PersonaFactory.create("advisor")

        return PersonaFactory.create(best_match)

    @staticmethod
    def get_all_routes(query: str) -> List[Dict[str, Any]]:
        """
        Get routing scores for all personas (useful for debugging).

        Args:
            query: The user's query string.

        Returns:
            List of dicts with persona type and match score.
        """
        query_lower = query.lower()
        results: List[Dict[str, Any]] = []

        for persona_key, keywords in PERSONA_KEYWORDS.items():
            score = 0
            matched_keywords: List[str] = []
            for keyword in keywords:
                kw_lower = keyword.lower()
                if kw_lower in query_lower:
                    weight = 2 if _detect_hebrew(keyword) else 1
                    score += weight
                    matched_keywords.append(keyword)
            results.append({
                "persona": persona_key,
                "score": score,
                "matched_keywords": matched_keywords,
            })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results


# =============================================================================
#                     MODULE EXPORTS
# =============================================================================

__all__ = [
    # Base class
    "BaseExpertPersona",
    # Persona implementations
    "SeniorLawyerPersona",
    "SeniorEngineerPersona",
    "SeniorDoctorPersona",
    "BusinessAdvisorPersona",
    "ProjectManagerPersona",
    "CreativeDirectorPersona",
    # Factory
    "PersonaFactory",
    # Utilities
    "PERSONA_KEYWORDS",
    "_detect_hebrew",
]
