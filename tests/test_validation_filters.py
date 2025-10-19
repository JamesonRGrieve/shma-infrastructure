import unittest

from filter_plugins.validation import ensure_defined


class EnsureDefinedFilterTests(unittest.TestCase):
    def test_returns_original_items_when_all_names_known(self) -> None:
        items = [{"name": "FOO"}, {"name": "BAR"}]
        known = ["FOO", "BAR", "BAZ"]

        result = ensure_defined(items, known, "test item")

        self.assertIs(result, items)

    def test_raises_for_unknown_names(self) -> None:
        items = [{"name": "MISSING"}]

        with self.assertRaises(ValueError) as ctx:
            ensure_defined(items, ["EXISTING"], "demo secret")

        message = str(ctx.exception)
        self.assertIn("demo secret", message)
        self.assertIn("MISSING", message)
        self.assertIn("Available: EXISTING", message)


if __name__ == "__main__":  # pragma: no cover - convenience
    unittest.main()
