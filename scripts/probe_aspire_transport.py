"""One bounded capability request; no experiment files sent."""
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
from src.aspire.relay import ProviderRelay
from src.aspire.artifacts import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--base-url', default='https://cgv.cs.nthu.edu.tw:9128/v1')
    parser.add_argument('--prior-requests', type=int, required=True)
    parser.add_argument('--max-total-requests', type=int, default=38)
    parser.add_argument('--mode', choices=['tool', 'text'], default='tool')
    args = parser.parse_args()
    if args.prior_requests+1 > args.max_total_requests:
        parser.error('No authorized request remains')
    load_credential(ROOT/'.env', 'API_KEY')
    with ProviderRelay(args.out, base_url=args.base_url,
        model='claude-secondary/claude-opus-4-6', credential=os.environ['API_KEY'],
        request_budget=1, prior_requests=args.prior_requests, upstream_stream=True) as relay:
        payload = dict(model=relay.model, messages=[dict(role='user', content='Reply with OK.')])
        if args.mode == 'tool':
            payload['tools'] = [dict(type='function', function=dict(name='acknowledge',
                description='Acknowledge this transport test.', parameters=dict(type='object',
                properties=dict(ok=dict(type='boolean')), required=['ok'], additionalProperties=False)))]
            payload['tool_choice'] = dict(type='function', function=dict(name='acknowledge'))
        try:
            request = urllib.request.Request(relay.url+'/chat/completions', data=json.dumps(payload).encode(),
                                             headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=1830) as response:
                result = json.load(response)
            print(json.dumps(dict(status='ok', choices=result['choices'], usage=result.get('usage'))))
        except urllib.error.HTTPError as error:
            print(json.dumps(dict(status='error', detail=json.loads(error.read()))))
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
