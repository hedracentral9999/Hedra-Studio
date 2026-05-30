#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import textwrap
from html.parser import HTMLParser
from pathlib import Path


class SlideHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack = []
        self.slides = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        node = {
            "tag": tag,
            "classes": classes,
            "mode": attr_map.get("data-mode") if "slide" in classes else None,
            "slide_id": (attr_map.get("data-slide-id") or attr_map.get("data-slide")) if "slide" in classes else None,
            "slide_elements": 1 if "slide-element" in classes else 0,
            "highlightables": 1 if "highlightable" in classes else 0,
            "lightables": 1 if "lightable" in classes else 0,
            "text_parts": [],
            "slide_element_texts": [],
            "highlightable_texts": [],
            "lightable_texts": [],
        }
        if tag in {"video", "audio"}:
            src = attr_map.get("src") or "embedded"
            node["text_parts"].append(f"[{tag}: {src}]")
        self.stack.append(node)

    def handle_data(self, data: str) -> None:
        if self.stack:
            self.stack[-1]["text_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return

        node = self.stack.pop()
        node_text = normalize_text(" ".join(node["text_parts"]))
        if "slide-element" in node["classes"] and node_text:
            node["slide_element_texts"].append(node_text)
        if "highlightable" in node["classes"] and node_text:
            node["highlightable_texts"].append(node_text)
        if "lightable" in node["classes"] and node_text:
            node["lightable_texts"].append(node_text)
        if "slide" not in node["classes"] and node_text:
            while len(node["highlightable_texts"]) < node["highlightables"]:
                node["highlightable_texts"].append(node_text)
            while len(node["lightable_texts"]) < node["lightables"]:
                node["lightable_texts"].append(node_text)

        if self.stack:
            parent = self.stack[-1]
            parent["slide_elements"] += node["slide_elements"]
            parent["highlightables"] += node["highlightables"]
            parent["lightables"] += node["lightables"]
            parent["text_parts"].extend(node["text_parts"])
            parent["slide_element_texts"].extend(node["slide_element_texts"])
            parent["highlightable_texts"].extend(node["highlightable_texts"])
            parent["lightable_texts"].extend(node["lightable_texts"])

        if "slide" in node["classes"]:
            self.slides.append(
                {
                    "mode": node["mode"],
                    "slide_id": node["slide_id"],
                    "slide_elements": int(node["slide_elements"]),
                    "highlightables": int(node["highlightables"]),
                    "lightables": int(node["lightables"]),
                    "slide_element_texts": node["slide_element_texts"],
                    "highlightable_texts": node["highlightable_texts"],
                    "lightable_texts": node["lightable_texts"],
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate slide/script mapping without TTS or rendering.")
    parser.add_argument("slide_dir", help="Slide project folder, relative to repo root or absolute")
    parser.add_argument("--expected-slides", type=int, default=None)
    parser.add_argument("--semantic-report", action="store_true", help="Print sentence-to-reveal text for manual review")
    parser.add_argument("--skip-safezone", action="store_true", help="Skip Playwright layout-box safezone check")
    parser.add_argument("--safe-top", type=float, default=100.0, help="Minimum allowed content top in CSS px")
    parser.add_argument("--safe-bottom", type=float, default=200.0, help="Minimum allowed distance from content bottom to slide bottom in CSS px")
    return parser.parse_args()


def resolve_slide_dir(raw_path: str) -> Path:
    repo_root = Path(__file__).resolve().parent
    slide_dir = Path(raw_path)
    if not slide_dir.is_absolute():
        slide_dir = repo_root / slide_dir
    return slide_dir.resolve()


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_script_lines(script_path: Path) -> list[str]:
    return script_path.read_text(encoding="utf-8").splitlines()


def extract_js_array_body(js: str, variable_name: str) -> str:
    match = re.search(rf"\bconst\s+{re.escape(variable_name)}\s*=\s*\[", js)
    if not match:
        raise ValueError(f"Cannot find const {variable_name} = [...] in app.js")

    start = js.find("[", match.start())
    depth = 0
    quote = ""
    escaped = False
    body_start = start + 1

    for index in range(start, len(js)):
        char = js[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue

        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "[":
            depth += 1
            continue
        if char == "]":
            depth -= 1
            if depth == 0:
                return js[body_start:index]

    raise ValueError(f"Cannot find closing ] for {variable_name} in app.js")


def extract_js_strings(array_body: str) -> list[str]:
    strings = []
    index = 0

    while index < len(array_body):
        char = array_body[index]
        if char not in {"'", '"', "`"}:
            index += 1
            continue

        quote = char
        index += 1
        value = []
        escaped = False

        while index < len(array_body):
            char = array_body[index]
            index += 1

            if escaped:
                if char == "n":
                    value.append("\n")
                elif char == "t":
                    value.append("\t")
                else:
                    value.append(char)
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue
            if char == quote:
                break
            value.append(char)

        strings.append("".join(value))

    return strings


def read_slide_scripts(app_path: Path) -> list[str]:
    app = app_path.read_text(encoding="utf-8")
    return extract_js_strings(extract_js_array_body(app, "slideScripts"))


def read_html_slides(index_path: Path) -> list[dict]:
    parser = SlideHTMLParser()
    parser.feed(index_path.read_text(encoding="utf-8"))
    return parser.slides


def read_preview_settings(slide_dir: Path) -> dict:
    path = slide_dir / "preview-settings.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def active_slide_indexes(html_slides: list[dict], settings: dict) -> list[int]:
    slides_settings = settings.get("slides", {}) if isinstance(settings, dict) else {}
    raw_deleted = slides_settings.get("deletedIds") if isinstance(slides_settings, dict) else []
    deleted_ids = {str(item) for item in raw_deleted} if isinstance(raw_deleted, list) else set()
    if not deleted_ids:
        return list(range(len(html_slides)))
    indexes = []
    for index, slide in enumerate(html_slides):
        slide_id = str(slide.get("slide_id") if slide.get("slide_id") is not None else index)
        if slide_id not in deleted_ids:
            indexes.append(index)
    return indexes


def preview_script_lines(settings: dict, expected_count: int) -> list[str] | None:
    slides_settings = settings.get("slides", {}) if isinstance(settings, dict) else {}
    raw_lines = slides_settings.get("scriptLines") if isinstance(slides_settings, dict) else []
    if not isinstance(raw_lines, list):
        return None
    lines = [str(line).strip() for line in raw_lines]
    if len(lines) != expected_count or any(not line for line in lines):
        return None
    return lines


def reveal_units(slide: dict) -> int:
    count = slide["slide_elements"]
    if slide["mode"] == "highlight":
        count += slide["highlightables"]
    if slide["mode"] == "traffic-light":
        count += slide["lightables"]
    return count


def reveal_texts(slide: dict) -> list[str]:
    texts = list(slide["slide_element_texts"])
    if slide["mode"] == "highlight":
        texts.extend(slide["highlightable_texts"])
    if slide["mode"] == "traffic-light":
        texts.extend(slide["lightable_texts"])
    return texts


def format_report_text(text: str) -> str:
    if not text:
        return "(missing)"
    return textwrap.shorten(text, width=180, placeholder="...")


def print_semantic_report(script_lines: list[str], html_slides: list[dict]) -> None:
    print("\n=== Semantic 1:1 report ===")
    print("Review manually: each sentence should match the visual/text revealed on the same row.")
    max_mapping = min(len(script_lines), len(html_slides))
    for slide_index in range(max_mapping):
        sentences = split_sentences(script_lines[slide_index])
        texts = reveal_texts(html_slides[slide_index])
        mode = html_slides[slide_index]["mode"] or "normal"
        print(f"\nSlide {slide_index + 1} (mode={mode})")
        rows = max(len(sentences), len(texts))
        for row_index in range(rows):
            sentence = sentences[row_index] if row_index < len(sentences) else ""
            visual_text = texts[row_index] if row_index < len(texts) else ""
            print(f"  Reveal {row_index + 1}")
            print(f"    Voiceover: {format_report_text(sentence)}")
            print(f"    Visual:    {format_report_text(visual_text)}")


async def measure_safezone_layout_async(slide_dir: Path, safe_top: float, safe_bottom: float) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for safezone checks. Install requirements and run `python3 -m playwright install chromium`.") from exc

    index_uri = (slide_dir / "index.html").as_uri()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
            await page.goto(index_uri, wait_until="networkidle")
            await page.evaluate(
                """
                () => {
                  const style = document.createElement('style');
                  style.textContent = '*, *::before, *::after { animation: none !important; transition: none !important; }';
                  document.head.appendChild(style);
                  document.querySelectorAll('.slide').forEach(slide => {
                    slide.classList.add('active');
                    slide.style.opacity = '1';
                    slide.style.transform = 'none';
                    slide.style.pointerEvents = 'none';
                  });
                  document.querySelectorAll('.slide-element, .highlightable, .lightable').forEach(el => {
                    el.classList.add('visible');
                    el.classList.add('active');
                    el.classList.add('lit-red');
                    el.classList.add('lit-yellow');
                    el.classList.add('lit-green');
                  });
                  document.querySelectorAll('video').forEach(video => { video.pause(); });
                }
                """
            )
            await page.wait_for_timeout(300)
            return await page.evaluate(
                """
                ({ safeTop, safeBottom }) => {
                  const container = document.querySelector('.slide-container');
                  if (!container) throw new Error('Missing .slide-container');
                  const c = container.getBoundingClientRect();
                  const safeBottomY = c.height - safeBottom;
                  function relRect(el) {
                    const r = el.getBoundingClientRect();
                    return {
                      top: r.top - c.top,
                      bottom: r.bottom - c.top,
                      left: r.left - c.left,
                      right: r.right - c.left,
                      width: r.width,
                      height: r.height,
                    };
                  }
                  function union(rects) {
                    if (!rects.length) return null;
                    const top = Math.min(...rects.map(r => r.top));
                    const bottom = Math.max(...rects.map(r => r.bottom));
                    const left = Math.min(...rects.map(r => r.left));
                    const right = Math.max(...rects.map(r => r.right));
                    return { top, bottom, left, right, height: bottom - top };
                  }
                  return {
                    width: c.width,
                    height: c.height,
                    safeTop,
                    safeBottom,
                    safeBottomY,
                    slides: Array.from(document.querySelectorAll('.slide')).map((slide, index) => {
                      const content = slide.querySelector('.slide-content');
                      const contentStyle = content ? getComputedStyle(content) : null;
                      const elements = Array.from(slide.querySelectorAll('.slide-element'));
                      const rect = union(elements.map(relRect));
                      return {
                        slide: index + 1,
                        mode: slide.getAttribute('data-mode') || 'normal',
                        paddingTop: contentStyle ? parseFloat(contentStyle.paddingTop) : null,
                        paddingBottom: contentStyle ? parseFloat(contentStyle.paddingBottom) : null,
                        top: rect ? rect.top : null,
                        bottom: rect ? rect.bottom : null,
                        bottomGap: rect ? c.height - rect.bottom : null,
                        topViolation: rect ? Math.max(0, safeTop - rect.top) : 0,
                        bottomViolation: rect ? Math.max(0, rect.bottom - safeBottomY) : 0,
                      };
                    }),
                  };
                }
                """,
                {"safeTop": safe_top, "safeBottom": safe_bottom},
            )
        finally:
            await browser.close()


def measure_safezone_layout(slide_dir: Path, safe_top: float, safe_bottom: float) -> dict:
    return asyncio.run(measure_safezone_layout_async(slide_dir, safe_top, safe_bottom))


def format_px(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}px"


def print_safezone_report(report: dict, errors: list[str]) -> None:
    print("\n=== Safezone layout-box ===")
    print(
        "Slide frame: "
        f"{format_px(report.get('width'))} x {format_px(report.get('height'))}; "
        f"safe Y: {format_px(report.get('safeTop'))} -> {format_px(report.get('safeBottomY'))} "
        f"(bottom gap >= {format_px(report.get('safeBottom'))})"
    )
    for item in report.get("slides", []):
        top_violation = float(item.get("topViolation") or 0)
        bottom_violation = float(item.get("bottomViolation") or 0)
        status = "OK" if top_violation <= 0.5 and bottom_violation <= 0.5 else "BAD"
        print(
            f"Slide {item['slide']}: "
            f"top={format_px(item.get('top'))}, "
            f"bottom={format_px(item.get('bottom'))}, "
            f"bottomGap={format_px(item.get('bottomGap'))}, "
            f"padding={format_px(item.get('paddingTop'))}/{format_px(item.get('paddingBottom'))} -> {status}"
        )
        if top_violation > 0.5:
            errors.append(f"Slide {item['slide']}: content starts {top_violation:.2f}px above top safezone")
        if bottom_violation > 0.5:
            errors.append(f"Slide {item['slide']}: content extends {bottom_violation:.2f}px into bottom safezone")


def validate(args: argparse.Namespace) -> int:
    slide_dir = resolve_slide_dir(args.slide_dir)
    script_path = slide_dir / "script-90s.txt"
    app_path = slide_dir / "app.js"
    index_path = slide_dir / "index.html"
    errors = []

    for path in (script_path, app_path, index_path):
        if not path.is_file():
            errors.append(f"Missing required file: {path.name}")

    if errors:
        print(f"Slide dir: {slide_dir}")
        print("\nFAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    try:
        script_lines = read_script_lines(script_path)
        slide_scripts = read_slide_scripts(app_path)
        html_slides = read_html_slides(index_path)
        preview_settings = read_preview_settings(slide_dir)
    except Exception as exc:
        print(f"Slide dir: {slide_dir}")
        print("\nFAIL")
        print(f"  - {exc}")
        return 1

    active_indexes = active_slide_indexes(html_slides, preview_settings)
    has_deleted_slides = len(active_indexes) != len(html_slides)
    preview_lines = preview_script_lines(preview_settings, len(active_indexes)) if has_deleted_slides else None
    html_slides = [html_slides[index] for index in active_indexes]
    if preview_lines is not None:
        slide_scripts = preview_lines
    elif len(slide_scripts) != len(active_indexes) and len(slide_scripts) >= max(active_indexes, default=-1) + 1:
        slide_scripts = [slide_scripts[index] for index in active_indexes]

    if args.expected_slides is not None:
        if len(script_lines) != args.expected_slides:
            errors.append(f"script-90s.txt has {len(script_lines)} lines, expected {args.expected_slides}")
        if len(slide_scripts) != args.expected_slides:
            errors.append(f"slideScripts has {len(slide_scripts)} items, expected {args.expected_slides}")
        if len(html_slides) != args.expected_slides:
            errors.append(f"index.html has {len(html_slides)} .slide elements, expected {args.expected_slides}")
    else:
        if len(script_lines) != len(slide_scripts):
            errors.append(f"script-90s.txt has {len(script_lines)} lines, slideScripts has {len(slide_scripts)} items")
        if len(script_lines) != len(html_slides):
            errors.append(f"script-90s.txt has {len(script_lines)} lines, index.html has {len(html_slides)} .slide elements")

    for index, line in enumerate(script_lines):
        if not line.strip():
            errors.append(f"Slide {index + 1}: script line is empty")

    for index, (script_line, app_line) in enumerate(zip(script_lines, slide_scripts), start=1):
        if script_line != app_line:
            errors.append(f"Slide {index}: script-90s.txt and slideScripts text do not match")

    max_mapping = min(len(script_lines), len(html_slides))
    mapping_rows = []
    for index in range(max_mapping):
        sentence_count = len(split_sentences(script_lines[index]))
        unit_count = reveal_units(html_slides[index])
        mode = html_slides[index]["mode"] or "normal"
        mapping_rows.append((index, sentence_count, unit_count, mode))

        if sentence_count != unit_count:
            errors.append(f"Slide {index + 1}: {sentence_count} script sentences != {unit_count} reveal units")

    print("=== Slide validation ===")
    print(f"Slide dir: {slide_dir}")
    print(f"script lines: {len(script_lines)}")
    print(f"slideScripts: {len(slide_scripts)}")
    print(f"HTML slides: {len(html_slides)}")
    print("\n=== Mapping ===")
    for index, sentence_count, unit_count, mode in mapping_rows:
        status = "OK" if sentence_count == unit_count else "BAD"
        print(f"Slide {index + 1}: {sentence_count} sentences / {unit_count} reveal units (mode={mode}) -> {status}")

    if args.semantic_report:
        print_semantic_report(script_lines, html_slides)

    if not args.skip_safezone:
        try:
            safezone_report = measure_safezone_layout(slide_dir, args.safe_top, args.safe_bottom)
            if has_deleted_slides:
                safezone_report["slides"] = [safezone_report["slides"][index] for index in active_indexes if index < len(safezone_report["slides"])]
            print_safezone_report(safezone_report, errors)
        except Exception as exc:
            errors.append(f"Safezone check failed: {exc}")

    if errors:
        print("\nFAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("\nPASS: slide is ready for TTS/render.")
    return 0


def main() -> int:
    return validate(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
