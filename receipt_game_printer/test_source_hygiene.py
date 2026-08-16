from __future__ import annotations

from pathlib import Path
import unittest

PROJECT_DIR = Path(__file__).resolve().parent
FORBIDDEN_MARKERS = ("`" * 3 + "python", "`" * 3, "<" * 7, "=" * 7, ">" * 7)


class SourceHygieneTests(unittest.TestCase):
    def test_template_editor_starts_with_python_code(self):
        template_editor = PROJECT_DIR / "template_editor.py"
        first_line = template_editor.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first_line, "from __future__ import annotations")

    def test_python_sources_do_not_contain_markdown_fences_or_conflict_markers(self):
        offenders: list[str] = []
        for path in PROJECT_DIR.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_MARKERS:
                if marker in text:
                    offenders.append(f"{path.relative_to(PROJECT_DIR)} contains {marker!r}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
