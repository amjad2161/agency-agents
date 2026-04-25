"""
Example Workflows for Amjad Jarvis Meta-Orchestrator

Runnable scenarios demonstrating multi-agent coordination.
"""

from __future__ import annotations

from agency.amjad_jarvis_meta_orchestrator import jarvis


# ============================================================================
# WORKFLOW 1: PRODUCT DISCOVERY & LAUNCH
# ============================================================================

def workflow_product_discovery():
    """
    Full product discovery workflow:
    - Market research (Trend Researcher)
    - Technical feasibility (Backend Architect)
    - Design thinking (UX Researcher + Brand Guardian)
    - GTM planning (Growth Hacker)
    - Execution roadmap (Project Shepherd)
    
    All agents work in parallel, synthesize results.
    """
    j = jarvis()
    
    print("\n" + "=" * 70)
    print("🚀 PRODUCT DISCOVERY WORKFLOW")
    print("=" * 70)
    
    request = """
    Evaluate building a new AI-powered analytics dashboard for SaaS companies.
    
    Provide:
    1. Market opportunity assessment
    2. Technical architecture overview
    3. Design/UX principles
    4. Go-to-market strategy
    5. 12-week execution plan
    """
    
    results = j.execute_multi_agent_workflow(
        workflow_name="product_discovery",
        primary_request=request,
        agent_sequence=[
            "product-trend-researcher",
            "engineering-backend-architect",
            "design-ux-researcher",
            "design-brand-guardian",
            "marketing-growth-hacker",
            "project-management-project-shepherd",
        ],
        parallel=True,
    )
    
    print("\n✓ Workflow Results:")
    for agent_slug, result in results.items():
        print(f"\n  {agent_slug}:")
        print(f"    Turns: {result.turns}")
        print(f"    Tokens: {result.usage.input_tokens}→{result.usage.output_tokens}")
        print(f"    Preview: {result.text[:100]}...")


# ============================================================================
# WORKFLOW 2: FEATURE DEVELOPMENT END-TO-END
# ============================================================================

def workflow_feature_development():
    """
    Complete feature build from spec to production:
    - Backend implementation
    - Database schema design
    - Frontend development
    - Security review
    - Testing & validation
    - Documentation
    
    Sequential execution with context passing.
    """
    j = jarvis()
    
    print("\n" + "=" * 70)
    print("💻 FEATURE DEVELOPMENT WORKFLOW")
    print("=" * 70)
    
    request = """
    Build passwordless authentication (email + TOTP) for our platform.
    
    Requirements:
    - Email verification flow
    - TOTP 2FA integration
    - Device trust/remember
    - Session management
    - Comprehensive test coverage
    """
    
    results = j.execute_multi_agent_workflow(
        workflow_name="feature_development",
        primary_request=request,
        agent_sequence=[
            "engineering-backend-architect",
            "engineering-database-optimizer",
            "engineering-engineering-frontend-developer",
            "engineering-engineering-security-engineer",
            "testing-testing-reality-checker",
            "engineering-engineering-technical-writer",
        ],
        parallel=False,  # Sequential - each builds on prior
    )
    
    print("\n✓ Development Pipeline:")
    for i, (agent_slug, result) in enumerate(results.items(), 1):
        print(f"\n  Step {i}: {agent_slug}")
        print(f"    Result: {result.text[:80]}...")


# ============================================================================
# WORKFLOW 3: PRODUCTION INCIDENT RESPONSE
# ============================================================================

def workflow_incident_response():
    """
    Emergency incident response with parallel investigation:
    - DevOps diagnostic (immediate triage)
    - Backend root cause analysis
    - Frontend impact assessment
    - SRE incident management
    - Post-incident review
    """
    j = jarvis()
    
    print("\n" + "=" * 70)
    print("🚨 INCIDENT RESPONSE WORKFLOW")
    print("=" * 70)
    
    request = """
    PRODUCTION DOWN: Frontend errors for 15% of users starting 2 hours ago.
    
    Immediate actions:
    1. Diagnose root cause
    2. Assess impact scope
    3. Execute fix/rollback
    4. Verify recovery
    5. Document incident
    """
    
    results = j.execute_multi_agent_workflow(
        workflow_name="incident_response",
        primary_request=request,
        agent_sequence=[
            "engineering-engineering-devops-automator",
            "engineering-engineering-backend-architect",
            "engineering-engineering-frontend-developer",
            "engineering-engineering-sre",
            "engineering-engineering-incident-response-commander",
        ],
        parallel=True,  # Initial diagnostics in parallel
    )
    
    print("\n✓ Incident Response Complete:")
    for agent_slug, result in results.items():
        print(f"\n  {agent_slug}: {result.text[:100]}...\"")


# ============================================================================
# WORKFLOW 4: SECURITY AUDIT & HARDENING
# ============================================================================

def workflow_security_audit():
    """
    Comprehensive security review:
    - Code security analysis
    - Infrastructure security
    - Threat modeling
    - Compliance check
    - Remediation planning
    """
    j = jarvis()
    
    print("\n" + "=" * 70)
    print("🔒 SECURITY AUDIT WORKFLOW")
    print("=" * 70)
    
    request = """
    Conduct comprehensive security audit of our platform.
    
    Review areas:
    1. Application security (OWASP Top 10)
    2. Infrastructure & cloud security
    3. Data protection & privacy
    4. Authentication & authorization
    5. Third-party risk assessment
    
    Provide findings, priority, and remediation plan.
    """
    
    results = j.execute_multi_agent_workflow(
        workflow_name="security_audit",
        primary_request=request,
        agent_sequence=[
            "engineering-engineering-security-engineer",
            "engineering-engineering-code-reviewer",
            "support-support-infrastructure-maintainer",
            "engineering-engineering-backend-architect",
            "support-support-legal-compliance-checker",
        ],
        parallel=True,
    )
    
    print("\n✓ Security Assessment Complete:")
    print("Agents involved:")
    for agent_slug in results.keys():
        print(f"  • {agent_slug}")


# ============================================================================
# WORKFLOW 5: GTM CAMPAIGN EXECUTION
# ============================================================================

def workflow_gtm_campaign():
    """
    Full go-to-market campaign coordination:
    - Content creation
    - Social media strategy
    - Ad campaign planning
    - Email marketing
    - Analytics & measurement
    """
    j = jarvis()
    
    print("\n" + "=" * 70)
    print("📢 GTM CAMPAIGN WORKFLOW")
    print("=" * 70)
    
    request = """
    Launch Q2 GTM campaign for new product.
    
    Scope:
    1. Campaign positioning & messaging
    2. Content calendar (blog, social, email)
    3. Paid media plan (Google, Meta, LinkedIn)
    4. Launch email sequence
    5. Analytics & success metrics dashboard
    
    Timeline: 2 weeks to launch
    """
    
    results = j.execute_multi_agent_workflow(
        workflow_name="gtm_campaign",
        primary_request=request,
        agent_sequence=[
            "marketing-marketing-content-creator",
            "marketing-marketing-social-media-strategist",
            "paid-media-paid-media-ppc-strategist",
            "marketing-marketing-growth-hacker",
            "support-support-analytics-reporter",
        ],
        parallel=True,
    )
    
    print("\n✓ Campaign Strategy Delivered:")
    for agent_slug, result in results.items():
        print(f"\n  {agent_slug}:")
        print(f"    Output: {len(result.text)} chars | {result.turns} turns")


# ============================================================================
# WORKFLOW 6: CODEBASE ANALYSIS & OPTIMIZATION
# ============================================================================

def workflow_codebase_analysis():
    """
    Deep codebase analysis for optimization:
    - Code quality review
    - Performance profiling
    - Architecture review
    - Dependency audit
    - Technical debt assessment
    """
    j = jarvis()
    
    print("\n" + "=" * 70)
    print("📊 CODEBASE ANALYSIS WORKFLOW")
    print("=" * 70)
    
    request = """
    Analyze our main backend codebase for:
    1. Code quality issues (maintainability, readability)
    2. Performance bottlenecks
    3. Security vulnerabilities
    4. Technical debt
    5. Architectural improvements
    
    Provide prioritized recommendations with effort estimates.
    """
    
    results = j.execute_multi_agent_workflow(
        workflow_name="codebase_analysis",
        primary_request=request,
        agent_sequence=[
            "engineering-engineering-code-reviewer",
            "engineering-engineering-security-engineer",
            "testing-testing-performance-benchmarker",
            "engineering-engineering-software-architect",
            "engineering-engineering-database-optimizer",
        ],
        parallel=True,
    )
    
    print("\n✓ Codebase Analysis Complete:")
    print(f"Total agents: {len(results)}")
    print(f"Total output: {sum(len(r.text) for r in results.values())} chars")


# ============================================================================
# MAIN: RUN ALL WORKFLOWS
# ============================================================================

if __name__ == "__main__":
    import sys
    
    workflows = {
        "product_discovery": workflow_product_discovery,
        "feature_development": workflow_feature_development,
        "incident_response": workflow_incident_response,
        "security_audit": workflow_security_audit,
        "gtm_campaign": workflow_gtm_campaign,
        "codebase_analysis": workflow_codebase_analysis,
    }
    
    if len(sys.argv) > 1:
        workflow_name = sys.argv[1]
        if workflow_name in workflows:
            workflows[workflow_name]()
        else:
            print(f"Unknown workflow: {workflow_name}")
            print(f"Available: {', '.join(workflows.keys())}")
    else:
        print("Amjad Jarvis Example Workflows")
        print("==============================\n")
        print("Available workflows:")
        for name in workflows.keys():
            print(f"  python -m examples.amjad_workflows {name}")
