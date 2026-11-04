"""Select verified text equivalents of wrappers too new for the 4.5 USD reader."""
import hashlib
import json
from .bootstrap import ROOT


def compatible_assets():
    manifest = ROOT/"env/aspire_usd45/manifest.json"
    if not manifest.exists():
        raise RuntimeError("Missing 4.5 text wrappers; run scripts/convert_aspire_assets.py with a newer USD reader")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data["contract"] != "usd45_text_wrappers_v1":
        raise ValueError("Unknown USD compatibility manifest")
    mapping = {}
    for item in data["assets"]:
        source, converted = ROOT/item["source"], ROOT/item["converted"]
        for file, key in ((source,"source_sha256"), (converted,"converted_sha256")):
            if hashlib.sha256(file.read_bytes()).hexdigest() != item[key]:
                raise RuntimeError("USD compatibility copy is stale: " + str(file))
        mapping[source.name] = converted
    return mapping


def apply_compatible_assets(instruments):
    from dataclasses import replace
    mapping = compatible_assets()
    for name, spec in instruments.items():
        if spec.usd in mapping:
            instruments[name] = replace(spec, usd=str(mapping[spec.usd]))
