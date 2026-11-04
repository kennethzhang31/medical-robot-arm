"""Read-only API discovery. Credentials are never printed or saved."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.aspire.provider import load_credential


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='https://cgv.cs.nthu.edu.tw:9128/v1')
    parser.add_argument('--out', required=True)
    parser.add_argument('--schema', action='store_true', help='Read public API route metadata instead of the model list')
    args = parser.parse_args()
    if not load_credential(ROOT / '.env', 'API_KEY'):
        raise RuntimeError('Missing API_KEY')
    key = os.environ['API_KEY']
    url = args.base_url.rstrip('/') + '/models'
    if args.schema:
        url = args.base_url.rsplit('/v1', 1)[0] + '/openapi.json'
    request = urllib.request.Request(url,
                                     headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
            result = dict(status=response.status, base_url=args.base_url)
            if args.schema:
                result['routes'] = {path:list(methods) for path, methods in body.get('paths', {}).items()
                                    if any(word in path for word in ('messages', 'completions', 'responses'))}
            else:
                result['models'] = [row.get('id') for row in body.get('data', [])]
    except Exception as error:
        result = dict(error_type=type(error).__name__,
                      reason=str(error).replace(key, '[redacted]'))
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
