"""Tests du client Open Prod (protocole getToken + endpoint) avec HTTP simulé."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api.client as client_module  # noqa: E402
from api.client import OpenProdAPIClient, OpenProdError, OpenProdUnavailable, values_to_pairs  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, body=None, text=''):
        self.status_code = status_code
        self._body = body
        self.text = text or (str(body) if body is not None else '')

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


def ok(data):
    return FakeResponse(200, {'jsonrpc': '2.0', 'id': None, 'result': {'data': data}})


def err(message, status=400):
    return FakeResponse(status, {'jsonrpc': '2.0', 'id': None, 'result': {'error': {'message': message}}})


class ScriptedSession:
    """Rejoue une liste de réponses et mémorise les requêtes envoyées."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


def make_client(responses):
    client = OpenProdAPIClient('http://erp:8068', 'matfer_db', 'secret')
    client.session = ScriptedSession(responses)
    return client


class ValuesTest(unittest.TestCase):
    def test_dict_becomes_pairs(self):
        self.assertEqual(values_to_pairs({'name': 'F1-1', 'qty': 2}), [['name', 'F1-1'], ['qty', 2]])

    def test_pairs_kept(self):
        self.assertEqual(values_to_pairs([('line_ids', [(0, 0, {'a': 1})])]), [['line_ids', [(0, 0, {'a': 1})]]])


class ClientTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(client_module.time, 'sleep', lambda s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_fetches_token_then_posts(self):
        client = make_client([ok('TOKEN1'), ok([42])])
        ids = client.create('keck.electrical.control', {'name': 'F1-1'})
        self.assertEqual(ids, [42])
        (url1, body1), (url2, body2) = client.session.calls
        self.assertTrue(url1.endswith('/web/api/getToken'))
        self.assertEqual(body1, {'db': 'matfer_db', 'id_secret': 'secret'})
        self.assertTrue(url2.endswith('/web/api/endpoint'))
        self.assertEqual(body2['method'], 'create')
        self.assertEqual(body2['model'], 'keck.electrical.control')
        self.assertEqual(body2['token'], 'TOKEN1')
        self.assertEqual(body2['values'], [['name', 'F1-1']])

    def test_any_refusal_is_retried_once_with_a_fresh_token(self):
        # le libellé du jeton expiré n'est pas documenté : on ne dépend d'aucun texte
        client = make_client([ok('OLD'), err('Accès refusé'), ok('NEW'), ok([7])])
        self.assertEqual(client.create('m', {'a': 1}), [7])
        self.assertEqual(client.token, 'NEW')
        self.assertEqual(len(client.session.calls), 4)

    def test_persistent_refusal_is_definitive(self):
        client = make_client([ok('T'), err("Invalid parameter name 'foo'"), ok('T2'), err("Invalid parameter name 'foo'")])
        with self.assertRaises(OpenProdError):
            client.create('m', {'foo': 1})
        self.assertEqual(len(client.session.calls), 4)
        self.assertIn('foo', client.last_error)

    def test_empty_result_gives_no_ids(self):
        client = make_client([ok('T'), ok(None)])
        self.assertEqual(client.create('m', {'a': 1}), [])

    def test_transient_failures_are_retried(self):
        import requests
        client = make_client([ok('T'), requests.Timeout(), FakeResponse(503, None, 'down'), ok([1])])
        self.assertEqual(client.create('m', {'a': 1}), [1])
        self.assertEqual(len(client.session.calls), 4)

    def test_retry_false_fails_fast_on_timeout(self):
        import requests
        client = make_client([ok('T'), requests.Timeout()])
        with self.assertRaises(OpenProdUnavailable):
            client.create('m', {'a': 1}, retry=False)
        self.assertEqual(len(client.session.calls), 2)

    def test_unavailable_after_max_retries(self):
        import requests
        client = make_client([ok('T')] + [requests.ConnectionError('refused')] * client_module.MAX_RETRIES)
        with self.assertRaises(OpenProdUnavailable):
            client.create('m', {'a': 1})

    def test_read_builds_domain(self):
        client = make_client([ok('T'), ok([{'id': 3, 'name': 'F1-1'}])])
        rows = client.read('stock.label', [('name', '=', 'F1-1')], fields=['id', 'name'], limit=1)
        self.assertEqual(rows[0]['id'], 3)
        body = client.session.calls[1][1]
        self.assertEqual(body['filters'], [['name', '=', 'F1-1']])
        self.assertEqual(body['fields'], ['id', 'name'])
        self.assertEqual(body['limit'], 1)

    def test_get_token_error(self):
        client = make_client([err('Invalid database')])
        self.assertFalse(client.check_connection())
        self.assertIn('database', client.last_error)


if __name__ == '__main__':
    unittest.main()
