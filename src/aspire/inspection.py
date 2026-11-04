"""Development-only, sensor-only evidence tools for the ASPIRE coding actor."""
import base64
import json


INSPECT_TOOL = dict(type='function', function=dict(name='inspect_evidence',
    description=('Read a development replay summary, a slice of its primitive trace, or selected sensor images. '
                 'The summary lists available image paths. Inspect failures before proposing a repair.'),
    parameters=dict(type='object', properties={
        'evidence_id': dict(type='string'),
        'view': dict(type='string', enum=['summary', 'trace', 'images']),
        'start': dict(type='integer', minimum=0),
        'limit': dict(type='integer', minimum=1, maximum=64),
        'images': dict(type='array', maxItems=4, items=dict(type='string'))},
        required=['evidence_id', 'view'], additionalProperties=False)))


def sensor_images(directory):
    # Explicit allowlist: never offer evaluator files, assets or arbitrary paths.
    result = {}
    root = directory.resolve()
    for folder in ('initial', 'final', 'keyframes'):
        for path in sorted((directory/folder).glob('*')):
            if (path.suffix.lower() in ('.png', '.jpg', '.jpeg') and path.is_file()
                    and path.resolve().is_relative_to(root)):
                result[path.relative_to(directory).as_posix()] = path
    return result


def inspect(campaign, arguments, allowed, *, admission=False):
    evidence_id = arguments['evidence_id']
    if evidence_id not in allowed:
        raise ValueError('Evidence is outside the supplied development partition')
    public, directory = campaign.public_trial(evidence_id, admission=admission)
    trace = public.pop('trace', [])
    images = sensor_images(directory)
    view = arguments['view']
    if view == 'summary':
        value = dict(**public, trace_entries=len(trace), images=list(images))
    elif view == 'trace':
        start, limit = arguments.get('start', 0), arguments.get('limit', 32)
        if type(start) is not int or type(limit) is not int or start < 0 or not 1 <= limit <= 64:
            raise ValueError('Trace range must be nonnegative with limit 1..64')
        value = dict(evidence_id=evidence_id, start=start, total=len(trace), entries=trace[start:start+limit])
    elif view == 'images':
        names = arguments.get('images', [])
        if not 1 <= len(names) <= 4 or any(name not in images for name in names):
            raise ValueError('Choose 1..4 image paths from the summary allowlist')
        content = []
        for name in names:
            path = images[name]
            mime = 'image/png' if path.suffix.lower() == '.png' else 'image/jpeg'
            url = f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()
            content.extend([dict(type='text', text=f'{evidence_id}: {name}'),
                            dict(type='image_url', image_url=dict(url=url))])
        return content
    else:
        raise ValueError('Unknown evidence view')
    return [dict(type='text', text=json.dumps(value))]
