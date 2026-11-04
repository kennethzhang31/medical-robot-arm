"""Build inspectable, standalone ASPIRE translations of the recorder stages.

The template is expanded before execution so the LLM can edit the entire skill.
No recorder import, simulator access, or hidden expert policy is injected.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "examples/aspire/translated/skill.py.in"

# Contact heights are sensor-based starting calibrations, not root-pose offsets.
# The legacy root offsets are deliberately not applied to a sensor surface point.
PROFILES = {
    "scalpel": dict(contact_height=.004, contact_tolerance=.001),
    "scissor": dict(contact_height=.003, contact_tolerance=.001),
    "love_retractor": dict(contact_height=.003, contact_tolerance=.00025),
    "kelly": dict(contact_height=.008, contact_tolerance=.001),
    "scalpel_type2": dict(contact_height=.005, contact_tolerance=.001),
}


def render_skill(target):
    if target not in PROFILES:
        raise ValueError(f"Unknown translated instrument: {target}")
    profile = dict(target=target, hover_height=.23, pre_height=.060,
                   lift_height=.16, above_height=.18, retreat_height=.22,
                   extra_lower=.0, release_gap=.008, direction_sign=1, **PROFILES[target])
    return TEMPLATE.read_text(encoding="utf-8").replace("@PROFILE@", repr(profile))


def render_protocol(target, *, perception="rfdetr"):
    if target not in PROFILES or perception not in ("rfdetr", "sam3"):
        raise ValueError("Unknown target or perception backend")
    data = json.loads((ROOT / "configs/aspire/surgical.json").read_text(encoding="utf-8"))
    data["development_seeds"] = [501, 502, 503, 504, 505]
    data["evaluation_seeds"] = [601, 602, 603, 604, 605]
    data["task"].update(target=target, perception_backend=perception,
                         rfdetr_url="http://127.0.0.1:8115" if perception == "rfdetr" else None,
                         sam3_url="http://127.0.0.1:8114" if perception == "sam3" else None)
    return json.dumps(data, indent=2) + "\n"


def render_search_protocol(target, *, perception="sam3"):
    data = json.loads(render_protocol(target, perception=perception))
    data.update(development_seeds=list(range(501, 507)),
                validation_seeds=list(range(551, 555)), evaluation_seeds=list(range(601, 611)))
    return json.dumps(data, indent=2) + "\n"


def render_manifest():
    shared = ["src/recorder/phase4_feedback.py", "src/recorder/phase4_approach.py",
              "src/recorder/phase4_tray_slots.py"]
    data = dict(contract="aspire_full_stage_translation_v1", equivalence="stage_structure_sensor_adaptation",
                physical_validation="pending", shared_source_sha256={
                    name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in shared},
                template_sha256=hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(), skills=[])
    for target in PROFILES:
        source = f"backends/phase3_grid_split_{target}_recorder.py"
        data["skills"].append(dict(target=target, source=source,
            source_sha256=hashlib.sha256((ROOT/source).read_bytes()).hexdigest(),
            skill=f"examples/aspire/translated/{target}.py",
            skill_sha256=hashlib.sha256(render_skill(target).encode()).hexdigest(),
            protocols={perception:f"configs/aspire/translated/{target}-{perception}.json"
                       for perception in ("rfdetr", "sam3")}))
    return json.dumps(data, indent=2)+"\n"
