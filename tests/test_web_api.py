import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from sonar_a0.adapters import DirencAdapter
from sonar_a0.models import Result, Status
from sonar_a0.transport import Document, FetchError
from sonar_web.api import Settings, create_app
from sonar_web.suppliers import SupplierService

FIXTURES = Path(__file__).parent / 'fixtures'
CSV = b'Reference,Value,MPN,Qty,DNP,Unknown\nU1,Amplifier,LM358P,1,0,keep\nR1,Resistor,TEST-R,1,1,keep-too\n'


class FixtureSuppliers:
    def __init__(self):
        self.calls = []
        self.status = Status.PARTIAL
        self.raise_error = False
        self.started = threading.Event()
        self.release = threading.Event(); self.release.set()
        self.guard = SupplierService()

    def validate_url(self, supplier, url):
        return self.guard.validate_url(supplier, url)

    def retrieve(self, supplier, mpn, url=None):
        self.calls.append((supplier, mpn, url))
        self.started.set(); self.release.wait(5)
        if self.raise_error:
            raise OSError('synthetic failure')
        doc = Document('https://www.direnc.net/test-product', (FIXTURES / 'direnc.html').read_text(encoding='utf-8'), '2026-10-09T12:00:00+00:00', 'synthetic')
        offer = DirencAdapter().parse_product(doc, mpn)
        return Result(supplier, 'product' if url else 'search', mpn, self.status,
                      [offer] if self.status in {Status.OK, Status.PARTIAL} else [], 'Synthetic test fixture, not live supplier data').to_dict()


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.service = FixtureSuppliers()
        self.app = create_app(Settings(max_upload=2048), self.service)
        self.client = TestClient(self.app)
        self.client.__enter__()
        session = self.client.get('/api/session').json()
        self.headers = {'X-Sonar-CSRF': session['csrf']}

    def tearDown(self):
        self.service.release.set()
        self.client.__exit__(None, None, None)

    def upload(self, content=CSV, filename='kicad.csv', mapping=None):
        preview = self.client.post('/api/import/preview', content=content, headers={**self.headers, 'X-Filename': filename})
        self.assertEqual(preview.status_code, 200, preview.text)
        p = preview.json()
        response = self.client.post('/api/boms', json={'preview_id': p['preview_id'], 'mapping': mapping or p['mapping'], 'name': 'Test BoM'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def lookup(self, bom, **options):
        return self.client.post('/api/supplier-jobs', json={'bom_id': bom['id'], 'component_ids': [bom['components'][0]['id']], 'supplier': 'direnc', **options}, headers=self.headers)

    def wait_job(self, job_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.client.get('/api/supplier-jobs/' + job_id).json()
            if result['state'] == 'done':
                return result
            time.sleep(.01)
        self.fail('Supplier job did not finish')

    def test_health_and_frontend(self):
        self.assertEqual(self.client.get('/healthz').json()['status'], 'ok')
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn('SONAR', page.text)
        self.assertIn("script-src 'self'", page.headers['content-security-policy'])
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)
        self.assertEqual(self.client.get('/docs').status_code, 404)

    def test_session_cookie_and_cache_headers(self):
        response = self.client.get('/api/session')
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_api_activity_refreshes_cookie_expiry(self):
        response = self.client.get('/api/procurement')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Max-Age=7200', response.headers['set-cookie'])
        self.assertIn('HttpOnly', response.headers['set-cookie'])

    def test_upload_mapping_and_source_preservation(self):
        bom = self.upload()
        self.assertEqual(len(bom['components']), 2)
        self.assertEqual(bom['components'][0]['raw']['6: Unknown'], 'keep')
        source = self.client.get(f"/api/boms/{bom['id']}/source.csv")
        self.assertIn('keep-too', source.text)

    def test_quantity_edit_and_production(self):
        bom = self.upload(); cid = bom['components'][0]['id']
        response = self.client.patch(f"/api/boms/{bom['id']}", json={'boards': 12}, headers=self.headers)
        self.assertEqual(response.json()['components'][0]['required'], 12)
        edited = self.client.patch(f"/api/boms/{bom['id']}/components/{cid}", json={'quantity': '3', 'references': 'U1 U2 U3'}, headers=self.headers)
        self.assertEqual(edited.json()['components'][0]['required'], 36)

    def test_dnp_excluded_from_export(self):
        self.upload()
        report = self.client.get('/api/procurement').json()
        self.assertEqual(len(report['lines']), 1)
        self.assertIsNone(report['lines'][0]['known_cost'])
        self.assertNotIn('TEST-R', self.client.get('/api/procurement.csv').text)

    def test_api_input_validation(self):
        bom = self.upload()
        for boards in [0, 1.5, True, '3']:
            self.assertEqual(self.client.patch(f"/api/boms/{bom['id']}", json={'boards': boards}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/boms/{bom['id']}/components/{bom['components'][0]['id']}", json={'results': {}}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.patch(f"/api/boms/{bom['id']}/components/{bom['components'][0]['id']}", json={'mpn': None}, headers=self.headers).status_code, 422)
        self.assertEqual(self.lookup(bom, supplier='unknown').status_code, 422)

    def test_csrf_origin_and_host_checks(self):
        self.assertEqual(self.client.post('/api/import/preview', content=CSV, headers={'X-Filename': 'bom.csv'}).status_code, 403)
        self.assertEqual(self.client.post('/api/import/preview', content=CSV, headers={**self.headers, 'X-Filename': 'bom.csv', 'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/session', headers={'Host': 'evil.example'}).status_code, 400)

    def test_private_session_isolation(self):
        bom = self.upload()
        other = TestClient(self.app)
        data = other.get('/api/session').json()
        self.assertEqual(data['boms'], [])
        headers = {'X-Sonar-CSRF': data['csrf']}
        self.assertEqual(other.patch(f"/api/boms/{bom['id']}", json={'boards': 2}, headers=headers).status_code, 404)
        self.assertEqual(other.get(f"/api/boms/{bom['id']}/source.csv").status_code, 404)
        self.assertNotIn('LM358P', other.get('/api/procurement.csv').text)

    def test_unauthorized_and_expired_session(self):
        other = TestClient(self.app)
        self.assertEqual(other.get('/api/procurement').status_code, 401)
        with self.app.state.store.lock:
            for session in self.app.state.store.sessions.values():
                session.touched -= 8000
        self.assertEqual(self.client.get('/api/procurement').status_code, 401)

    def test_upload_size_limit_and_bad_file(self):
        response = self.client.post('/api/import/preview', content=b'x' * 2049, headers={**self.headers, 'X-Filename': 'bom.csv'})
        self.assertEqual(response.status_code, 413)
        for data, name in [(b'not a workbook', 'bom.xlsx'), (b'x', 'bom.exe'), (b'', 'bom.csv')]:
            self.assertEqual(self.client.post('/api/import/preview', content=data, headers={**self.headers, 'X-Filename': name}).status_code, 400)

    def test_supplier_job_integrates_a0_fixture(self):
        bom = self.upload()
        job = self.lookup(bom)
        self.assertEqual(job.status_code, 202)
        done = self.wait_job(job.json()['id'])
        self.assertEqual(done['completed'], 1)
        c = self.client.get('/api/session').json()['boms'][0]['components'][0]
        result = c['results']['direnc']
        self.assertEqual(result['status'], 'partial')
        self.assertIsNone(result['offers'][0]['stock_quantity'])
        self.assertNotEqual(result['offers'][0]['match'], 'exact_mpn')

    def test_manual_urls_allowlist(self):
        bom = self.upload()
        for url in ['http://www.direnc.net/test', 'https://127.0.0.1/test', 'https://evil.example/test', 'https://www.direnc.net.evil.example/test', 'https://user:pass@www.direnc.net/test', 'https://www.direnc.net:8080/test', 'https://www.ozdisan.com/test', 'https://www.direnc.net/test#fragment']:
            self.assertEqual(self.lookup(bom, url=url).status_code, 400, url)
        response = self.lookup(bom, url='https://www.direnc.net/test')
        self.assertEqual(response.status_code, 202)
        self.wait_job(response.json()['id'])
        self.assertEqual(self.service.calls[-1][2], 'https://www.direnc.net/test')

    def test_uncertain_match_requires_acknowledgement(self):
        bom = self.upload(); self.wait_job(self.lookup(bom).json()['id'])
        path = f"/api/boms/{bom['id']}/components/{bom['components'][0]['id']}/choice"
        body = {'supplier': 'direnc', 'offer': 0, 'tier': 0}
        self.assertEqual(self.client.put(path, json=body, headers=self.headers).status_code, 422)
        response = self.client.put(path, json={**body, 'acknowledge_uncertain': True}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        report = self.client.get('/api/procurement').json()
        self.assertEqual(report['lines'][0]['supplier'], 'direnc')
        self.assertIsNotNone(report['lines'][0]['known_cost'])
        self.assertTrue(any('Unverified' in w for w in report['lines'][0]['warnings']))
        self.assertIn('not disclosed', ' '.join(response.json()['results']['direnc']['offers'][0]['warnings']).lower())

    def test_edit_invalidates_results_and_selection(self):
        bom = self.upload(); self.wait_job(self.lookup(bom).json()['id'])
        cid = bom['components'][0]['id']
        self.client.put(f"/api/boms/{bom['id']}/components/{cid}/choice", json={'supplier': 'direnc', 'offer': 0, 'tier': 0, 'acknowledge_uncertain': True}, headers=self.headers)
        result = self.client.patch(f"/api/boms/{bom['id']}/components/{cid}", json={'mpn': 'NEW-PART'}, headers=self.headers).json()
        self.assertEqual(result['components'][0]['results'], {})
        self.assertIsNone(result['components'][0]['choice'])

    def test_stale_async_results_not_applied(self):
        bom = self.upload(); self.service.release.clear()
        job = self.lookup(bom).json()
        self.assertTrue(self.service.started.wait(1))
        resumed = self.client.get('/api/session').json()
        self.assertEqual(resumed['jobs'][0]['id'], job['id'])
        self.assertEqual(resumed['jobs'][0]['state'], 'running')
        self.client.patch(f"/api/boms/{bom['id']}/components/{bom['components'][0]['id']}", json={'mpn': 'CHANGED'}, headers=self.headers)
        self.service.release.set()
        result = self.wait_job(job['id'])
        self.assertFalse(result['results'][0]['applied'])
        self.assertEqual(self.client.get('/api/session').json()['boms'][0]['components'][0]['results'], {})

    def test_failure_and_blocked_batch_stop(self):
        bom = self.upload(b'Reference,MPN,Qty\nU1,P1,1\nU2,P2,1\n')
        self.service.status = Status.BLOCKED
        job = self.lookup(bom, component_ids=[c['id'] for c in bom['components']]).json()
        result = self.wait_job(job['id'])
        self.assertEqual(result['completed'], 1)
        self.assertIn('stopped', result['message'])
        self.assertEqual(len(self.service.calls), 1)

    def test_unexpected_supplier_failure_is_explicit(self):
        bom = self.upload(); self.service.raise_error = True
        result = self.wait_job(self.lookup(bom).json()['id'])
        self.assertEqual(result['results'][0]['status'], 'network_error')
        self.assertIsNone(self.client.get('/api/procurement').json()['lines'][0]['known_cost'])

    def test_supplier_input_checks(self):
        bom = self.upload()
        self.assertEqual(self.lookup(bom, component_ids=[bom['components'][1]['id']]).status_code, 422)
        self.assertEqual(self.lookup(bom, component_ids=[bom['components'][0]['id']] * 2).status_code, 422)
        self.assertEqual(self.lookup(bom, component_ids=['missing']).status_code, 404)
        self.assertEqual(self.lookup(bom, component_ids=[c['id'] for c in bom['components']], url='https://www.direnc.net/test').status_code, 422)

    def test_supplier_rate_limit(self):
        bom = self.upload()
        with self.app.state.store.lock:
            next(iter(self.app.state.store.sessions.values())).rates.extend([time.monotonic()] * 10)
        self.assertEqual(self.lookup(bom).status_code, 429)

    def test_batch_selection_and_remove_bom(self):
        bom = self.upload()
        result = self.client.post(f"/api/boms/{bom['id']}/selection", json={'component_ids': [c['id'] for c in bom['components']], 'selected': False}, headers=self.headers)
        self.assertTrue(all(not c['selected'] for c in result.json()['components']))
        self.assertEqual(self.client.get('/api/procurement').json()['lines'], [])
        self.assertEqual(self.client.delete(f"/api/boms/{bom['id']}", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get('/api/session').json()['boms'], [])


class SupplierFacadeTests(unittest.TestCase):
    def test_dns_private_address_rejected(self):
        service = SupplierService()
        with patch('sonar_web.suppliers.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaisesRegex(ValueError, 'non-public'):
                service.retrieve('direnc', 'P1')

    def test_adapter_reuse_and_policy_refresh(self):
        service = SupplierService()
        adapter = service.adapters['direnc']
        adapter.client.policies['old'] = 'old policy'
        adapter.client.last_request['www.direnc.net'] = 123
        with patch('sonar_web.suppliers.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]), patch.object(adapter, 'search', return_value=Result('direnc', 'search', 'P1', Status.NOT_FOUND)) as search:
            result = service.retrieve('direnc', 'P1')
        search.assert_called_once_with('P1', limit=3)
        self.assertEqual(adapter.client.policies, {})
        self.assertEqual(adapter.client.last_request['www.direnc.net'], 123)
        self.assertEqual(result['status'], 'not_found')


if __name__ == '__main__':
    unittest.main()
