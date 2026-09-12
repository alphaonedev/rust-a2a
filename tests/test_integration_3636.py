"""Issue #3636: protocol home must describe shipped status honestly."""
from pathlib import Path
import re
import unittest

class Integration3636(unittest.TestCase):
    def test_3636_shipped_components_measurement_open(self):
        page = (Path(__file__).resolve().parents[1] / "docs/index.html").read_text()
        self.assertIn("complete and shipped in ai-memory v1.0.0", page)
        for issue in range(3467, 3473):
            card = re.search(r'<a[^>]*issues/' + str(issue) + r'".*?</a>', page, re.S)
            self.assertIsNotNone(card)
            self.assertIn('pill done', card[0])
        card = re.search(r'<a[^>]*issues/3473"[^>]*><strong>.*?</a>', page, re.S)
        self.assertIsNotNone(card)
        self.assertIn('pill open', card[0])
        self.assertNotIn('in gate', page)

    def test_3636_integration_link(self):
        for relative in ["README.md", "docs/index.html"]:
            text = (Path(__file__).resolve().parents[1] / relative).read_text()
            self.assertIn("Integrate your agent", text)
            self.assertIn("https://alphaonedev.github.io/ai-memory-mcp/a2a-integration.html", text)

if __name__ == "__main__":
    unittest.main()
