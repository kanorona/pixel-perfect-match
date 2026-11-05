"""Require a healthy database and the expected build, with verified HTTPS."""
import json
import sys
import time
import urllib.error
import urllib.request


def check(base_url, revision, attempts=30, delay=10):
    if not base_url.startswith('https://'):
        raise ValueError('Deployment checks require HTTPS')
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(base_url.rstrip('/') + '/health/ready', timeout=10) as response:
                result = json.load(response)
                if response.status == 200 and result.get('status') == 'ready' and result.get('revision') == revision:
                    print(f'HTTPS readiness and revision {revision}: OK')
                    return
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise RuntimeError('The public endpoint did not report the expected healthy revision')


if __name__ == '__main__':
    check(sys.argv[1], sys.argv[2])
