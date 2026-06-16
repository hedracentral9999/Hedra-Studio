import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

from app_utils import load_settings
from auto_video_workers import (
    OneShotRenderWorker,
    _default_dji_lut_path,
    _ffprobe_duration,
)


PREVIEW_RUN_DIR = (
    Path.home()
    / "Library/Application Support/Hedra Studio/output/one-shot/_preview-test/2026-06-05/title-expert-a-z-27"
)
PREVIEW_SUMMARY = PREVIEW_RUN_DIR / "preview-summary.json"
RUN_DIR = ROOT / "output/one-shot/render-from-preview/2026-06-06/title-expert-a-z-27"
SUMMARY_JSON = RUN_DIR / "render-summary.json"
SUMMARY_MD = RUN_DIR / "render-summary.md"
LOG_PATH = RUN_DIR / "render-preview-lab-27.log"


def log(line: str) -> None:
    print(line, flush=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_preview_items() -> list[dict]:
    summary = json.loads(PREVIEW_SUMMARY.read_text(encoding="utf-8"))
    items = summary.get("items") if isinstance(summary.get("items"), list) else []
    if len(items) != 27:
        raise RuntimeError(f"Preview summary phải có 27 items, hiện có {len(items)}")
    bad = [x for x in items if x.get("status") not in {"ready", "auto_repaired"} or not x.get("final_title")]
    if bad:
        raise RuntimeError(f"Còn {len(bad)} item chưa pass preview, không render.")
    return items


def load_existing() -> dict[int, dict]:
    if not SUMMARY_JSON.exists():
        return {}
    try:
        data = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = data.get("items") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return {}
    return {int(r.get("index", 0)): r for r in rows if r.get("status") == "OK" and r.get("export_video")}


def build_plan(item: dict, job_dir: Path) -> Path:
    source = Path(str(item["source_video"]))
    if not source.exists():
        raise FileNotFoundError(f"Không thấy video nguồn: {source}")
    item_dir = Path(str(item.get("full_context_pack", ""))).parent
    transcript_path = item_dir / "raw_transcript.json"
    transcript = []
    if transcript_path.exists():
        try:
            data = json.loads(transcript_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                transcript = data
        except Exception:
            transcript = []
    thumbnail_frame = item_dir / "source_frame.png"
    if not thumbnail_frame.exists():
        thumbnail_frame = item_dir / "thumbnail-frame.png"
    if not thumbnail_frame.exists():
        thumbnail_frame = Path("")
    plan = {
        "source_video": str(source),
        "output_dir": str(job_dir),
        "duration": _ffprobe_duration(source),
        "cut_video": False,
        "cuts": [],
        "transcript": transcript,
        "transcript_mode": "preview_lab_raw_transcript",
        "transcript_detail": str(transcript_path),
        "thumbnail_frame": str(thumbnail_frame),
        "thumbnail_preview": str(item.get("thumbnail_preview") or ""),
        "thumbnail_title_suggestion": str(item.get("final_title") or source.stem),
        "industry": "tech",
        "ai_costs": item.get("ai_costs") if isinstance(item.get("ai_costs"), list) else [],
        "preview_status": item.get("status", ""),
        "certified_script_pack": item.get("certified_script_pack", ""),
        "title_candidates": item.get("title_candidates", ""),
    }
    plan_path = job_dir / "cuts.json"
    write_json(plan_path, plan)
    return plan_path


def run_render(plan_path: Path, settings: dict, title: str) -> str:
    result = {"report": "", "error": ""}
    opts = {
        "cut_video": False,
        "noise_reduce": bool(settings.get("one_shot_noise_reduce", True)),
        "noise_mode": settings.get("one_shot_noise_mode", "auto_gentle"),
        "apply_lut": bool(settings.get("one_shot_apply_lut", True)),
        "lut_path": settings.get("one_shot_lut_path") or _default_dji_lut_path(),
        "render_profile": "multi_1080",
        "thumbnail_title": title,
        "thumbnail_font": settings.get("one_shot_thumbnail_font", "dt_phudu_black"),
        "thumbnail_size": settings.get("one_shot_thumbnail_size", "large"),
        "thumbnail_lines": settings.get("one_shot_thumbnail_lines", "auto"),
        "thumbnail_position": settings.get("one_shot_thumbnail_position", "center"),
        "ai_review_thumbnail": False,
        "export_thumbnail": True,
        "prepend_thumbnail_cover": True,
        "render_to_final": True,
        "settings": settings,
        "cleanup_partial": True,
        "overwrite": False,
        "industry": "tech",
    }
    worker = OneShotRenderWorker(str(plan_path), [], opts)
    worker.log_line.connect(lambda line: log("   " + line))
    worker.finished.connect(lambda path: result.__setitem__("report", path))
    worker.error.connect(lambda msg: result.__setitem__("error", msg))
    worker.run()
    if result["error"]:
        raise RuntimeError(result["error"])
    return result["report"]


def write_summary(rows: list[dict], started: float) -> None:
    ok = [r for r in rows if r.get("status") == "OK"]
    err = [r for r in rows if r.get("status") != "OK"]
    summary = {
        "run_dir": str(RUN_DIR),
        "source_preview": str(PREVIEW_SUMMARY),
        "total": len(rows),
        "ok": len(ok),
        "error": len(err),
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "items": rows,
    }
    write_json(SUMMARY_JSON, summary)
    lines = [
        "# Render From Preview Lab 27",
        "",
        f"Run dir: `{RUN_DIR}`",
        f"Source preview: `{PREVIEW_SUMMARY}`",
        f"Result: OK {len(ok)}/27 | Error {len(err)}/27",
        f"Elapsed seconds: {summary['elapsed_seconds']}",
        "",
        "| # | Status | Source | Title | Final video | Thumbnail | Error |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        video = row.get("export_video") or ""
        thumb = row.get("export_thumbnail") or ""
        video_link = f"[{Path(video).name}]({video})" if video else ""
        thumb_link = f"[png]({thumb})" if thumb else ""
        lines.append(
            f"| {row.get('index')} | {row.get('status')} | `{Path(row.get('source_video', '')).name}` | "
            f"{row.get('title', '')} | {video_link} | {thumb_link} | {row.get('error', '')} |"
        )
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    QApplication.instance() or QApplication([])
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    items = load_preview_items()
    settings = load_settings()
    settings.setdefault("one_shot_apply_lut", True)
    settings.setdefault("one_shot_noise_reduce", True)
    settings.setdefault("one_shot_noise_mode", "auto_gentle")
    settings.setdefault("one_shot_thumbnail_font", "dt_phudu_black")
    settings.setdefault("one_shot_thumbnail_size", "large")
    settings.setdefault("one_shot_thumbnail_lines", "auto")
    settings.setdefault("one_shot_thumbnail_position", "center")

    existing = load_existing()
    rows: list[dict] = [existing[i] for i in sorted(existing)]
    started = time.perf_counter()
    log(f"Render preview lab 27 started: {RUN_DIR}")
    log(f"Already OK: {sorted(existing)}")

    for item in items:
        idx = int(item["index"])
        if idx in existing:
            continue
        source = Path(str(item["source_video"]))
        title = str(item["final_title"]).strip()
        job_dir = RUN_DIR / f"{idx:02d}-{source.stem}"
        job_dir.mkdir(parents=True, exist_ok=True)
        row = {
            "index": idx,
            "source_video": str(source),
            "title": title,
            "preview_status": item.get("status", ""),
            "status": "ERROR",
            "error": "",
        }
        t0 = time.perf_counter()
        try:
            log(f"\n[{idx:02d}/27] RENDER | {source.name} | {title}")
            plan_path = build_plan(item, job_dir)
            report_path = run_render(plan_path, settings, title)
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            row.update(
                {
                    "status": "OK",
                    "report": report_path,
                    "export_video": report.get("export_video", ""),
                    "export_thumbnail": report.get("export_thumbnail", ""),
                    "final_video_name": report.get("final_video_name", Path(report.get("export_video", "")).name),
                    "caption": report.get("platform_caption", ""),
                    "hashtags": report.get("final_hashtags", []),
                    "lut_applied_to_video": report.get("lut_applied_to_video", False),
                    "lut_applied_to_thumbnail": report.get("lut_applied_to_thumbnail", False),
                    "noise_decision": report.get("noise_decision", ""),
                    "noise_reason": report.get("noise_reason", ""),
                    "render_profile": report.get("render_profile", {}),
                    "seconds": round(time.perf_counter() - t0, 1),
                }
            )
            log(f"[{idx:02d}/27] OK | {row['final_video_name']} | {row['seconds']}s")
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["seconds"] = round(time.perf_counter() - t0, 1)
            log(f"[{idx:02d}/27] ERROR | {row['error']}")
        existing[idx] = row
        rows = [existing[i] for i in sorted(existing)]
        write_summary(rows, started)

    rows = [existing[i] for i in sorted(existing)]
    write_summary(rows, started)
    ok = len([r for r in rows if r.get("status") == "OK"])
    err = len([r for r in rows if r.get("status") != "OK"])
    log(f"\nDONE OK {ok}/27 | Error {err}/27")
    log(f"Summary: {SUMMARY_MD}")
    return 0 if ok == 27 and err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
