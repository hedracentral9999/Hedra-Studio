#!/usr/bin/env python3
"""Utilities for subtitle timing data."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"\S+")
NORMALIZE_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)
VIETNAMESE_RE = re.compile(r"[ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.IGNORECASE)
CACHE_FILE_NAME = "subtitle-word-timing.json"
CAPTION_CONSTRAINTS_VERSION = 2


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def split_caption_chunks(text: str, max_words: int = 9, max_chars: int = 62) -> list[str]:
    return [" ".join(group).strip() for group in split_caption_token_groups(text, max_words=max_words, max_chars=max_chars)]


def split_caption_token_groups(text: str, max_words: int = 9, max_chars: int = 62) -> list[list[str]]:
    groups: list[list[str]] = []

    def append_sentence(sentence: str) -> None:
        tokens = WORD_RE.findall(sentence)
        if not tokens:
            return
        current: list[str] = []

        def flush() -> None:
            if current:
                groups.append(current.copy())
                current.clear()

        for token in tokens:
            tentative = " ".join([*current, token]).strip()
            if current and (len(current) >= max_words or len(tentative) > max_chars):
                flush()
            current.append(token)

        flush()

    for sentence in split_sentences(text) or [text]:
        append_sentence(sentence)

    if not groups and text.strip():
        groups.append(WORD_RE.findall(text.strip()))
    return [group for group in groups if group]


def normalize_token(token: str) -> str:
    lowered = unicodedata.normalize("NFC", token).strip().lower()
    cleaned = NORMALIZE_TOKEN_RE.sub("", lowered)
    return cleaned or lowered


def caption_constraints(max_lines: int = 2) -> tuple[int, int]:
    if max_lines <= 1:
        return 6, 34
    return 9, 62


def guess_whisper_language(line_items: list[dict[str, Any]]) -> str | None:
    sample = " ".join(str(item.get("text", "")) for item in line_items[:6])
    if VIETNAMESE_RE.search(sample):
        return "vi"
    return None


def line_audio_path(output_dir: Path, line_number: int) -> Path:
    return output_dir / f"line_{line_number}.mp3"


def build_script_subtitle_timing(line_items: list[dict[str, Any]], *, max_lines: int = 2) -> dict[str, Any]:
    slides = []
    captions = []
    cumulative = 0.0
    max_words, max_chars = caption_constraints(max_lines)

    for item in line_items:
        line = int(item["line"])
        text = str(item["text"])
        duration = float(item["duration"])
        original_duration = float(item.get("original_audio_duration", duration))
        sentence_chunks = []
        for sentence in split_sentences(text) or [text]:
            sentence_chunks.extend(split_caption_chunks(sentence, max_words=max_words, max_chars=max_chars))
        if not sentence_chunks:
            sentence_chunks = [text]

        weights = [max(8, len(chunk)) for chunk in sentence_chunks]
        total_weight = max(1, sum(weights))
        cursor = cumulative
        slide_captions = []

        for chunk, weight in zip(sentence_chunks, weights):
            span = max(0.35, original_duration * weight / total_weight)
            caption = {
                "slide": line,
                "start": round(cursor, 3),
                "end": round(cursor + span, 3),
                "text": chunk,
            }
            captions.append(caption)
            slide_captions.append(caption)
            cursor += span

        slides.append(
            {
                "line": line,
                "start": round(cumulative, 3),
                "duration": round(duration, 3),
                "original_audio_duration": round(original_duration, 3),
                "text": text,
                "captions": slide_captions,
            }
        )
        cumulative += duration

    return {
        "version": 1,
        "source": "script",
        "mode": "static-yellow",
        "duration": round(cumulative, 3),
        "slides": slides,
        "captions": captions,
    }


def _fresh_cache(cache_file: Path, source_files: list[Path]) -> bool:
    if not cache_file.exists():
        return False
    try:
        cache_mtime = cache_file.stat().st_mtime
    except OSError:
        return False
    for path in source_files:
        if not path.exists():
            return False
        try:
            if path.stat().st_mtime > cache_mtime:
                return False
        except OSError:
            return False
    return True


def _load_cached_karaoke(cache_file: Path, *, max_lines: int, max_words: int, max_chars: int) -> dict[str, Any] | None:
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("mode") != "karaoke-red" or not isinstance(data.get("captions"), list):
        return None
    layout = data.get("subtitle_layout")
    if not isinstance(layout, dict):
        return None
    if int(layout.get("constraints_version", 0) or 0) != CAPTION_CONSTRAINTS_VERSION:
        return None
    if int(layout.get("max_lines", 0) or 0) != int(max_lines):
        return None
    if int(layout.get("max_words", 0) or 0) != int(max_words):
        return None
    if int(layout.get("max_chars", 0) or 0) != int(max_chars):
        return None
    return data


def _load_whisper_model(model_size: str = "base"):
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError("faster-whisper is not available") from exc
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def _transcribe_line_words(model, audio_file: Path, *, language: str | None) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "word_timestamps": True,
        "vad_filter": True,
    }
    if language:
        kwargs["language"] = language
    segments, _info = model.transcribe(str(audio_file), **kwargs)
    words: list[dict[str, Any]] = []
    for segment in segments:
        for word in segment.words or []:
            if word.start is None or word.end is None:
                continue
            raw = str(word.word or "").strip()
            if not raw:
                continue
            words.append(
                {
                    "word": raw,
                    "start": float(word.start),
                    "end": float(word.end),
                }
            )
    return words


def _weights_for_tokens(tokens: list[str]) -> list[int]:
    return [max(1, len(normalize_token(token)) or len(token.strip()) or 1) for token in tokens]


def _spread_times(tokens: list[str], start: float, end: float) -> list[tuple[float, float]]:
    if not tokens:
        return []
    total_span = max(end - start, 0.06 * len(tokens))
    weights = _weights_for_tokens(tokens)
    total_weight = max(1, sum(weights))
    cursor = start
    spans: list[tuple[float, float]] = []
    for idx, weight in enumerate(weights):
        if idx == len(weights) - 1:
            token_end = start + total_span
        else:
            token_end = cursor + total_span * weight / total_weight
        spans.append((cursor, token_end))
        cursor = token_end
    return spans


def _assign_group(
    token_times: list[tuple[float, float] | None],
    script_tokens: list[str],
    start_idx: int,
    end_idx: int,
    transcript_words: list[dict[str, Any]],
) -> None:
    if start_idx >= end_idx or not transcript_words:
        return
    spans = _spread_times(script_tokens[start_idx:end_idx], float(transcript_words[0]["start"]), float(transcript_words[-1]["end"]))
    for offset, span in enumerate(spans):
        token_times[start_idx + offset] = span


def _fill_missing_times(
    token_times: list[tuple[float, float] | None],
    script_tokens: list[str],
    total_end: float,
) -> list[tuple[float, float]]:
    if not token_times:
        return []
    total_end = max(total_end, 0.06 * len(token_times))
    if all(span is None for span in token_times):
        return _spread_times(script_tokens, 0.0, total_end)

    filled = token_times[:]
    idx = 0
    while idx < len(filled):
        if filled[idx] is not None:
            idx += 1
            continue
        run_start = idx
        while idx < len(filled) and filled[idx] is None:
            idx += 1
        run_end = idx
        prev_end = filled[run_start - 1][1] if run_start > 0 and filled[run_start - 1] is not None else 0.0
        next_start = filled[run_end][0] if run_end < len(filled) and filled[run_end] is not None else total_end
        if next_start <= prev_end:
            next_start = prev_end + 0.06 * (run_end - run_start)
        spans = _spread_times(script_tokens[run_start:run_end], prev_end, next_start)
        for offset, span in enumerate(spans):
            filled[run_start + offset] = span

    resolved = [span if span is not None else (0.0, 0.06) for span in filled]
    normalized: list[tuple[float, float]] = []
    for idx, span in enumerate(resolved):
        start, end = span
        if idx > 0 and start < normalized[-1][0]:
            start = normalized[-1][0]
        if idx > 0 and start < normalized[-1][1]:
            start = normalized[-1][1]
        if end <= start:
            end = start + 0.06
        normalized.append((start, end))
    return normalized


def _align_script_tokens(
    script_tokens: list[str],
    transcript_words: list[dict[str, Any]],
    fallback_end: float,
) -> list[dict[str, Any]]:
    if not script_tokens:
        return []
    if not transcript_words:
        spans = _spread_times(script_tokens, 0.0, fallback_end)
        return [
            {"text": token, "start": round(start, 3), "end": round(end, 3)}
            for token, (start, end) in zip(script_tokens, spans)
        ]

    script_norm = [normalize_token(token) for token in script_tokens]
    transcript_norm = [normalize_token(str(word.get("word", ""))) for word in transcript_words]
    matcher = SequenceMatcher(a=script_norm, b=transcript_norm, autojunk=False)
    token_times: list[tuple[float, float] | None] = [None] * len(script_tokens)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for script_idx, transcript_idx in zip(range(i1, i2), range(j1, j2)):
                word = transcript_words[transcript_idx]
                token_times[script_idx] = (float(word["start"]), float(word["end"]))
        elif tag == "replace" and (i2 - i1) > 0 and (j2 - j1) > 0:
            _assign_group(token_times, script_tokens, i1, i2, transcript_words[j1:j2])

    total_end = max(fallback_end, float(transcript_words[-1]["end"]))
    spans = _fill_missing_times(token_times, script_tokens, total_end)
    return [
        {"text": token, "start": round(start, 3), "end": round(end, 3)}
        for token, (start, end) in zip(script_tokens, spans)
    ]


def build_karaoke_subtitle_timing(
    output_dir: Path,
    line_items: list[dict[str, Any]],
    *,
    model_size: str = "base",
    language: str | None = None,
    cache_name: str = CACHE_FILE_NAME,
    max_lines: int = 2,
) -> dict[str, Any]:
    cache_file = output_dir / cache_name
    source_files = [output_dir / "timing.json", *[line_audio_path(output_dir, int(item["line"])) for item in line_items]]
    max_words, max_chars = caption_constraints(max_lines)
    if _fresh_cache(cache_file, source_files):
        cached = _load_cached_karaoke(
            cache_file,
            max_lines=max_lines,
            max_words=max_words,
            max_chars=max_chars,
        )
        if cached is not None:
            return cached

    whisper_language = language if language is not None else guess_whisper_language(line_items)
    model = _load_whisper_model(model_size=model_size)

    slides = []
    captions = []
    cumulative = 0.0

    for item in line_items:
        line = int(item["line"])
        text = str(item["text"])
        duration = float(item["duration"])
        original_duration = float(item.get("original_audio_duration", duration))
        audio_file = line_audio_path(output_dir, line)
        if not audio_file.exists():
            raise FileNotFoundError(f"Missing line audio for karaoke subtitles: {audio_file}")

        transcript_words = _transcribe_line_words(model, audio_file, language=whisper_language)
        script_tokens = WORD_RE.findall(text)
        timed_tokens = _align_script_tokens(script_tokens, transcript_words, original_duration)
        token_cursor = 0
        slide_captions = []

        for token_group in split_caption_token_groups(text, max_words=max_words, max_chars=max_chars) or [script_tokens]:
            if not token_group:
                continue
            group_tokens = timed_tokens[token_cursor:token_cursor + len(token_group)]
            token_cursor += len(token_group)
            if not group_tokens:
                continue
            caption_words = [
                {
                    "text": token["text"],
                    "start": round(cumulative + float(token["start"]), 3),
                    "end": round(cumulative + float(token["end"]), 3),
                }
                for token in group_tokens
            ]
            caption = {
                "slide": line,
                "start": caption_words[0]["start"],
                "end": caption_words[-1]["end"],
                "text": " ".join(word["text"] for word in caption_words).strip(),
                "words": caption_words,
            }
            captions.append(caption)
            slide_captions.append(caption)

        slides.append(
            {
                "line": line,
                "start": round(cumulative, 3),
                "duration": round(duration, 3),
                "original_audio_duration": round(original_duration, 3),
                "text": text,
                "captions": slide_captions,
            }
        )
        cumulative += duration

    data = {
        "version": 2,
        "source": "whisper-word-timestamps",
        "mode": "karaoke-red",
        "subtitle_layout": {
            "constraints_version": CAPTION_CONSTRAINTS_VERSION,
            "max_lines": max_lines,
            "max_words": max_words,
            "max_chars": max_chars,
        },
        "duration": round(cumulative, 3),
        "slides": slides,
        "captions": captions,
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def write_subtitle_timing(output_file: Path, line_items: list[dict[str, Any]]) -> dict[str, Any]:
    data = build_script_subtitle_timing(line_items)
    output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
