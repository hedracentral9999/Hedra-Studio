#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

REQUIRED_SENTENCES = [1, 3, 3, 3, 4, 3]
DEMO_TERMS = [
    "AI Liquidity BTC Finance Test",
    "BTC BỊ BỎ LẠI",
    "BTC rút vốn",
    "1.42B",
    "2.52T, BTC, HORMUZ",
    "ETH BTC",
    "SOL BTC",
    "BTC BTC",
    "Placeholder source visual",
]


def normalize(text: str) -> str:
    text = html.unescape(text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-zA-Z0-9]+", " ", text.replace("đ", "d").replace("Đ", "D")).lower().strip()


def split_sentences(text: str) -> list[str]:
    protected = re.sub(r"(\d)\.(\d)", r"\1<DECIMAL>\2", text)
    return [
        item.replace("<DECIMAL>", ".").strip()
        for item in re.findall(r"[^.!?]+[.!?]+", protected)
        if item.strip()
    ]


def extract_slide_scripts(app_text: str) -> list[str]:
    match = re.search(r"const slideScripts = (\[[\s\S]*?\]);", app_text)
    if not match:
        raise ValueError("Missing slideScripts array in app.js")
    return json.loads(match.group(1))


def flatten_visuals(value) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(flatten_visuals(item))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(flatten_visuals(item))
        return out
    text = str(value or "").strip()
    return [text] if len(text) >= 4 else []


def visual_coverage(script: dict, html_text: str) -> dict:
    html_words = set(normalize(html_text).split())
    values = []
    for scene in script.get("scenes", []):
        values.extend(flatten_visuals(scene.get("visual", {})))
    meaningful = []
    for value in values:
        norm = normalize(value)
        words = [word for word in norm.split() if len(word) >= 3]
        if not words:
            continue
        meaningful.append((value, words))
    matched = []
    missing = []
    for value, words in meaningful:
        overlap = len(set(words) & html_words)
        needed = min(3, max(1, len(set(words)) // 2))
        if overlap >= needed:
            matched.append(value)
        else:
            missing.append(value)
    total = len(meaningful)
    score = round(len(matched) / total, 3) if total else 1.0
    return {
        "score": score,
        "matched": len(matched),
        "total": total,
        "missing": missing[:12],
    }


def token_overlap(left: str, right: str) -> float:
    left_words = {word for word in normalize(left).split() if len(word) >= 3}
    right_words = {word for word in normalize(right).split() if len(word) >= 3}
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / min(len(left_words), len(right_words))


def semantic_alignment(script: dict) -> dict:
    checks: list[dict] = []
    rules = {
        2: [(1, "highlight"), (2, "callout")],
        3: [(0, "left"), (1, "bullet1"), (2, "bullet2")],
        4: [(1, "risk1"), (2, "risk2"), (3, "risk3")],
        5: [(0, "focus"), (1, "verdict")],
    }
    for scene_index, pairs in rules.items():
        scene = script.get("scenes", [])[scene_index]
        sentences = split_sentences(scene.get("voiceText", ""))
        visual = scene.get("visual", {})
        for sentence_index, field in pairs:
            sentence = sentences[sentence_index] if sentence_index < len(sentences) else ""
            fields = field if isinstance(field, tuple) else (field,)
            scored = [(name, token_overlap(sentence, visual.get(name, ""))) for name in fields]
            best_field, score = max(scored, key=lambda item: item[1])
            checks.append({
                "scene": scene_index + 1,
                "sentence": sentence_index + 1,
                "field": best_field if len(fields) == 1 else "/".join(fields),
                "score": round(score, 3),
                "ok": score >= 0.34,
            })
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "checks": checks}


def run_qa(project_dir: Path) -> tuple[bool, dict]:
    script_path = project_dir / "script.json"
    script_text_path = project_dir / "script-90s.txt"
    app_path = project_dir / "app.js"
    html_path = project_dir / "index.html"

    script = json.loads(script_path.read_text(encoding="utf-8"))
    script_lines = [line.strip() for line in script_text_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    app_scripts = extract_slide_scripts(app_path.read_text(encoding="utf-8"))
    html_text = html_path.read_text(encoding="utf-8")

    checks = []
    checks.append({"name": "scene_count", "ok": len(script.get("scenes", [])) == 6, "value": len(script.get("scenes", []))})
    checks.append({"name": "script_txt_matches_app_js", "ok": script_lines == app_scripts})
    for idx, expected in enumerate(REQUIRED_SENTENCES):
        text = script.get("scenes", [{}])[idx].get("voiceText", "") if idx < len(script.get("scenes", [])) else ""
        actual = len(split_sentences(text))
        checks.append({"name": f"slide_{idx + 1}_sentence_count", "ok": actual == expected, "expected": expected, "actual": actual})

    leftover_tokens = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", html_text)))
    checks.append({"name": "no_unbound_tokens", "ok": not leftover_tokens, "leftover_tokens": leftover_tokens})

    demo_hits = [term for term in DEMO_TERMS if term in html_text]
    checks.append({"name": "no_demo_placeholders", "ok": not demo_hits, "demo_hits": demo_hits})

    coverage = visual_coverage(script, html_text)
    checks.append({"name": "visual_coverage", "ok": coverage["score"] >= 0.72, **coverage})

    alignment = semantic_alignment(script)
    checks.append({"name": "semantic_alignment", **alignment})

    ok = all(item["ok"] for item in checks)
    report = {"ok": ok, "project_dir": str(project_dir), "checks": checks}
    return ok, report


def main() -> None:
    parser = argparse.ArgumentParser(description="QA gate for generated finance Escbase projects.")
    parser.add_argument("project_dir")
    args = parser.parse_args()
    project_dir = Path(args.project_dir).resolve()
    ok, report = run_qa(project_dir)
    report_path = project_dir / "qa-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
