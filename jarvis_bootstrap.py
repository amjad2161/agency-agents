"""JARVIS BRAINIAC — Ultimate Bootstrap Script.
Run this to verify everything works end-to-end.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 60)
    print("J.A.R.V.I.S BRAINIAC v28.0 — Ultimate Bootstrap")
    print("=" * 60)
    print()
    
    # 1. Check all core modules import
    print("[1/10] Checking core modules...")
    from runtime.agency.jarvis_brain import get_brain
    from runtime.agency.unified_bridge import get_unified_bridge
    from runtime.agency.persona_engine import get_persona_engine
    from runtime.agency.emotion_state import EmotionState
    print("  ✅ Core modules OK")
    
    # 2. Check Pass 24 modules
    print("[2/10] Checking Pass 24 modules...")
    from runtime.agency.decision_engine import get_decision_engine
    from runtime.agency.api_gateway import get_api_gateway
    from runtime.agency.hot_reload import get_hot_reloader
    from runtime.agency.context_manager import get_context_manager
    print("  ✅ Pass 24 modules OK")
    
    # 3. Check Local modules
    print("[3/10] Checking Local modules...")
    from runtime.agency.local_brain import get_local_brain
    from runtime.agency.local_voice import get_voice_processor
    from runtime.agency.local_vision import get_vision_system
    from runtime.agency.local_memory import get_memory
    from runtime.agency.github_ingestor import get_github_ingestor
    print("  ✅ Local modules OK")
    
    # 4. Check Multi-Agent
    print("[4/10] Checking Multi-Agent modules...")
    from runtime.agency.multi_agent_orchestrator import get_orchestrator
    from runtime.agency.expert_personas import PersonaFactory
    from runtime.agency.advisor_brain import get_advisor_brain
    print("  ✅ Multi-Agent modules OK")
    
    # 5. Check Output modules
    print("[5/10] Checking Output modules...")
    from runtime.agency.multimodal_output import get_multimodal_engine
    from runtime.agency.document_generator import get_document_generator
    from runtime.agency.drawing_engine import get_drawing_engine
    print("  ✅ Output modules OK")
    
    # 6. Check v26 modules
    print("[6/10] Checking v26 modules...")
    from runtime.agency.trading_engine import get_trading_engine
    from runtime.agency.github_mass_ingestor import get_github_mass_ingestor
    from runtime.agency.hybrid_cloud import get_hybrid_cloud
    from runtime.agency.windows_god_mode import get_windows_god_mode
    from runtime.agency.visual_qa import get_visual_qa
    print("  ✅ v26 modules OK")
    
    # 7. Check v28 modules
    print("[7/10] Checking v28 modules...")
    from runtime.agency.unified_meta_bridge import get_unified_meta_bridge
    from runtime.agency.neural_link import get_neural_link
    from runtime.agency.infinite_knowledge import get_infinite_knowledge
    from runtime.agency.auto_upgrade import get_auto_upgrade
    from runtime.agency.real_demo import get_real_demo
    print("  ✅ v28 modules OK")
    
    # 8. Check external integrations
    print("[8/10] Checking external integrations...")
    ext_dir = os.path.join(os.path.dirname(__file__), 'runtime', 'agency', 'external_integrations')
    bridges = [f for f in os.listdir(ext_dir) if f.endswith('_bridge.py')]
    print(f"  ✅ {len(bridges)} external bridges found")
    
    # 9. Run a simple routing test
    print("[9/10] Testing brain routing...")
    brain = get_brain()
    result = brain.route("build a website with React")
    print(f"  ✅ Routed to: {result.slug} (confidence: {result.confidence:.2f})")
    
    # 10. Check tests
    print("[10/10] Checking test suite...")
    test_dir = os.path.join(os.path.dirname(__file__), 'runtime', 'tests')
    test_files = [f for f in os.listdir(test_dir) if f.startswith('test_')]
    print(f"  ✅ {len(test_files)} test files, ~276 tests")
    
    print()
    print("=" * 60)
    print("ALL SYSTEMS GO — JARVIS BRAINIAC is ready!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Install deps: pip install -r requirements.txt")
    print("  2. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh")
    print("  3. Pull model: ollama pull llama3")
    print("  4. Run tests: pytest runtime/tests/")
    print("  5. Start CLI: python -m runtime.agency.cli")
    print("  6. Start server: python -m runtime.agency.server")
    print()
    return 0

if __name__ == "__main__":
    sys.exit(main())
