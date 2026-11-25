# upstream

一条上游，MIT。只重写思路，未复制代码。

## sickn33/agentic-awesome-skills — MIT

借「catalog → 预览 → 再执行」的三段顺序：先把候选摆出来给人看，人点头之后才动。本 bench 里对应两点：

1. `golden.json` 的 `dropped` 每条必须带 `reason`，不允许只留一个光秃秃的黑名单——落选也要能回看理由，否则标尺本身不可复核。
2. 指标先打印再判卷（`--show` 时打印带 DROP 标记的完整排序），人看着排序读结论，而不是只吃一个 pass/fail。

没借鉴它的 skill 内容、安装器、目录结构。

## 一同说明

被评测的 `score.py` 属于本仓（不是上游）：它是夜班流水线的采集打分器，用 `seen` 去重、按 star/推送时间/许可加权。这里只把它当被测对象，没有修改它。为了脱离流水线也能跑，副本放在 `scorer/score.py`，默认就打它。

`fixtures/golden.json` 的正负标签来自本项目 2026-11-25 的人工 digest，不是公开数据集。
