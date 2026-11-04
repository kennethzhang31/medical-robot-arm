"""Export the three newer USD wrappers as portable USDA, preserving authored data.

Run with a newer USD reader, e.g. C:\\isaac-sim-600\\python.bat. This does not
launch Kit or change the simulation runtime. Original assets are read-only.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = ("love_centered_root_at_center.usd", "kelly_root_at_center.usd", "scalpel_type2_root.usd")


def usd_bindings():
    try:
        from pxr import Sdf
        return Sdf, []
    except ImportError:
        installation = Path(os.environ["ISAAC_PATH"])
        candidates = list((installation/"extscache").glob("omni.usd.libs-*"))
        if len(candidates) != 1:
            raise RuntimeError("Cannot identify this launcher's USD library extension")
        directory = candidates[0]
        handles = []
        if os.name == "nt":
            for binary in (directory/"bin", installation/"kit", installation/"kit/kernel/plugins"):
                if binary.is_dir():
                    handles.append(os.add_dll_directory(str(binary)))
        sys.path.insert(0, str(directory))
        from pxr import Sdf
        return Sdf, handles


def main():
    Sdf, dll_handles = usd_bindings()
    output = ROOT/"env/aspire_usd45"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for filename in WRAPPERS:
        source = ROOT/"assets"/filename
        layer = Sdf.Layer.FindOrOpen(str(source))
        if layer is None:
            raise RuntimeError("USD reader cannot open " + str(source))
        for dependency in layer.GetCompositionAssetDependencies():
            resolved = (source.parent/dependency).resolve()
            if not resolved.is_file():
                raise RuntimeError("Missing referenced asset: " + str(resolved))
            replacement = Path(os.path.relpath(resolved, output)).as_posix()
            layer.UpdateCompositionAssetDependency(dependency, replacement)
        destination = output/(source.stem+".usda")
        if not layer.Export(str(destination)):
            raise RuntimeError("USD export failed: " + str(destination))
        records.append(dict(source=source.relative_to(ROOT).as_posix(),
                            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            converted=destination.relative_to(ROOT).as_posix(),
                            converted_sha256=hashlib.sha256(destination.read_bytes()).hexdigest()))
    (output/"manifest.json").write_text(json.dumps(dict(contract="usd45_text_wrappers_v1", assets=records),
                                                 indent=2)+"\n", encoding="utf-8")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
