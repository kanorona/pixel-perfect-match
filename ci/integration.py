"""Exercise the actual production Compose API and origin protection locally."""
import json
import os
import secrets
import urllib.error
import urllib.request
from uuid import uuid4

BASE = 'http://127.0.0.1:18180'
ORIGIN = os.environ['BLUEPRINT_ORIGIN_TOKEN']


def request(path, expected, method='GET', data=None, token=ORIGIN, auth=None):
    headers = {'apikey': 'sb_publishable_local_demo'}
    if token is not None:
        headers['X-Blueprint-Origin-Token'] = token
    if auth:
        headers['Authorization'] = 'Bearer ' + auth
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(BASE + path, headers=headers, method=method,
        data=json.dumps(data).encode() if data is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as response:
        status, body = response.code, response.read()
    assert status == expected, f'{method} {path.split("?")[0]}: expected {expected}, received {status}'
    return json.loads(body) if body and body[:1] in (b'{', b'[') else body


def main():
    for path in ['/', '/health/ready', '/auth/v1/signup', '/realtime/v1/websocket']:
        request(path, 403, token=None)
        request(path, 403, token='invalid')
    assert request('/health/ready', 200)['status'] == 'ready'
    assert b'<html' in request('/', 200).lower()
    request('/rest/v1/interview_sessions', 401)
    request('/auth/v1/token?grant_type=password', 400, method='POST',
        data={'email': 'demo@example.com', 'password': 'DemoPass123!'})
    credentials = {'email': f'ci-{uuid4().hex}@example.com', 'password': secrets.token_urlsafe(32)}
    signed = request('/auth/v1/signup', 200, method='POST', data=credentials)
    login = request('/auth/v1/token?grant_type=password', 200, method='POST', data=credentials)
    auth = login['access_token']
    created = request('/rest/v1/interview_sessions?select=id', 201, method='POST', auth=auth,
        data={'owner_id': signed['user']['id'], 'title': 'CI integration', 'prompt': 'Disposable test', 'duration_minutes': 15})
    path = '/rest/v1/interview_sessions?id=eq.' + created['id']
    try:
        assert request(path, 200, auth=auth)[0]['title'] == 'CI integration'
        request(path, 401)
    finally:
        request(path, 204, method='DELETE', auth=auth)
    print('Production origin protection, database readiness, frontend, authentication and interview CRUD: OK')


if __name__ == '__main__':
    main()
