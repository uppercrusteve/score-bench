import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bench  # noqa: E402


def write(d, rel, text):
    p = os.path.join(d, rel.replace("/", os.sep))
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


GOLD = {"kept": [{"fullName": "a/keep1"}, {"fullName": "a/keep2"}],
        "dropped": [{"fullName": "b/drop1"}]}

# 假打分器：分数写在文件里的表里；顺便从沙箱 ROOT 读 seen，证明隔离生效。
SCORER_TMPL = (
    "import json, os, sys\n"
    "ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
    "TABLE = json.loads(r'''{table}''')\n"
    'seen = json.load(open(os.path.join(ROOT, "state", "seen.json"), encoding="utf-8"))\n'
    "rows = json.load(open(sys.argv[1], encoding='utf-8'))\n"
    "out = [{{'fullName': r['fullName'], 'score': TABLE.get(r['fullName'], 0) + seen.get('bonus', 0)}}\n"
    "       for r in rows]\n"
    "json.dump({{'rows': out}}, open(sys.argv[2], 'w', encoding='utf-8'))\n"
    "print('ok')\n"
)

RAW = [{"fullName": "a/keep1"}, {"fullName": "a/keep2"}, {"fullName": "b/drop1"}]


class Tmp(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="bench-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d, ignore_errors=True))

    def scorer(self, table):
        return write(self.d, "fake_score.py", SCORER_TMPL.format(table=json.dumps(table)))


class TestMath(Tmp):
    def test_perfect_agreement(self):
        m = bench.evaluate({"a/keep1": 3, "a/keep2": 2, "b/drop1": 1}, GOLD, top=2)
        self.assertEqual(m["agreement"], 1.0)
        self.assertEqual(m["invasion"], 0)
        self.assertEqual(m["precision_at_k"], 1.0)

    def test_one_inversion(self):
        m = bench.evaluate({"a/keep1": 3, "a/keep2": 1, "b/drop1": 2}, GOLD, top=2)
        self.assertEqual(m["agreement"], 0.5)    # 2 对里 1 对正确
        self.assertEqual(m["invasion"], 1)       # drop 挤进 top2
        self.assertEqual(m["precision_at_k"], 0.5)
        self.assertEqual(m["margin"], -1)

    def test_tie_counts_half(self):
        m = bench.evaluate({"a/keep1": 2, "a/keep2": 2, "b/drop1": 2}, GOLD, top=3)
        self.assertEqual(m["agreement"], 0.5)

    def test_missing_row_raises(self):
        with self.assertRaises(RuntimeError):
            bench.evaluate({"a/keep1": 1}, GOLD, top=2)


class TestVerdict(Tmp):
    def test_fails_low_agreement(self):
        m = {"agreement": 0.5, "invasion": 0}
        self.assertEqual(len(bench.verdict(m, 0.6, 1)), 1)

    def test_fails_invasion(self):
        m = {"agreement": 1.0, "invasion": 3}
        self.assertEqual(len(bench.verdict(m, 0.6, 1)), 1)

    def test_pass(self):
        self.assertEqual(bench.verdict({"agreement": 0.8, "invasion": 1}, 0.6, 1), [])


class TestSandbox(Tmp):
    def test_root_is_isolated_and_seen_is_read(self):
        s = self.scorer({"a/keep1": 5, "a/keep2": 4, "b/drop1": 1})
        scores = bench.run_scorer(s, RAW, {"bonus": 10})
        self.assertEqual(scores["a/keep1"], 15)

    def test_missing_scorer(self):
        with self.assertRaises(RuntimeError):
            bench.run_scorer(os.path.join(self.d, "nope.py"), RAW, {})

    def test_crashing_scorer(self):
        s = write(self.d, "boom.py", "import sys\nsys.stderr.write('kaput')\nsys.exit(3)\n")
        with self.assertRaises(RuntimeError) as ctx:
            bench.run_scorer(s, RAW, {})
        self.assertIn("kaput", str(ctx.exception))

    def test_main_returns_two_on_crash(self):
        s = write(self.d, "boom2.py", "import sys\nsys.exit(1)\n")
        self.assertEqual(bench.main(["--scorer", s]), 2)


class TestFixtures(unittest.TestCase):
    def setUp(self):
        self.golden = bench.load(os.path.join(bench.FIX, "golden.json"))
        self.raw = bench.load(os.path.join(bench.FIX, "raw.json"))

    def test_fixture_shape(self):
        names = {r["fullName"] for r in self.raw}
        self.assertEqual(len(self.golden["kept"]), 25)
        self.assertEqual(len(self.golden["dropped"]), 5)
        for k in self.golden["kept"] + self.golden["dropped"]:
            self.assertIn(k["fullName"], names)
        self.assertTrue(all(d.get("reason") for d in self.golden["dropped"]))

    def test_no_overlap_between_kept_and_dropped(self):
        kept = {k["fullName"] for k in self.golden["kept"]}
        dropped = {d["fullName"] for d in self.golden["dropped"]}
        self.assertEqual(kept & dropped, set())


class TestCurrentScorer(unittest.TestCase):
    """集成：当前打分器必须过默认门限，且 --json 里 pass=True。"""

    def test_baseline_gate(self):
        self.assertEqual(bench.main([]), 0)

    def test_json_shape(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bench.main(["--json"])
        data = json.loads(buf.getvalue())
        self.assertTrue(data["pass"])
        self.assertEqual(data["pairs"], 125)
        self.assertGreaterEqual(data["agreement"], 0.6)


if __name__ == "__main__":
    unittest.main()
