"""JARVIS Expert Domain Modules."""
from .expert_clinician import get_expert as get_clinician
from .expert_contracts_law import get_expert as get_contracts_law
from .expert_mathematics import get_expert as get_mathematics
from .expert_physics import get_expert as get_physics
from .expert_psychology_cbt import get_expert as get_psychology_cbt
from .expert_economics import get_expert as get_economics
from .expert_chemistry import get_expert as get_chemistry
from .expert_neuroscience import get_expert as get_neuroscience

__all__ = [
    "get_clinician",
    "get_contracts_law",
    "get_mathematics",
    "get_physics",
    "get_psychology_cbt",
    "get_economics",
    "get_chemistry",
    "get_neuroscience",
]
