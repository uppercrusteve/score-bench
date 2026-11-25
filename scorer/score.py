#!/usr/bin/env python
"""对采集结果做确定性打分分层。判断全部来自可解释的信号，不含 LLM 主观分。

用法: python lib/score.py radar/YYYY-MM-DD/raw.json radar/YYYY-MM-DD/scored.json
"""
import json, math, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN = os.path.join(ROOT, "state", "seen.json")
KW = ("skill", "skills", "skill.md", "agent", "claude", "codex", "cursor", "mcp",
      "prompt", "workflow", "plugin", "registry", "marketplace", "eval", "bench", "lint")
BAD_LIST = ("awesome", "curated list", "collection of links", "link list")
PERMISSIVE = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense", "0bsd"}


def days_since(iso):
    if not iso:
        return 9999
    try:
        t = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return 9999
    return (datetime.datetime.utcnow() - t).days


def main():
    raw, out = sys.argv[1], sys.argv[2]
    seen = {}
    if os.path.exists(SEEN):
        try:
            seen = json.load(open(SEEN, encoding="utf-8"))
        except Exception:
            seen = {}

    rows = []
    for r in json.load(open(raw, encoding="utf-8")):
        m = r.get("meta") or {}
        fn = r["fullName"]
        name_desc = (fn + " " + (m.get("description") or "")).lower()
        stars = m.get("stargazersCount") or 0
        forks = m.get("forksCount") or 0
        lic = (m.get("license") or "none").lower()
        dpush = days_since(m.get("pushedAt"))
        dcreate = days_since(m.get("createdAt"))
        reasons, score = [], 0.0

        score += min(30.0, 6 * math.log10(stars + 1))
        if dpush <= 3: score += 12; reasons.append("push<=3d")
        elif dpush <= 14: score += 8; reasons.append("push<=14d")
        elif dpush <= 60: score += 4; reasons.append("push<=60d")
        else: reasons.append(f"stale{dpush}d")
        if dcreate <= 14: score += 8; reasons.append("new")
        elif dcreate <= 60: score += 4
        hits = sum(1 for k in KW if k in name_desc)
        score += min(20, hits * 4)
        if hits: reasons.append(f"kw{hits}")
        extra_via = max(0, len(r.get("via", [])) - 1)
        score += min(9, extra_via * 3)
        if extra_via: reasons.append(f"multi{len(r['via'])}")
        if lic in PERMISSIVE: score += 6; reasons.append("permissive")
        elif lic == "none": score -= 4; reasons.append("no-license")
        elif "gpl" in lic: score -= 1; reasons.append("gpl")
        if m.get("isArchived"): score -= 15; reasons.append("archived")
        if stars and forks / max(stars, 1) > 0.4: score -= 3; reasons.append("forky")
        if (m.get("size") or 0) > 200000: score -= 2; reasons.append("huge")
        if any(b in name_desc for b in BAD_LIST): score -= 6; reasons.append("linklist")

        s = seen.get(fn)
        if s:
            prev = s.get("stars", 0)
            if stars <= prev * 1.2:
                score -= 10; reasons.append("seen")
            else:
                reasons.append(f"regrow{prev}->{stars}")

        tier = "A" if score >= 55 else "B" if score >= 35 else "C"
        rows.append({"fullName": fn, "score": round(score, 1), "tier": tier,
                     "reasons": reasons, "stars": stars, "license": lic,
                     "pushedDays": dpush, "createdDays": dcreate,
                     "url": m.get("url"), "desc": m.get("description"),
                     "language": m.get("language")})

    rows.sort(key=lambda x: -x["score"])
    json.dump({"generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
               "counts": {t: sum(1 for r in rows if r["tier"] == t) for t in "ABC"},
               "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    c = {t: sum(1 for r in rows if r["tier"] == t) for t in "ABC"}
    print("scored %d -> A=%d B=%d C=%d" % (len(rows), c["A"], c["B"], c["C"]))


if __name__ == "__main__":
    main()
