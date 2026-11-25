# score-bench

一个打分器的排序回归台。给人已经挑过的正例和已经扔掉的负例，量出「谁压着谁」。

## 做什么

`score.py` 是采集流水线的排序器，纯信号加权、无 LLM。它一直只能靠手感调：改一个系数，翻眼看前十，觉得差不多就收工。这个 bench 把当天的真实施工结果固定下来：

- 正例 25 条 = digest 当天实际保留的
- 负例 5 条 = 当天明确扔掉的，每条带落选理由（大杂烩、绑厂商、是产品不是构件……）

同一个 fixture、同一份 `seen.json`、固定指标，改动前后数字直接对比。输出四个指标：

| 指标 | 含义 | 方向 |
|---|---|---|
| `agreement` | 125 个正负配对里，正例分更高的比例，并列记 0.5 | 越高越好 |
| `invasion` | 前十名里挤进几个负例 | 越低越好 |
| `precision@k` | 前 k 名里正例占比 | 越高越好 |
| `margin` | 最低正例分 − 最高负例分 | 正数=分得开 |

默认门限贴着 2026-11-25 的实测基线（`agreement=0.656`、`invasion=1`），所以它是**回退警报**，不是「已经很好了」的奖状。实测 `margin=-10.5`、agreement 才 0.656——前十基本对，但逐对比较大量颠倒，说明权重还糙。想收紧自己调 `--min-agreement`。

## 怎么跑

```bash
python bench.py                    # 默认跑 scorer/score.py，过闸返回 0
python bench.py --show             # 带完整排序，负例标 DROP
python bench.py --json             # 机器读
python bench.py --scorer ../other/score.py --min-agreement 0.75
python -m unittest discover -s . -t .
```

`scorer/score.py` 是随仓带的被测打分器（夜班流水线的采集打分器，未修改），装上就能跑。换别的排序器用 `--scorer` 指过去。

沙箱是硬隔离：打分器被复制进临时目录的 `lib/` 下，`seen.json` 写在临时目录的 `state/` 下，所以它按 `__file__` 推出来的 ROOT 落在沙箱里，不会读写真实 `state/seen.json`。跑完整个临时目录删掉。

退出码：`0` 过闸、`1` 不过闸、`2` 打分器根本跑不起来。三种要分清——跑不起来常常是接口变了，跟分数好坏是两回事。

换一份 fixture 就能给别的排序器用，只要 `golden.json` 有 `kept`/`dropped` 两个数组、`raw.json` 的字段和你打分器的入参对得上。

## 上游

`sickn33/agentic-awesome-skills`（MIT）的 catalog 三段式——发现、预览、再动手。这里借的是「先给人看清单再执行」的顺序：负例必须带一句落选理由，不能只有一个名单。逐条见 `upstream.md`。没搬代码。

## 许可

本目录原创部分 MIT，见 `LICENSE`。`fixtures/raw.json` 是从公开 GitHub 元数据（stargazers、license、description）抽的，不含上游源码。

## 原创

上游停在做目录让人挑，我们把人挑完的结果反过来当标尺——**从「看着前十差不多就发」到「改动让 agreement 掉到 0.65 以下就红」**：负例带理由、指标可复算、打分器在沙箱里跑，三次跑出来的数一模一样。
