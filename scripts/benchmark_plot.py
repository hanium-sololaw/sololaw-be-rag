"""실험 A 결과 그래프·표 — benchmark_agents 결과 폴더를 읽어 chart.png 와 summary.md 를 만든다.

matplotlib 은 이 스크립트에만 필요해 의존성에 넣지 않는다.
실행: uv run --with matplotlib python -m scripts.benchmark_plot <결과 폴더>
"""

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"single": "#2a78d6", "multi": "#eb6834"}  # 범주 1·2번 (색약 검증 통과)
LABELS = {"single": "단일 호출", "multi": "Multi-Agent"}
INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a64", "#e6e5e0", "#fcfcfb"
RATES = [
    ("completed_pct", "정상 완료"),
    ("pass_all_pct", "전체 검사 통과"),
    ("values_pct", "입력값 보존"),
    ("composition_pct", "청구 구성(소장)"),
    ("no_hallucination_pct", "미제공 사건번호 없음"),
    ("no_irrelevant_pct", "무관 판례 미인용"),
]


def _num(v):
    return None if v in ("", None) else float(v)


def _bars(ax, groups, values, fmt, ymax=None):
    width = 0.38
    for k, system in enumerate(("single", "multi")):
        xs = [i + (k - 0.5) * width for i in range(len(groups))]
        ys = [values[system][i] or 0 for i in range(len(groups))]
        ax.bar(
            xs,
            ys,
            width,
            color=COLORS[system],
            edgecolor=SURFACE,
            linewidth=2,
            label=LABELS[system],
        )
        for x, y, raw in zip(xs, ys, values[system]):
            ax.text(
                x,
                y,
                "—" if raw is None else fmt(raw),
                ha="center",
                va="bottom",
                fontsize=8,
                color=INK,
            )
    ax.set_xticks(range(len(groups)), groups, fontsize=8, color=INK)
    ax.tick_params(axis="y", colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    if ymax:
        ax.set_ylim(0, ymax)


def main(folder: str):
    out = Path(folder)
    summary = {
        r["system"]: r
        for r in csv.DictReader((out / "summary.csv").read_text().splitlines())
    }
    meta = json.loads((out / "meta.json").read_text())
    plt.rcParams["font.family"] = [
        "AppleGothic",
        "Malgun Gothic",
        "NanumGothic",
        "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(13, 4.2),
        gridspec_kw={"width_ratios": [3.2, 1, 1]},
        facecolor=SURFACE,
    )
    for ax in axes:
        ax.set_facecolor(SURFACE)

    _bars(
        axes[0],
        [lbl for _, lbl in RATES],
        {s: [_num(summary[s][k]) for k, _ in RATES] for s in summary},
        lambda v: f"{v:.0f}%",
        ymax=112,
    )
    axes[0].set_title("자동 검사 통과율 (%)", loc="left", fontsize=10, color=INK)
    axes[0].tick_params(axis="x", labelrotation=15)

    _bars(
        axes[1],
        ["중앙값"],
        {s: [_num(summary[s]["seconds_median"])] for s in summary},
        lambda v: f"{v:.1f}s",
    )
    axes[1].set_title("처리 시간 (초)", loc="left", fontsize=10, color=INK)

    _bars(
        axes[2],
        ["평균"],
        {s: [_num(summary[s]["cost_usd_mean"])] for s in summary},
        lambda v: f"${v:.4f}",
    )
    axes[2].set_title("실행당 비용 (USD)", loc="left", fontsize=10, color=INK)

    axes[0].legend(
        loc="upper left",
        bbox_to_anchor=(0, 1.22),
        ncol=2,
        frameon=False,
        fontsize=9,
        labelcolor=INK,
    )
    runs = summary["single"]["runs"]
    fig.text(
        0.01,
        0.01,
        f"실험 A · 시나리오 {meta['scenarios']}개(보류 {meta['holdout']}) × {meta['reps']}회, "
        f"방식별 {runs}회 · 같은 입력·판례·프롬프트 · {meta['model']} · {meta['started'][:10]} · "
        f"커밋 {meta['commit']}. 실패한 실행은 모든 검사 불통과로 집계. 자동 검사는 형식·입력값·청구 구성·"
        "인용 일치만 보며 전문가 품질 평가가 아니다.",
        fontsize=7,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    fig.savefig(out / "chart.png", dpi=200, facecolor=SURFACE)

    rows = [
        (
            "방식",
            "실행 수",
            *[lbl for _, lbl in RATES],
            "재작성(%)",
            "시간 중앙값(초)",
            "시간 p90(초)",
            "LLM 호출(평균)",
            "토큰(평균)",
            "비용(USD, 평균)",
        )
    ]
    for s in ("single", "multi"):
        r = summary[s]
        rows.append(
            (
                LABELS[s],
                r["runs"],
                *[r[k] or "—" for k, _ in RATES],
                r["rewrite_pct"],
                r["seconds_median"],
                r["seconds_p90"],
                r["llm_calls_mean"],
                r["tokens_mean"],
                r["cost_usd_mean"],
            )
        )
    md = ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    md.insert(1, "|" + "---|" * len(rows[0]))
    (out / "summary.md").write_text(
        f"# 실험 A 결과 ({meta['started']})\n\n"
        + "\n".join(md)
        + "\n\n- 통과율은 실패한 실행을 포함한 전체 실행 기준. 청구 구성은 소장 시나리오만.\n"
        + "- '미제공 사건번호 없음'은 Multi-Agent 내부 검증과 같은 정의라 독립 검증이 아니다.\n"
        + f"- 조건: {json.dumps(meta, ensure_ascii=False)}\n"
    )
    print(out / "chart.png", out / "summary.md")


if __name__ == "__main__":
    main(sys.argv[1])
