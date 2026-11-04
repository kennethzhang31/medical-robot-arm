"""Loopback-only credential and budget boundary for native ASPIRE model calls."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .artifacts import write_json


def messages_payload(payload):
    """Map the transport envelope to the gateway's native Anthropic route."""
    messages, system = [], []
    for message in payload['messages']:
        content = message.get('content') or []
        if message['role'] == 'system':
            system.append(dict(type='text', text=content))
            continue
        if isinstance(content, str):
            content = [dict(type='text', text=content)]
        blocks = []
        for block in content:
            if block['type'] == 'text':
                blocks.append(block)
            elif block['type'] == 'image_url':
                header, data = block['image_url']['url'].split(',', 1)
                if not header.startswith('data:') or not header.endswith(';base64'):
                    raise ValueError('Only explicit local sensor image data is supported')
                blocks.append(dict(type='image', source=dict(type='base64',
                    media_type=header[5:-7], data=data)))
            else:
                raise ValueError('Unsupported native message block')
        for call in message.get('tool_calls', []):
            blocks.append(dict(type='tool_use', id=call['id'], name=call['function']['name'],
                               input=json.loads(call['function']['arguments'])))
        role = message['role']
        if role == 'tool':
            blocks = [dict(type='tool_result', tool_use_id=message['tool_call_id'], content=blocks)]
            role = 'user'
        if messages and messages[-1]['role'] == role:
            messages[-1]['content'].extend(blocks)
        else:
            messages.append(dict(role=role, content=blocks))
    result = dict(model=payload['model'], max_tokens=payload['max_tokens'],
                  system=system, messages=messages, stream=True)
    for key in ('timeout', 'stream_timeout'):
        if key in payload:
            result[key] = payload[key]
    if payload.get('tools'):
        result['tools'] = [dict(name=tool['function']['name'], description=tool['function'].get('description', ''),
            input_schema=tool['function']['parameters'], eager_input_streaming=True) for tool in payload['tools']]
        choice = payload.get('tool_choice', 'auto')
        result['tool_choice'] = (dict(type='tool', name=choice['function']['name'])
                                 if isinstance(choice, dict) else dict(type='any' if choice == 'required' else 'auto'))
    return result


def collect_messages_stream(response, raw_path, *, timeout=1800):
    started = time.monotonic()
    result, blocks, usage = {}, {}, {}
    closed_blocks = set()
    stopped, finish = False, None
    with Path(raw_path).open('wb') as raw:
        for line in response:
            raw.write(line)
            raw.flush()
            if time.monotonic()-started > timeout:
                raise TimeoutError('Provider stream exceeded its wall-time budget')
            if not line.startswith(b'data:'):
                continue
            event = json.loads(line[5:].strip())
            kind = event.get('type')
            if kind == 'error':
                raise RuntimeError('Provider error in native stream; see SSE artifact')
            if kind == 'message_start':
                msg = event['message']
                result.update(id=msg.get('id'), model=msg.get('model'))
                usage.update(msg.get('usage') or {})
            elif kind == 'content_block_start':
                block = event['content_block'].copy()
                block['partial_json'] = ''
                blocks[event['index']] = block
            elif kind == 'content_block_delta':
                block = blocks[event['index']]
                delta = event['delta']
                if delta['type'] == 'text_delta':
                    block['text'] = block.get('text', '') + delta['text']
                elif delta['type'] == 'input_json_delta':
                    block['partial_json'] += delta['partial_json']
            elif kind == 'message_delta':
                finish = event.get('delta', {}).get('stop_reason') or finish
                usage.update(event.get('usage') or {})
            elif kind == 'content_block_stop':
                closed_blocks.add(event['index'])
            elif kind == 'message_stop':
                stopped = True
                break
    if not stopped or finish is None:
        raise RuntimeError('Incomplete native stream preserved; execution rejected')
    for index, block in blocks.items():
        if block['type'] != 'tool_use':
            continue
        if index not in closed_blocks:
            raise RuntimeError('Incomplete native tool block preserved; execution rejected')
        try:
            arguments = json.loads(block['partial_json'] or json.dumps(block.get('input', {})))
        except ValueError as error:
            raise RuntimeError('Malformed native tool arguments preserved; execution rejected') from error
        if not isinstance(arguments, dict):
            raise RuntimeError('Native tool arguments must be an object; execution rejected')
    message = dict(role='assistant', content=''.join(block.get('text', '') for block in blocks.values()) or None)
    calls = [dict(id=block['id'], type='function', function=dict(name=block['name'],
                 arguments=block['partial_json'] or json.dumps(block.get('input', {}))))
             for block in blocks.values() if block['type'] == 'tool_use']
    if calls:
        message['tool_calls'] = calls
    normalized_finish = dict(tool_use='tool_calls', max_tokens='length').get(finish, 'stop')
    if finish == 'end_turn' and calls:
        normalized_finish = 'tool_calls'
    result['choices'] = [dict(index=0, message=message,
        finish_reason=normalized_finish)]
    input_tokens = usage.get('input_tokens', 0)+usage.get('cache_read_input_tokens', 0)+usage.get('cache_creation_input_tokens', 0)
    result['usage'] = dict(prompt_tokens=input_tokens, completion_tokens=usage.get('output_tokens', 0),
                          total_tokens=input_tokens+usage.get('output_tokens', 0), native=usage)
    return result


def collect_stream(response, raw_path, *, timeout=1800):
    """Preserve SSE bytes and reconstruct text/tool calls without changing prompts."""
    started = time.monotonic()
    result = dict(object='chat.completion', choices=[])
    content, tool_calls, finish, done = '', {}, None, False
    with Path(raw_path).open('wb') as raw:
        for line in response:
            raw.write(line)
            raw.flush()
            if time.monotonic()-started > timeout:
                raise TimeoutError('Provider stream exceeded its wall-time budget')
            if not line.startswith(b'data:'):
                continue
            data = line[5:].strip()
            if data == b'[DONE]':
                done = True
                break
            if not data:
                continue
            event = json.loads(data)
            if event.get('error'):
                raise RuntimeError('Provider returned an error in the stream; see saved SSE artifact')
            for key in ('id', 'model', 'created', 'usage'):
                if event.get(key) is not None:
                    result[key] = event[key]
            for choice in event.get('choices', []):
                if choice.get('index', 0) != 0:
                    continue
                delta = choice.get('delta', {})
                content += delta.get('content') or ''
                for call in delta.get('tool_calls', []):
                    item = tool_calls.setdefault(call['index'], dict(id='', type='function', function=dict(name='', arguments='')))
                    if call.get('id'):
                        item['id'] = call['id']
                    for key in ('name', 'arguments'):
                        item['function'][key] += call.get('function', {}).get(key) or ''
                if choice.get('finish_reason'):
                    finish = choice['finish_reason']
    if not done or finish is None:
        raise RuntimeError('Incomplete provider stream preserved; execution rejected')
    message = dict(role='assistant', content=content or None)
    if tool_calls:
        message['tool_calls'] = [tool_calls[index] for index in sorted(tool_calls)]
    result['choices'] = [dict(index=0, finish_reason=finish, message=message)]
    return result


class ProviderRelay:
    def __init__(self, directory, *, base_url, model, credential, request_budget=22,
                 prior_requests=2, timeout=1800., max_output_tokens=128000, upstream_stream=False,
                 native_messages=False):
        self.directory = Path(directory)
        self.directory.mkdir()
        self.base_url, self.model, self.credential = base_url, model, credential
        self.request_budget, self.prior_requests = request_budget, prior_requests
        self.timeout, self.max_output_tokens = timeout, max_output_tokens
        self.upstream_stream = upstream_stream
        self.native_messages = native_messages
        self.requests = 0
        self.completed = 0
        self.lock = threading.Lock()
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, status, body):
                value = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(value)))
                self.end_headers()
                try:
                    self.wfile.write(value)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                if self.path != "/budget":
                    self.respond(404, {})
                    return
                with relay.lock:
                    self.respond(200, relay.state())

            def do_POST(self):
                if self.path != "/chat/completions":
                    self.respond(400, {"error": "Unsupported relay endpoint"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if not 0 < length <= 32*1024*1024:
                        raise ValueError("Invalid request size")
                    payload = json.loads(self.rfile.read(length))
                    if payload.get("model") != relay.model or not payload.get("messages"):
                        raise ValueError("Unexpected model or messages")
                    payload["max_tokens"] = relay.max_output_tokens
                    if relay.upstream_stream:
                        payload['stream'] = True
                        payload['stream_options'] = dict(include_usage=True)
                        # Set the gateway's upstream deadline as well as our socket timeout.
                        payload['timeout'] = relay.timeout
                        payload['stream_timeout'] = relay.timeout
                except (ValueError, TypeError):
                    self.respond(400, {"error": "Invalid relay request"})
                    return
                with relay.lock:
                    if relay.requests >= relay.request_budget:
                        self.respond(400, {"error": "Approved request budget exhausted"})
                        return
                    relay.requests += 1
                    number = relay.requests
                    relay.checkpoint()
                prefix = relay.directory/f"request_{number:03d}"
                if relay.native_messages:
                    write_json(prefix.with_suffix('.client_request.json'), payload)
                    payload = messages_payload(payload)
                write_json(prefix.with_suffix(".request.json"), payload)
                endpoint = '/messages' if relay.native_messages else '/chat/completions'
                request = urllib.request.Request(relay.base_url.rstrip("/")+endpoint,
                    data=json.dumps(payload).encode(), headers={"Content-Type":"application/json",
                    "Authorization":"Bearer "+relay.credential, 'anthropic-version':'2023-06-01'})
                try:
                    with urllib.request.urlopen(request, timeout=relay.timeout) as response:
                        if relay.native_messages:
                            completion = collect_messages_stream(response, prefix.with_suffix('.stream.sse'), timeout=relay.timeout)
                        elif relay.upstream_stream and 'text/event-stream' in response.headers.get('Content-Type', ''):
                            completion = collect_stream(response, prefix.with_suffix('.stream.sse'), timeout=relay.timeout)
                        else:
                            completion = json.load(response)
                    # Preserve raw responses before upstream extraction or validation.
                    write_json(prefix.with_suffix(".response.json"), completion)
                    choices = completion.get("choices", [])
                    finish = choices[0].get("finish_reason") if choices else None
                    write_json(prefix.with_suffix(".usage.json"), dict(usage=completion.get("usage"),
                        model=completion.get("model"), finish_reason=finish))
                    if finish == "length":
                        self.respond(400, {"error": "Completion truncated; execution rejected"})
                    else:
                        self.respond(200, completion)
                except Exception as error:
                    # Non-retryable relay status prevents upstream's unbounded HTTP retry loop.
                    record = dict(error_type=type(error).__name__)
                    if isinstance(error, urllib.error.HTTPError):
                        record["http_status"] = error.code
                        record["provider_detail"] = error.read(8192).decode("utf-8", errors="replace").replace(relay.credential, "[redacted]")
                    elif isinstance(error, urllib.error.URLError):
                        record["reason_type"] = type(error.reason).__name__
                        record["reason"] = str(error.reason).replace(relay.credential, "[redacted]")
                    else:
                        record['reason'] = str(error).replace(relay.credential, '[redacted]')
                    write_json(prefix.with_suffix(".error.json"), record)
                    self.respond(400, {"error": record})
                finally:
                    with relay.lock:
                        relay.completed += 1
                        relay.checkpoint()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.checkpoint()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def state(self):
        return dict(requests=self.requests, completed=self.completed,
            pending=self.requests-self.completed, remaining=self.request_budget-self.requests,
            prior_requests=self.prior_requests, total_requests=self.prior_requests+self.requests,
            max_total_requests=self.prior_requests+self.request_budget)

    def checkpoint(self):
        write_json(self.directory/"report.json", self.state())

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
