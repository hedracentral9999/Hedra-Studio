"""
core — Foundation library for OneShot.
ffmpeg · media · paths
"""
from .ffmpeg import ff_run, duration as ffprobe_duration, video_info as ffprobe_video_info, has_audio as has_audio_stream
from .media import slugify, video_filename, clean_title, split_lines, thumbnail_line_candidates
from .paths import log, output_root, make_job_dir, resolve_lut, recent_titles, api_key_from_settings, cost_vnd, cost_str
