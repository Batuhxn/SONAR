import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sonar_a0.cli import main, verify
from sonar_a0.models import Result, Status


class CliTests(unittest.TestCase):
    def test_verify_stops_blocked_supplier_and_is_not_pass(self):
        adapter = Mock(name="adapter")
        adapter.name = "direnc"
        adapter.client.evidence = []
        adapter.search.return_value = Result("direnc","search","TEST",Status.RATE_LIMITED,message="retry later")
        with tempfile.TemporaryDirectory() as tmp:
            cases = Path(tmp)/"cases.json"
            output = Path(tmp)/"result.json"
            cases.write_text(json.dumps([{"id":"first","supplier":"direnc","operation":"search","mpn":"TEST"},{"id":"second","supplier":"direnc","operation":"search","mpn":"TEST2"}]),encoding="utf-8")
            with patch("sonar_a0.cli.ADAPTERS",{"direnc":Mock(return_value=adapter)}):
                self.assertEqual(verify(cases,output),0)
            result=json.loads(output.read_text())
            self.assertTrue(result["execution_completed"])
            self.assertFalse(result["integration_pass_claimed"])
            self.assertEqual(result["cases"][1]["status"],"skipped")
            adapter.search.assert_called_once()

    def test_search_partial_exit_code(self):
        adapter=Mock()
        adapter.search.return_value=Result("direnc","search","TEST",Status.PARTIAL)
        with patch("sonar_a0.cli.ADAPTERS",{"direnc":Mock(return_value=adapter)}):
            self.assertEqual(main(["search","direnc","TEST"]),2)

    def test_invalid_input_file_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["verify","--cases",str(Path(tmp)/"absent.json")]),1)
