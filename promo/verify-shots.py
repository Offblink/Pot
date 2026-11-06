# -*- coding: utf-8 -*-
"""阶段 1–3 用：校验本片选中的镜头卡与 style-key 是否真的存在于 gallery 索引里。
用法：python promo/verify-shots.py
对应 design-spec.md §8「功能 → 镜头映射表」的每一行（首选 / 备选 / 已读未用）。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, 'data', 'skills', 'video-shotcraft', 'gallery', 'api', 'library.json')

# (shot, 用途, card, styleKey, 状态)  状态: 选中 / 备选 / 已读未用
SELECTION = [
    ('S1', '一句话：打字', 'glass-pill-dictation-typing', 'glass-pill-dictation-typing', '选中'),
    ('S2', '一句话凝成卡并嵌入板槽', 'row-embed', 'row-embed', '选中'),
    ('S2', '俯视场景揭示（相机层）', 'crane-rise-reveal', 'crane-rise-reveal', '选中'),
    ('S3', '标签闸：拒绝的一瞬', 'crash-zoom-punch', 'crash-zoom-punch', '选中'),
    ('S4', '多角色多轨并行', 'quad-split-parallel-scenes', 'quad-split-parallel-scenes', '选中'),
    ('S5', '报告落回会话 + 完成', 'doc-park-left-pill-deal', 'doc-park-left-pill-deal', '选中'),
    ('S6', '整块板剥离成字标', 'ui-strip-away-outro', 'ui-strip-away-outro', '选中'),
    ('S1', '打字（首要备选）', 'typewriter-moves', 'error-retype', '备选'),
    ('S1', '打字（备选）', 'type-rhythm-sync', 'font-weight-pump', '备选'),
    ('S2', '文本实体化（备选）', 'hashtag-to-pill-materialize', 'hashtag-to-pill-materialize', '备选'),
    ('S2', '俯拍揭示（备选）', 'overhead-camera-moves', 'tilt-reveal', '备选'),
    ('S2', '发牌飞入（已读未用）', 'deck-deal-flyin', 'deck-deal-flyin', '已读未用'),
    ('S3', '拒绝（已读未用）', 'impact-feedback', 'hit-counter', '已读未用'),
    ('S3', '打断节奏（备选）', 'rhythm-interrupt-moves', 'jump-cut-punch-in', '备选'),
    ('S3', '通过（备选）', 'list-reveal', 'list-reveal', '备选'),
    ('S4', '分格（备选）', 'panel-grid-moves', 'comic-panel-split', '备选'),
    ('S4', '增殖（已读未用）', 'cloner-depth-echo', 'cloner-depth-echo', '已读未用'),
    ('S5', '完成压暗（备选）', 'list-stack-press', 'list-stack-press', '备选'),
    ('S6', 'UI 变品牌（备选）', 'ui-to-brand-morph', 'input-morph-assemble', '备选'),
]


def main():
    with open(LIB, encoding='utf-8') as f:
        lib = json.load(f)
    cards = {c['name']: c for c in lib['cards']}
    print('library.json: generatedAt=%s revision=%s' % (lib['generatedAt'], lib['revision']))
    print('stats: %s' % json.dumps(lib['stats'], ensure_ascii=False))
    print('')
    bad = 0
    for shot, use, card, key, state in SELECTION:
        c = cards.get(card)
        if c is None:
            print('FAIL  %-3s %-14s %-30s style=%-28s  卡名不存在' % (shot, state, card, key))
            bad += 1
            continue
        keys = [s['key'] for s in c['styles']]
        if key not in keys:
            print('FAIL  %-3s %-14s %-30s style=%-28s  卡存在但 style 不存在（有：%s）'
                  % (shot, state, card, key, ','.join(keys)))
            bad += 1
            continue
        has_media = any(s.get('media') for s in c['styles'] if s['key'] == key)
        print('OK    %-3s %-14s %-30s style=%-28s cat=%-12s preview=%s dur=%s'
              % (shot, state, card, key, c['category'], 'yes' if has_media else 'NO', c['duration']))
    print('')
    print('checked=%d failed=%d' % (len(SELECTION), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
