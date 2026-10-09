"""Local deterministic browser fixture. Never used by the production app.

Run from repo: PYTHONPATH=src python tools/browser_fixture_server.py
"""
from decimal import Decimal
import time
from sonar_a0.models import Offer, PriceBreak, Result, Status
from sonar_web.api import Settings, create_app
from sonar_web.suppliers import SupplierService
import uvicorn

class BrowserSuppliers:
    def validate_url(self, supplier, url):
        SupplierService().validate_url(supplier, url)

    def retrieve(self, supplier, mpn, url=None):
        time.sleep(2 if mpn == "SLOW" else .25)
        if mpn == 'FAIL':
            return Result(supplier, 'search', mpn, Status.NETWORK_ERROR, message='Synthetic network failure; stock unknown').to_dict()
        if mpn == 'RATE':
            return Result(supplier, 'search', mpn, Status.RATE_LIMITED, message='Synthetic supplier rate limit').to_dict()
        if mpn == 'EMPTY':
            return Result(supplier, 'search', mpn, Status.NOT_FOUND, message='Synthetic empty retrieval').to_dict()
        offer = Offer(supplier, url or 'https://www.direnc.net/synthetic-test-product',
                      '2026-10-09T09:00:00+00:00', 'SYNTHETIC browser fixture ' + mpn,
                      mpn=mpn if supplier == 'ozdisan' else None,
                      match='exact_mpn' if supplier == 'ozdisan' else 'title_token',
                      stock_status='unknown', stock_quantity=None, moq=5, order_multiple=5,
                      prices=[] if mpn == 'UNPRICED' else [
                          PriceBreak(1, Decimal('2.50'), 'TRY', 'included', max_quantity=9),
                          PriceBreak(10, Decimal('2.00'), 'TRY', 'excluded', max_quantity=100),
                          PriceBreak(1, Decimal('0.50'), 'USD', 'unknown')],
                      warnings=['Synthetic test data; not live supplier inventory'],
                      field_sources={'stock_status':'Unknown in synthetic fixture'})
        return Result(supplier, 'product' if url else 'search', mpn, Status.PARTIAL, [offer], 'SYNTHETIC test retrieval').to_dict()

if __name__ == '__main__':
    uvicorn.run(create_app(Settings(origins=('http://127.0.0.1:8013',)), BrowserSuppliers()), host='127.0.0.1', port=8013)
