import io
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from contextlib import closing
from unittest.mock import patch

from PIL import Image
import app as module


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = patch.multiple(module, DB_DIR=self.temp.name,
                                     DB_PATH=os.path.join(self.temp.name, 'bills.db'),
                                     UPLOAD_DIR=os.path.join(self.temp.name, 'uploads'))
        self.config.start()
        module.init_db()
        self.client = module.app.test_client()
        self.bill = dict(totalBill=1000, mainMeter=100, lokantaStart=10,
                         lokantaEnd=50, koltukcuStart=10, koltukcuEnd=30,
                         readingDate='2026-11-06')

    def tearDown(self):
        self.config.stop()
        self.temp.cleanup()

    def test_preview_does_not_save(self):
        response = self.client.post('/api/calculate', json=self.bill)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['shops'][0]['amount'], 400)
        self.assertEqual(self.client.get('/api/calculations').json, [])

    def test_strict_number_formats(self):
        for text, expected in [('878.350', 878.35), ('24883,827', 24883.827),
                               ('1.500,75', 1500.75), ('1,500.75', 1500.75),
                               ('1.500.000', 1500000), ('-10', -10)]:
            with self.subTest(text=text):
                self.assertEqual(module.parse_input_number(text), expected)
        for text in ['12abc34', '1,2,3', '1.2.3', '1..2', '', True, float('inf'), float('nan')]:
            with self.subTest(text=text):
                self.assertIsNone(module.parse_input_number(text))

    def test_invalid_inputs_never_save(self):
        for changes in [dict(totalBill='-1000'), dict(lokantaEnd='abc'), dict(lokantaStart=None),
                        dict(totalBill=float('nan')), dict(mainMeter=float('inf')),
                        dict(lokantaEnd=-5), dict(lokantaEnd=5), dict(lokantaEnd=200),
                        dict(readingDate='2026-99-99'), dict(readingDate='2026-02-30'),
                        dict(readingDate=['2026-11-06']), dict(lokantaEnd=50.0001),
                        dict(totalBill=1000.001), dict(totalBill=True), dict(mainMeter=0)]:
            with self.subTest(changes=changes):
                data = dict(self.bill, **changes)
                for route in ['/api/calculate', '/api/calculations']:
                    self.assertEqual(self.client.post(route, json=data).status_code, 400)
        self.assertEqual(self.client.get('/api/calculations').json, [])

    def test_submeter_fields_required(self):
        for key in ['lokantaStart', 'lokantaEnd', 'koltukcuStart', 'koltukcuEnd']:
            data = self.bill.copy()
            del data[key]
            self.assertEqual(self.client.post('/api/calculations', json=data).status_code, 400)

    def test_thousandth_precision(self):
        data = dict(self.bill, mainMeter='878.350', lokantaStart='24883.827',
                    lokantaEnd='25410.027', koltukcuStart='9745.629', koltukcuEnd='9850.629')
        result = self.client.post('/api/calculate', json=data)
        self.assertEqual(result.status_code, 200)
        self.assertEqual([s['consumption'] for s in result.json['shops']], [526.2, 105, 247.15])

    def test_cents_sum_and_nonnegative(self):
        for total in [0.01, 0.03, 1, 5800.51]:
            result = self.client.post('/api/calculate', json=dict(
                self.bill, totalBill=total, mainMeter=3, lokantaStart=0,
                lokantaEnd=1.5, koltukcuStart=0, koltukcuEnd=1.5)).json
            amounts = [Decimal(str(s['amount'])) for s in result['shops']]
            self.assertEqual(sum(amounts), Decimal(str(total)))
            self.assertTrue(all(x >= 0 for x in amounts))

    def test_duplicate_retry_returns_original(self):
        first = self.client.post('/api/calculations', json=self.bill)
        second = self.client.post('/api/calculations', json=self.bill)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json['id'], second.json['id'])
        self.assertTrue(second.json['duplicate'])
        self.assertEqual(len(self.client.get('/api/calculations').json), 1)

    def test_concurrent_duplicate_retry(self):
        def save(_):
            with module.app.test_client() as client:
                return client.post('/api/calculations', json=self.bill).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(save, range(4)))
        self.assertEqual(sorted(statuses), [200, 200, 200, 201])
        self.assertEqual(len(self.client.get('/api/calculations').json), 1)

    def test_readings_order_by_period_not_insert(self):
        self.client.post('/api/calculations', json=self.bill)
        self.client.post('/api/calculations', json=dict(self.bill, readingDate='2026-01-01', lokantaEnd=20))
        self.assertEqual(self.client.get('/api/last-readings').json['lokantaEnd'], 50)
        self.assertEqual(self.client.get('/api/calculations').json[0]['reading_date'], '2026-11-06')

    def test_grayscale_and_cmyk_marker_scan(self):
        for mode in ['L', '1', 'CMYK', 'RGB', 'RGBA']:
            self.assertIsNone(module.find_blue_marker_region(Image.new(mode, (20, 20))))

    def test_grayscale_upload_ocr(self):
        buffer = io.BytesIO()
        Image.new('L', (50, 50), 255).save(buffer, 'PNG')
        with patch('pytesseract.image_to_string', return_value='Fatura Tutarı: 5800.51 TL\nTek Zamanlı 4201.919 5080.269 878.350') as ocr:
            response = self.client.post('/api/upload', data={'file': (io.BytesIO(buffer.getvalue()), 'fatura.png')})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['mainMeter'], 878.35)
            self.assertEqual(response.json['totalBill'], 5800.51)
            self.assertEqual(ocr.call_args.args[0].mode, 'RGB')
            self.assertEqual(ocr.call_args.kwargs['timeout'], 60)

    def test_malformed_documents_json_error(self):
        for filename in ['bad.png', 'bad.pdf']:
            response = self.client.post('/api/upload', data={'file': (io.BytesIO(b'invalid document'), filename)})
            self.assertEqual(response.status_code, 422)
            self.assertIn('error', response.json)

    def test_upload_limit_json(self):
        with patch.dict(module.app.config, MAX_CONTENT_LENGTH=100):
            response = self.client.post('/api/upload', data={'file': (io.BytesIO(b'x' * 200), 'large.png')})
            self.assertEqual(response.status_code, 413)
            self.assertIn('16 MB', response.json['error'])

    def test_bad_json(self):
        for route in ['/api/calculate', '/api/calculations']:
            self.assertEqual(self.client.post(route, data='bad', content_type='application/json').status_code, 400)

    def test_legacy_schema_migration_preserves_rows(self):
        import sqlite3
        old = os.path.join(self.temp.name, 'legacy.db')
        with closing(sqlite3.connect(old)) as db:
            db.execute('CREATE TABLE calculations (id INTEGER PRIMARY KEY, created_at TEXT)')
            db.execute("INSERT INTO calculations VALUES (1, '2026-01-01 00:00:00')")
            db.commit()
        with patch.object(module, 'DB_PATH', old):
            module.init_db()
            with closing(module.get_db()) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM calculations').fetchone()[0], 1)
                self.assertIn('reading_date', [r[1] for r in db.execute('PRAGMA table_info(calculations)')])


if __name__ == '__main__':
    unittest.main()
