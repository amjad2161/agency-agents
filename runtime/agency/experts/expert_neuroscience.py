"""JARVIS Expert: Neuroscience (brain regions, neurotransmitters, conditions)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NeuroscienceQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class NeuroscienceResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "brain", "neuron", "synapse", "cortex", "amygdala", "hippocampus",
    "thalamus", "cerebellum", "neurotransmitter", "dopamine", "serotonin",
    "gaba", "glutamate", "acetylcholine", "norepinephrine", "neuro",
    "memory", "attention", "executive function", "learning", "plasticity",
    "alzheimer", "parkinson", "stroke", "epilepsy", "seizure", "tbi",
    "fmri", "eeg", "neurology", "neuroscience", "axon", "dendrite",
    "myelin", "glia", "astrocyte", "microglia", "bbb",
)

_REGIONS = {
    "prefrontal cortex": "executive function, working memory, decision-making, impulse control",
    "amygdala": "fear processing, emotional salience, threat detection",
    "hippocampus": "declarative/spatial memory consolidation",
    "thalamus": "sensory relay (except olfaction), cortical gating",
    "cerebellum": "motor coordination, timing, motor learning, some cognitive roles",
    "basal ganglia": "action selection, habit learning, reward (striatum)",
    "occipital cortex": "visual processing (V1-V5)",
    "temporal cortex": "auditory, language (left), face/object recognition",
    "parietal cortex": "spatial attention, sensorimotor integration",
    "insula": "interoception, salience, disgust",
    "anterior cingulate": "conflict monitoring, error detection, emotional regulation",
    "brainstem": "arousal, autonomic, cranial nerve nuclei",
}

_NEUROTRANSMITTERS = {
    "dopamine": {
        "pathways": ["mesocortical", "mesolimbic", "nigrostriatal", "tuberoinfundibular"],
        "function": "reward prediction error, motor control, motivation",
        "disorders": ["Parkinson's (loss)", "schizophrenia (excess D2)", "ADHD"],
    },
    "serotonin": {
        "pathways": ["raphe → cortex/limbic"],
        "function": "mood, sleep, appetite, gut motility",
        "disorders": ["depression", "anxiety", "OCD"],
    },
    "gaba": {
        "pathways": ["widespread inhibitory"],
        "function": "primary inhibitory neurotransmitter",
        "disorders": ["epilepsy", "anxiety"],
    },
    "glutamate": {
        "pathways": ["widespread excitatory"],
        "function": "primary excitatory neurotransmitter, LTP/learning",
        "disorders": ["excitotoxicity (stroke)", "schizophrenia (NMDA hypofunction)"],
    },
    "acetylcholine": {
        "pathways": ["basal forebrain → cortex", "neuromuscular junction"],
        "function": "attention, memory, muscle activation",
        "disorders": ["Alzheimer's", "myasthenia gravis"],
    },
    "norepinephrine": {
        "pathways": ["locus coeruleus → cortex"],
        "function": "arousal, vigilance, sympathetic activation",
        "disorders": ["depression", "PTSD", "ADHD"],
    },
}

_CONDITIONS = {
    "alzheimer": "Progressive dementia. Hallmarks: amyloid-β plaques, tau tangles, "
                  "cholinergic deficit. First affects entorhinal cortex/hippocampus.",
    "parkinson": "Loss of dopaminergic neurons in substantia nigra. Cardinal signs: "
                  "tremor, rigidity, bradykinesia, postural instability.",
    "stroke": "Sudden focal neurological deficit from ischemia or hemorrhage. "
               "Time-critical: 'time is brain'. Treat with tPA/thrombectomy if eligible.",
    "epilepsy": "Recurrent unprovoked seizures from abnormal cortical hyperexcitability. "
                 "Classified by onset (focal vs generalized).",
    "ms": "Multiple sclerosis: autoimmune demyelination of CNS white matter. "
           "Classic: optic neuritis, internuclear ophthalmoplegia.",
    "tbi": "Traumatic brain injury: primary (mechanical) + secondary (edema, ischemia, "
            "inflammation) damage. Severity by GCS.",
    "schizophrenia": "Psychotic disorder. Positive (hallucinations/delusions), "
                      "negative, and cognitive symptoms. Dopamine/glutamate hypotheses.",
}

_COGNITIVE_FUNCTIONS = {
    "memory": ["declarative (hippocampus, MTL)", "procedural (cerebellum, basal ganglia)",
               "working (prefrontal)"],
    "attention": ["alerting (locus coeruleus)", "orienting (parietal)",
                  "executive (anterior cingulate, prefrontal)"],
    "language": ["Broca's area (production, left IFG)", "Wernicke's area (comprehension, left STG)"],
    "executive function": ["dorsolateral prefrontal", "anterior cingulate",
                            "orbitofrontal cortex"],
}


class NeuroscienceExpert:
    """JARVIS expert for neuroscience."""

    DOMAIN = "neuroscience"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> NeuroscienceResult:
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        regions = self.lookup_regions(query)
        if regions:
            meta["regions"] = regions
            sources.append("brain-atlas")
            parts.append("Brain regions: " +
                         "; ".join(f"{k}: {v}" for k, v in regions.items()) + ".")

        nts = self.lookup_neurotransmitters(query)
        if nts:
            meta["neurotransmitters"] = nts
            sources.append("neurotransmitter-pathways")
            for n, info in nts.items():
                parts.append(f"{n}: {info['function']}.")

        cond = self.lookup_condition(query)
        if cond:
            meta["condition"] = cond
            sources.append("clinical-neuro")
            parts.append(f"{cond['name']}: {cond['description']}.")

        cog = self.lookup_cognitive_function(query)
        if cog:
            meta["cognitive_function"] = cog
            sources.append("cognitive-mapping")
            parts.append(f"{cog['name']}: substrates → {', '.join(cog['substrates'])}.")

        if not parts:
            parts.append("Neuroscience query received. Specify a brain region, "
                         "neurotransmitter, condition, or cognitive function.")
            confidence = min(confidence, 0.3)

        return NeuroscienceResult(
            answer=" ".join(parts),
            confidence=confidence,
            domain=self.DOMAIN,
            sources=sources,
            metadata=meta,
        )

    def can_handle(self, query: str) -> float:
        q = query.lower()
        hits = sum(1 for kw in _KEYWORDS if kw in q)
        if hits == 0:
            return 0.0
        return min(1.0, 0.3 + 0.12 * hits)

    def lookup_regions(self, query: str) -> dict[str, str]:
        q = query.lower()
        return {name: desc for name, desc in _REGIONS.items() if name in q}

    def lookup_neurotransmitters(self, query: str) -> dict[str, dict[str, Any]]:
        q = query.lower()
        return {n: info for n, info in _NEUROTRANSMITTERS.items() if n in q}

    def lookup_condition(self, query: str) -> dict[str, str] | None:
        q = query.lower()
        for k, desc in _CONDITIONS.items():
            if k in q:
                return {"name": k.title(), "description": desc}
        return None

    def lookup_cognitive_function(self, query: str) -> dict[str, Any] | None:
        q = query.lower()
        for k, subs in _COGNITIVE_FUNCTIONS.items():
            if k in q:
                return {"name": k, "substrates": subs}
        return None

    def receptor_for_neurotransmitter(self, nt: str) -> list[str]:
        receptors = {
            "dopamine": ["D1", "D2", "D3", "D4", "D5"],
            "serotonin": ["5-HT1A", "5-HT2A", "5-HT3", "5-HT4"],
            "gaba": ["GABA_A", "GABA_B"],
            "glutamate": ["NMDA", "AMPA", "kainate", "mGluR"],
            "acetylcholine": ["nicotinic", "muscarinic (M1-M5)"],
            "norepinephrine": ["alpha1", "alpha2", "beta1", "beta2", "beta3"],
        }
        return receptors.get(nt.lower(), [])

    def summarize_paper(self, abstract: str) -> dict[str, Any]:
        words = abstract.split()
        wc = len(words)
        # extract simple keywords by frequency
        freq: dict[str, int] = {}
        for w in words:
            wl = w.lower().strip(".,;:()[]")
            if len(wl) > 5:
                freq[wl] = freq.get(wl, 0) + 1
        top = sorted(freq.items(), key=lambda kv: -kv[1])[:5]
        return {
            "word_count": wc,
            "top_terms": [t for t, _ in top],
            "first_sentence": abstract.split(".")[0].strip() + "." if "." in abstract else abstract,
        }

    def imaging_modality_for(self, target: str) -> str:
        t = target.lower()
        mapping = {
            "structure": "MRI (T1/T2)",
            "function": "fMRI (BOLD)",
            "metabolism": "PET / FDG",
            "electrical": "EEG / MEG",
            "white matter": "DTI",
            "blood flow": "ASL / perfusion MRI",
        }
        for k, v in mapping.items():
            if k in t:
                return v
        return "MRI (general)"

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "regions": len(_REGIONS),
            "neurotransmitters": list(_NEUROTRANSMITTERS.keys()),
            "conditions": list(_CONDITIONS.keys()),
        }


_singleton: NeuroscienceExpert | None = None


def get_expert() -> NeuroscienceExpert:
    global _singleton
    if _singleton is None:
        _singleton = NeuroscienceExpert()
    return _singleton
