#!/usr/bin/env python
"""score-bench: 把「人已经挑过的」和「人已经扔掉的」放回同一条排序里对拍。

本来打分器只能靠手感调参：改一个权重，翻眼看前十。这里把它变成可复跑的审计——
同一个 fixture、同一份 seen、固定的指标和门限，改动前后直接比数字。

用法:
    python bench.py [--scorer scorer/score.py] [--top 10]
                    [--min-agreement 0.60] [--max-invasion 1] [--json] [--show]

默认门限贴着当前基线取（2026-11-25 实测 agreement=0.656、invasion=1），
作用是「别回退」而不是「已经很好了」；想收紧就调高 --min-agreement。

指标:
    agreement    所有 kept×dropped 配对里，kept 分数更高的比例（并列记 0.5）
    invasion     前十名里挤进了多少个 dropped
    precision@k  前 k 名里 kept 的占比
    margin       最低的 kept 减最高的 dropped

退出码: 0 过闸 / 1 不过闸 / 2 跑不起来
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
DEFAULT_SCORER = os.path.join(HERE, "scorer", "score.py")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_scorer(scorer, raw_rows, seen, timeout=120):
    """在沙箱里跑打分器：把 scorer 复制到 <tmp>/lib/ 下，让它的 ROOT 落在沙箱。"""
    scorer = os.path.abspath(scorer)
    if not os.path.exists(scorer):
        raise RuntimeError(f"找不到打分器: {scorer}")
    tmp = tempfile.mkdtemp(prefix="score-bench-")
    try:
        os.makedirs(os.path.join(tmp, "lib"))
        os.makedirs(os.path.join(tmp, "state"))
        shutil.copy2(scorer, os.path.join(tmp, "lib", "score.py"))
        with open(os.path.join(tmp, "state", "seen.json"), "w", encoding="utf-8") as f:
            json.dump(seen, f)
        with open(os.path.join(tmp, "raw.json"), "w", encoding="utf-8") as f:
            json.dump(raw_rows, f, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, os.path.join("lib", "score.py"), "raw.json", "out.json"],
            cwd=tmp, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError("打分器退出 %d: %s" % (proc.returncode, (proc.stderr or "")[-400:]))
        out = load(os.path.join(tmp, "out.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {r["fullName"]: float(r["score"]) for r in out["rows"]}


def evaluate(scores, golden, top=10):
    kept = [k["fullName"] for k in golden["kept"]]
    dropped = [d["fullName"] for d in golden["dropped"]]
    missing = [n for n in kept + dropped if n not in scores]
    if missing:
        raise RuntimeError("打分结果缺 %d 条，例如 %s" % (len(missing), missing[0]))

    hits = 0.0
    for k in kept:
        for d in dropped:
            if scores[k] > scores[d]:
                hits += 1
            elif scores[k] == scores[d]:
                hits += 0.5
    pairs = len(kept) * len(dropped)
    agreement = hits / pairs if pairs else 1.0

    order = sorted(scores, key=lambda n: -scores[n])
    head = order[:top]
    invasion = sum(1 for n in head if n in set(dropped))
    precision = (top - invasion) / top if top else 0.0
    margin = min(scores[k] for k in kept) - max(scores[d] for d in dropped)
    return {
        "agreement": round(agreement, 3),
        "invasion": invasion,
        "precision_at_k": round(precision, 3),
        "margin": round(margin, 2),
        "pairs": pairs,
        "top": head,
        "kept": kept,
        "dropped": dropped,
    }


def verdict(m, min_agreement, max_invasion):
    fails = []
    if m["agreement"] < min_agreement:
        fails.append(f"agreement {m['agreement']} < {min_agreement}")
    if m["invasion"] > max_invasion:
        fails.append(f"前十混入 {m['invasion']} 个落选项 > {max_invasion}")
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description="排序对拍")
    ap.add_argument("--scorer", default=DEFAULT_SCORER)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-agreement", type=float, default=0.60)
    ap.add_argument("--max-invasion", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show", action="store_true", help="打印完整排序")
    a = ap.parse_args(argv)

    golden = load(os.path.join(FIX, "golden.json"))
    raw_rows = load(os.path.join(FIX, "raw.json"))
    seen = load(os.path.join(FIX, "seen.json"))
    try:
        scores = run_scorer(a.scorer, raw_rows, seen)
        m = evaluate(scores, golden, a.top)
    except Exception as e:  # noqa: BLE001
        print(f"跑不起来: {e}")
        return 2

    fails = verdict(m, a.min_agreement, a.max_invasion)
    if a.json:
        print(json.dumps({**m, "scorer": os.path.basename(a.scorer),
                          "fails": fails, "pass": not fails}, ensure_ascii=False, indent=1))
    else:
        print(f"scorer={os.path.basename(a.scorer)} pairs={m['pairs']}")
        print(f"agreement={m['agreement']}  invasion={m['invasion']}  "
              f"precision@{a.top}={m['precision_at_k']}  margin={m['margin']}")
        if a.show:
            dset = set(m["dropped"])
            for i, n in enumerate(sorted(scores, key=lambda n: -scores[n]), 1):
                print(f"{i:>3} {scores[n]:>7.1f} {'DROP' if n in dset else '    '} {n}")
        for f in fails:
            print("FAIL " + f)
        print("--- " + ("PASS" if not fails else "FAIL"))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
