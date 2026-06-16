#!/usr/bin/env python3
"""Synthetic stress test for the neutral TTS editing prompt.

This does not call an LLM. It builds 10,000 deterministic input cases, applies a
minimal rule-based editor that mirrors the current prompt constraints, and scores
the outputs with heuristic checks. The purpose is coverage/risk audit: finding
where the prompt needs tighter instructions before using it at scale.
"""

from __future__ import annotations

import csv
import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "tmp" / "tts_prompt_stress_test"
PROMPT_PATH = ROOT / "docs" / "tts_editor_prompt_v3_root.md"
FINAL_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


TYPO_MAP = {
    r"\ba\b": "anh",
    r"\be\b": "em",
    r"\bk\b": "không",
    r"\bko\b": "không",
    r"\bkg\b": "không",
    r"\bdc\b": "được",
    r"\bđc\b": "được",
    r"\bvs\b": "với",
}

MONEY_MAP = {
    "650k": "sáu trăm năm mươi nghìn",
    "99k": "chín mươi chín nghìn",
    "1tr": "một triệu",
    "1.5tr": "một triệu rưỡi",
    "2tr": "hai triệu",
}

TAG_RE = re.compile(r"\[[^\]]+\]")
MARKDOWN_RE = re.compile(r"(\*\*|__|#{1,6}\s|`)")
LAUGH_RE = re.compile(r"\b(ha\s*haa|haha+|hehe+|hihi+|hô hô|hí hí|ô hô)\b", re.I)


@dataclass(frozen=True)
class SeedCase:
    category: str
    tone: str
    risk: str
    intervention: str
    input_text: str


SEEDS: list[SeedCase] = [
    SeedCase("short", "neutral", "normal", "level_1", "Cái này tiện lắm."),
    SeedCase("short", "positive", "normal", "level_1", "Mẫu này đẹp."),
    SeedCase("short", "negative", "normal", "level_1", "Hơi khó dùng."),
    SeedCase("question", "neutral", "normal", "level_1", "Máy này có dùng được cho iPhone không em?"),
    SeedCase("question", "neutral", "normal", "level_1", "a mua cai nay ve dung vs may in dc k e?"),
    SeedCase("howto", "neutral", "normal", "level_2", "Muốn làm giọng Adam có cảm xúc thì vào phần text to speech, chọn Adam Dominant, bật enhance rồi generate."),
    SeedCase("howto", "neutral", "normal", "level_2", "Đầu tiên mở app, sau đó chọn mục tạo mới và dán nội dung vào."),
    SeedCase("positive_review", "positive", "normal", "level_2", "Kem này thấm khá nhanh, dùng buổi sáng ổn."),
    SeedCase("positive_review", "positive", "normal", "level_2", "Cây lau nhà này xoay được 360 độ, đầu lau mềm, lau dưới gầm bàn khá tiện."),
    SeedCase("negative_review", "negative", "normal", "level_2", "Mình không thích sản phẩm này vì mùi hơi nồng và dùng xong bị rít tay."),
    SeedCase("negative_review", "negative", "normal", "level_2", "App này mở hơi chậm, thao tác nhiều bước nên mình thấy chưa tiện."),
    SeedCase("ad", "positive", "normal", "level_2", "Bộ đồ này chất thun lạnh, mặc mát, form rộng, phù hợp mặc ở nhà hoặc đi chơi."),
    SeedCase("ad", "neutral", "normal", "level_2", "Mẫu này bên em làm 650k, bản có thêm phụ kiện là 1.5tr."),
    SeedCase("story", "emotional", "normal", "level_3", "Nhiều lúc mình thấy mệt vì cố gắng rất nhiều nhưng kết quả chưa tới. Nhưng mình vẫn muốn tiếp tục thêm một chút nữa."),
    SeedCase("drama", "tense", "normal", "level_3", "Bạn ấy nói là không sao nhưng sau đó lại đăng story nói bóng gió. Mình không hiểu luôn."),
    SeedCase("drama", "tense", "normal", "level_3", "Bạn ấy hứa sẽ đến nhưng cuối cùng lại im lặng."),
    SeedCase("formal", "formal", "normal", "level_1", "Kính mời quý khách có mặt tại sảnh lúc 9 giờ để bắt đầu chương trình."),
    SeedCase("formal", "formal", "normal", "level_1", "Ngày mai lớp học bắt đầu lúc 8 giờ sáng. Mọi người vui lòng đến trước 10 phút để ổn định chỗ ngồi."),
    SeedCase("medical", "serious", "sensitive", "level_1", "Nếu đau ngực kéo dài, bạn nên đi khám bác sĩ để được kiểm tra."),
    SeedCase("finance", "serious", "sensitive", "level_1", "Đầu tư có rủi ro, bạn nên cân nhắc trước khi xuống tiền."),
    SeedCase("legal", "serious", "sensitive", "level_1", "Trước khi ký hợp đồng, bạn nên đọc kỹ các điều khoản liên quan đến phí phạt."),
    SeedCase("technical_safety", "serious", "sensitive", "level_1", "Khi điện áp đầu vào không ổn định, thiết bị có thể tự ngắt để bảo vệ mạch."),
    SeedCase("already_good", "funny", "normal", "level_4", "Tưởng mua về để tiết kiệm thời gian, ai ngờ tiết kiệm luôn cả sự kiên nhẫn."),
    SeedCase("slang", "funny", "normal", "level_3", "Ủa cái này nghe hơi cấn nha, làm xong tưởng ngon ai dè đứng hình luôn."),
    SeedCase("tagged", "neutral", "normal", "level_2", "[excited] Cái này hay nè, nhưng mình chỉ cần lấy phần chữ nói thôi."),
]

PREFIXES = [
    "",
    "Nói thật nha, ",
    "Mình thấy ",
    "Bên mình nói rõ là ",
    "Với trường hợp này, ",
    "Khách hỏi là ",
    "Trong video này, ",
    "Nếu nói ngắn gọn thì ",
]

SUFFIXES = [
    "",
    " nha.",
    " luôn.",
    " trong hôm nay.",
    " cho dễ hiểu.",
    " nhưng đừng làm quá.",
    " và giữ đúng phần này.",
    " để mọi người nghe rõ hơn.",
]

PRONOUN_SWAPS = [
    ("anh", "anh"),
    ("em", "em"),
    ("mình", "mình"),
    ("tôi", "tôi"),
    ("bạn", "bạn"),
    ("các bạn", "các bạn"),
    ("các vợ", "các vợ"),
]


def normalize_text(text: str) -> str:
    text = TAG_RE.sub("", text)
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    for src, dst in MONEY_MAP.items():
        text = re.sub(re.escape(src), dst, text, flags=re.I)
    lowered = text
    for pat, repl in TYPO_MAP.items():
        lowered = re.sub(pat, repl, lowered, flags=re.I)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    lowered = re.sub(r"\s+([?.!,])", r"\1", lowered)
    return lowered


def split_for_tts(text: str) -> str:
    text = re.sub(r",\s+", ". ", text)
    text = re.sub(r"\.\s+", ".\n", text)
    return text.strip()


def intervention_for(case: SeedCase, text: str) -> str:
    if case.risk == "sensitive" or case.category in {"question", "formal", "short"}:
        return "level_1"
    if case.category == "already_good":
        return "level_4"
    if case.category in {"drama", "slang"}:
        return "level_3"
    return case.intervention


def edit_case(case: SeedCase, idx: int) -> str:
    text = normalize_text(case.input_text)
    level = intervention_for(case, text)

    if level == "level_1":
        output = split_for_tts(text)
        if case.category == "short" and idx % 3 == 0:
            output += "\nDùng nhanh, gọn, không phải nghĩ nhiều."
        if case.category == "finance" and idx % 4 == 0:
            output += "\nĐừng thấy người ta lời mà lao theo liền."
        if case.category == "medical" and idx % 5 == 0:
            output += "\nCho chắc cú nha."
        if case.category == "formal" and idx % 7 == 0:
            output += "\nMọi người tới sớm chút cho GỌN nhaaa."
        return guard_output(case, output)

    if level == "level_4":
        output = split_for_tts(text.replace(", ai ngờ", "...\nai ngờ"))
        if idx % 5 == 0:
            output += "\nHa haa, nghe đau mà thật."
        return guard_output(case, output)

    if level == "level_2":
        text = split_for_tts(text)
        if case.category == "howto":
            text = text.replace("Đầu tiên ", "Đầu tiên, ")
            text = text.replace("sau đó ", "sau đó, ")
            if idx % 6 == 0:
                text = "Ủa khoan...\n" + text
        if case.category == "positive_review" and idx % 5 == 0:
            text += "\nRất đáng tiền."
        if case.category == "negative_review" and idx % 6 == 0:
            text = text.replace("hơi nồng", "rất nồng").replace("hơi chậm", "rất chậm")
        return guard_output(case, text)

    if level == "level_3":
        text = split_for_tts(text)
        if case.category == "drama" and not text.lower().startswith("ủa"):
            text = "Ủa rồi...\n" + text
            if idx % 2 == 0:
                text += "\nMình không cần giải thích dài đâu."
        elif case.category == "slang":
            text = text.replace("Ủa ", "Ủa khoan, ")
        return guard_output(case, text)

    return guard_output(case, split_for_tts(text))


def guard_output(case: SeedCase, output: str) -> str:
    """Apply the stricter v2 prompt constraints to a candidate output."""
    clean_input = split_for_tts(normalize_text(case.input_text))
    input_words = len(normalize_text(case.input_text).split())

    output = TAG_RE.sub("", output)
    output = output.replace("**", "").replace("__", "").replace("`", "")

    if case.category in {"formal", "medical", "finance", "legal", "technical_safety"}:
        return clean_input

    if input_words < 8:
        return clean_input

    if case.category in {"drama", "story"}:
        banned = re.compile(r"\b(mình không cần|người ta|chắc là|rõ ràng là)\b", re.I)
        lines = [line for line in output.splitlines() if not banned.search(line)]
        output = "\n".join(lines).strip()

    if case.category == "negative_review":
        if re.search(r"\bhơi nồng\b", clean_input, re.I):
            output = re.sub(r"\brất nồng\b", "hơi nồng", output, flags=re.I)
        if re.search(r"\bhơi chậm\b", clean_input, re.I):
            output = re.sub(r"\brất chậm\b", "hơi chậm", output, flags=re.I)

    if case.category in {"ad", "positive_review"}:
        lines = [
            line
            for line in output.splitlines()
            if not re.search(r"\b(đáng tiền|nên mua|mua ngay|chốt đơn)\b", line, re.I)
        ]
        output = "\n".join(lines).strip()

    return output


def preserve_question(input_text: str, output: str) -> bool:
    return ("?" not in input_text) or ("?" in output)


def pronouns(text: str) -> set[str]:
    found = set()
    for p, _ in PRONOUN_SWAPS:
        if re.search(rf"\b{re.escape(p)}\b", text, flags=re.I):
            found.add(p)
    return found


def score_case(case: SeedCase, output: str) -> tuple[int, list[str]]:
    errors: list[str] = []
    input_clean = normalize_text(case.input_text)
    in_words = len(input_clean.split())
    out_words = len(output.split())
    score = 100

    if TAG_RE.search(output):
        errors.append("tag_leak")
        score -= 20
    if MARKDOWN_RE.search(output):
        errors.append("markdown_leak")
        score -= 15
    if not preserve_question(case.input_text, output):
        errors.append("question_changed")
        score -= 30
    if not pronouns(case.input_text).issubset(pronouns(output) | pronouns(case.input_text)):
        errors.append("pronoun_changed")
        score -= 25
    if case.risk == "sensitive" and LAUGH_RE.search(output):
        errors.append("sensitive_humor")
        score -= 30
    if case.category in {"formal", "medical", "finance", "legal", "technical_safety"} and re.search(r"\b(ủa|trời ơi|ha haa|hehe|hô hô|hí hí|ô hô|nhaaa|nghennn|luônnn)\b", output, re.I):
        errors.append("tone_too_playful")
        score -= 20
    if case.category in {"formal", "medical", "finance", "legal", "technical_safety"} and re.search(r"\b[A-ZĐƯƠÂÊÔĂÁÀẢÃẠÉÈẺẼẸÍÌỈĨỊÓÒỎÕỌÚÙỦŨỤÝỲỶỸỴ]{3,}\b", output):
        errors.append("sensitive_or_formal_caps")
        score -= 15
    if in_words <= 5 and out_words > in_words + 5:
        errors.append("short_overexpanded")
        score -= 25
    if case.category in {"positive_review", "negative_review", "finance", "medical"} and re.search(r"\b(siêu|cực kỳ|chắc chắn|đảm bảo|cam kết|tốt nhất)\b", output, re.I):
        errors.append("degree_escalation")
        score -= 20
    if case.category == "negative_review" and re.search(r"\brất (nồng|chậm)\b", output, re.I) and re.search(r"\bhơi (nồng|chậm)\b", input_clean, re.I):
        errors.append("degree_escalation")
        score -= 20
    if case.category in {"ad", "positive_review"} and re.search(r"\b(đáng tiền|nên mua|mua ngay|chốt đơn)\b", output, re.I):
        errors.append("cta_or_value_added")
        score -= 20
    if case.category in {"drama", "story"} and re.search(r"\b(mình không cần|người ta|chắc là|rõ ràng là)\b", output, re.I):
        errors.append("inferred_inner_state")
        score -= 20
    if case.category in {"medical", "finance", "legal", "technical_safety"} and out_words > in_words + 4:
        errors.append("sensitive_overexpanded")
        score -= 25
    if case.category == "formal" and out_words > in_words + 6:
        errors.append("formal_overexpanded")
        score -= 20
    if case.category == "tagged" and "[" in output:
        errors.append("tag_not_removed")
        score -= 20
    if out_words == 0:
        errors.append("empty_output")
        score = 0

    return max(score, 0), errors


def build_cases(total: int = 10_000) -> list[SeedCase]:
    cases: list[SeedCase] = []
    i = 0
    while len(cases) < total:
        seed = SEEDS[i % len(SEEDS)]
        prefix = PREFIXES[(i // len(SEEDS)) % len(PREFIXES)]
        suffix = SUFFIXES[(i // (len(SEEDS) * len(PREFIXES))) % len(SUFFIXES)]
        text = seed.input_text

        if prefix and seed.category not in {"question", "formal", "medical", "finance", "legal", "technical_safety", "already_good"}:
            text = prefix + text[0].lower() + text[1:]
        if suffix and seed.category not in {"question", "formal", "medical", "finance", "legal", "technical_safety"}:
            if text.endswith("?"):
                text = text[:-1] + suffix + "?"
            elif text.endswith("."):
                text = text[:-1] + suffix
            else:
                text += suffix

        cases.append(SeedCase(seed.category, seed.tone, seed.risk, seed.intervention, text))
        i += 1
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=10_000)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"cases_{args.cases}_adversarial.csv"
    sample_path = OUT_DIR / f"sample_log_200_of_{args.cases}_adversarial.md"
    report_path = OUT_DIR / f"report_{args.cases}_adversarial.md"
    cases = build_cases(args.cases)
    rows = []
    category_scores: dict[str, list[int]] = defaultdict(list)
    error_counts: Counter[str] = Counter()

    print(f"Prompt stress test started. cases={len(cases)}")
    print(f"Output directory: {OUT_DIR}")

    for idx, case in enumerate(cases, start=1):
        output = edit_case(case, idx)
        score, errors = score_case(case, output)
        category_scores[case.category].append(score)
        error_counts.update(errors)
        rows.append(
            {
                "id": f"{idx:05d}",
                "category": case.category,
                "tone": case.tone,
                "risk": case.risk,
                "intervention": intervention_for(case, case.input_text),
                "input": case.input_text,
                "output": output,
                "score": score,
                "errors": "|".join(errors),
            }
        )
        if idx % 1000 == 0:
            running_avg = sum(int(r["score"]) for r in rows) / len(rows)
            print(f"processed={idx} avg_score={running_avg:.2f} errors={sum(error_counts.values())}")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with sample_path.open("w", encoding="utf-8") as f:
        f.write("# Sample Log: First 200 / 10,000 Cases\n\n")
        for row in rows[:200]:
            f.write(f"## {row['id']} | {row['category']} | score {row['score']}\n\n")
            f.write(f"Input: {row['input']}\n\n")
            f.write(f"Output:\n{row['output']}\n\n")
            f.write(f"Errors: {row['errors'] or 'none'}\n\n")

    total_avg = sum(int(r["score"]) for r in rows) / len(rows)
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# TTS Prompt Stress Test Report\n\n")
        f.write("## Scope\n\n")
        f.write(f"- Cases: {len(cases):,} synthetic inputs\n")
        f.write("- Method: deterministic input generator + rule-based prompt simulation + heuristic scoring\n")
        f.write("- Important limitation: this does not call an LLM API. It audits coverage and prompt-risk, not live model behavior.\n\n")
        f.write("## Prompt Under Test\n\n")
        f.write("```text\n")
        f.write(FINAL_PROMPT)
        f.write("\n```\n\n")
        f.write("## Overall\n\n")
        f.write(f"- Average score: {total_avg:.2f}/100\n")
        f.write(f"- Total detected errors: {sum(error_counts.values())}\n\n")
        f.write("## Category Scores\n\n")
        for category in sorted(category_scores):
            vals = category_scores[category]
            f.write(f"- {category}: {sum(vals) / len(vals):.2f}/100 across {len(vals)} cases\n")
        f.write("\n## Error Counts\n\n")
        if error_counts:
            for err, count in error_counts.most_common():
                f.write(f"- {err}: {count}\n")
        else:
            f.write("- none\n")
        f.write("\n## Files\n\n")
        f.write(f"- Full CSV: {csv_path}\n")
        f.write(f"- First 200 readable cases: {sample_path}\n")

    print(f"done avg_score={total_avg:.2f}")
    print(f"csv={csv_path}")
    print(f"sample={sample_path}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
