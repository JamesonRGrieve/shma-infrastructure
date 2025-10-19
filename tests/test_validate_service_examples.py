from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from ci import validate_schema


class ValidateServiceExamplesTests(unittest.TestCase):
    def test_invalid_service_definition_reports_error(self) -> None:
        schema_result = validate_schema.validate_schema(
            Path("schemas/service.schema.yml")
        )
        self.assertIsInstance(schema_result, tuple)
        _, validator = schema_result

        with TemporaryDirectory() as tmpdir:
            examples_dir = Path(tmpdir)
            invalid_example = examples_dir / "invalid.yml"
            invalid_example.write_text("service_id: 123\n")

            buffer = io.StringIO()
            with redirect_stderr(buffer):
                result = validate_schema.validate_examples(validator, examples_dir)

        self.assertEqual(result, 1)
        self.assertIn("invalid.yml", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
