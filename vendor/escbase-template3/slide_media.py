from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


class SlideVideoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_slide: int | None = None
        self.next_slide = 0
        self.slide_div_depth = 0
        self.videos: dict[int, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "div" and "slide" in classes:
            raw_slide = attr_map.get("data-slide", "")
            if raw_slide.isdigit():
                self.current_slide = int(raw_slide)
                self.next_slide = max(self.next_slide, self.current_slide + 1)
            else:
                self.current_slide = self.next_slide
                self.next_slide += 1
            self.slide_div_depth = 1
            self.videos.setdefault(self.current_slide, [])
        elif tag == "div" and self.current_slide is not None:
            self.slide_div_depth += 1
        if self.current_slide is not None and tag in {"video", "source"}:
            src = attr_map.get("src", "").strip()
            if src:
                self.videos.setdefault(self.current_slide, []).append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or self.current_slide is None:
            return
        self.slide_div_depth -= 1
        if self.slide_div_depth <= 0:
            self.current_slide = None
            self.slide_div_depth = 0


def media_src_to_path(slide_dir: Path, src: str) -> Path | None:
    parsed = urlsplit(src.strip())
    if parsed.scheme and parsed.scheme not in {"file"}:
        return None
    clean_path = unquote(parsed.path if parsed.scheme == "file" else src.split("#", 1)[0].split("?", 1)[0])
    if not clean_path:
        return None
    path = Path(clean_path)
    if not path.is_absolute():
        path = slide_dir / path
    try:
        path = path.resolve()
    except OSError:
        return None
    return path if path.exists() and path.is_file() else None


def discover_slide_videos(slide_dir: Path) -> dict[int, list[Path]]:
    index_path = slide_dir / "index.html"
    if not index_path.exists():
        return {}
    parser = SlideVideoParser()
    parser.feed(index_path.read_text(encoding="utf-8"))
    deleted_ids: set[str] = set()
    settings_path = slide_dir / "preview-settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            raw_deleted = settings.get("slides", {}).get("deletedIds", []) if isinstance(settings, dict) else []
            if isinstance(raw_deleted, list):
                deleted_ids = {str(item) for item in raw_deleted}
        except json.JSONDecodeError:
            deleted_ids = set()
    active_index_by_original: dict[int, int] = {}
    for slide_idx in sorted(parser.videos):
        if str(slide_idx) in deleted_ids:
            continue
        active_index_by_original[slide_idx] = len(active_index_by_original)
    videos: dict[int, list[Path]] = {}
    for slide_idx, srcs in parser.videos.items():
        active_idx = active_index_by_original.get(slide_idx)
        if active_idx is None:
            continue
        seen: set[Path] = set()
        for src in srcs:
            path = media_src_to_path(slide_dir, src)
            if path is None or path in seen:
                continue
            seen.add(path)
            videos.setdefault(active_idx, []).append(path)
    return videos
