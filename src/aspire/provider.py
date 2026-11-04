"""Load one orchestrator credential without evaluating shell or dotenv code."""
import os
import re
from pathlib import Path


def load_credential(path, name):
    """Existing process environment wins; support simple KEY=value dotenv lines.

    Only the requested key is loaded. Quotes and unquoted inline comments are
    supported; interpolation, escape expansion and multiline values are not.
    """
    if os.environ.get(name):
        return True
    path = Path(path)
    if not path.is_file():
        return False
    pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(name) + r"\s*=\s*(.*)$")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end+1:].strip() and not value[end+1:].strip().startswith("#")):
                raise ValueError(f"Invalid single-line credential assignment for {name}")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if value:
            os.environ[name] = value
            return True
    return False
