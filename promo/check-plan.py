# -*- coding: utf-8 -*-
"""plan.json 自检：六段帧数相加必须等于 durationInFrames，且每段 beats 之和等于该段 dur。"""
import json
import os
import sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plan.json')
p = json.load(open(P, encoding='utf-8'))

print('fps={fps} {width}x{height} durationInFrames={durationInFrames}'.format(**p))
print('shot  from   dur   to')
total = 0
prev_end = 0
ok = True
for s in p['shots']:
    end = s['from'] + s['dur']
    gap = '' if s['from'] == prev_end else '  <-- 帧不连续（上段止于 {}）'.format(prev_end)
    if gap:
        ok = False
    bsum = sum(b['dur'] for b in s['beats'])
    bflag = '' if bsum == s['dur'] else '  <-- beats 之和 {} != dur {}'.format(bsum, s['dur'])
    if bflag:
        ok = False
    print('{:<4} {:>5} {:>5} {:>5}{}{}'.format(s['id'], s['from'], s['dur'], end, gap, bflag))
    total += s['dur']
    prev_end = end
print('')
print('sum(dur) = {}'.format(total))
print('durationInFrames = {}'.format(p['durationInFrames']))
print('MATCH' if total == p['durationInFrames'] else 'MISMATCH')
print('beats/continuity: {}'.format('OK' if ok and prev_end == p['durationInFrames'] else 'CHECK'))
sys.exit(0 if total == p['durationInFrames'] and ok else 1)
