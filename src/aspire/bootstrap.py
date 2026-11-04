"""Source-path setup; intentionally usable before Kit starts."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "third_party" / "ASPIRE"


def setup_paths():
    required = UPSTREAM / "aspire/sim/cap/envs/tasks/base.py"
    if not required.is_file():
        raise RuntimeError("ASPIRE is missing. Run git submodule update --init third_party/ASPIRE")
    directories = [ROOT, ROOT / "compat", UPSTREAM, ROOT / ".local/aspire-python"]
    lab = ROOT / ".local/IsaacLab/source"
    directories.extend(lab / name for name in ("isaaclab", "isaaclab_assets", "isaaclab_tasks"))
    for directory in directories:
        if not directory.is_dir():
            continue
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)


def upstream_revision():
    """Read the checked-out commit without requiring Git in a simulator worker."""
    git = UPSTREAM / ".git"
    if git.is_file():
        git = (UPSTREAM / git.read_text().strip().removeprefix("gitdir: ")).resolve()
    head = (git / "HEAD").read_text().strip()
    if not head.startswith("ref: "):
        return head
    ref = head[5:]
    if (git / ref).is_file():
        return (git / ref).read_text().strip()
    for line in (git / "packed-refs").read_text().splitlines():
        if line.endswith(" " + ref):
            return line.split()[0]
    raise RuntimeError("Cannot resolve ASPIRE submodule revision")
