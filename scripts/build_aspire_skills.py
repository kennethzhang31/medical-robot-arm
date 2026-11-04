"""Materialize the five full-stage ASPIRE skills and matching protocols."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.aspire.translation import ROOT, PROFILES, render_skill, render_protocol, render_search_protocol, render_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check generated files without writing")
    args = parser.parse_args()
    mismatches = []
    all_files = {ROOT / "examples/aspire/translated/manifest.json": render_manifest()}
    for target in PROFILES:
        all_files[ROOT / f"examples/aspire/translated/{target}.py"] = render_skill(target)
        for perception in ("rfdetr", "sam3"):
            all_files[ROOT / f"configs/aspire/translated/{target}-{perception}.json"] = render_protocol(target, perception=perception)
            all_files[ROOT / f"configs/aspire/search/{target}-{perception}.json"] = render_search_protocol(target, perception=perception)
    for path, content in all_files.items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                mismatches.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if mismatches:
        print("Generated files differ: " + ", ".join(mismatches))
        return 1
    print("Checked" if args.check else "Built", "five full-stage skills, ten legacy and ten search protocols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
