import json, sys, os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '/Users/admin/hedra-studio')
from PyQt6.QtWidgets import QApplication; QApplication.instance() or QApplication([])
from app_utils import load_settings
from auto_video_workers import OneShotBatchWorker
from pathlib import Path

videos = sorted(Path('/Users/admin/Documents/POCKET 3/oneshot').glob('DJI_*.MP4'))[:3]
s = load_settings()
s['output_dir'] = '/Users/admin/hedra-studio/output/_verify'
r = {'s': '', 'e': ''}
items = []
w = OneShotBatchWorker(
    [str(v) for v in videos], s,
    {'copy_source': False, 'cut_video': False, 'enterprise_pipeline': True,
     'batch_review_before_render': True, 'batch_deepseek_repair_title': False}
)
w.item_done.connect(lambda i: items.append(i))
w.finished.connect(lambda p: r.__setitem__('s', p))
w.error.connect(lambda m: r.__setitem__('e', m))
w.run()

print(f'Batch: {len(items)} items, error={r["e"] or "none"}')
for i in items:
    n = Path(i.get('source_name', i.get('source', ''))).name
    p = i.get('plan', '')
    psrc = ''
    if p:
        pp = json.loads(open(p).read())
        psrc = Path(pp.get('source_video', '')).name
    ok = 'PASS' if psrc == n else 'MIXUP'
    title = i.get('thumbnail_title', '')
    status = i.get('final_status', '')
    print(f'  {n}: title={title} status={status} plan_src={psrc} [{ok}]')
