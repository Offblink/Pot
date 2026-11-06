/**
 * 音频资源入口。
 *
 * 和 `src/assets.ts` 里的纹理同理：本机 `staticFile()` 在这个 Remotion 版本 +
 * staticBase(`/public`) 组合下会抛「already prefixed」，所以音频也走 webpack import。
 * 好处是音频被打进 bundle，渲染时不需要跑 dev server 去取 public/。
 */
import bgm from '../public/audio/bgm/pot-bgm-120bpm.mp3';
import typing from '../public/audio/sfx/fs-450282.mp3';
import paper from '../public/audio/sfx/fs-464302.mp3';
import whoosh2 from '../public/audio/sfx/fs-701104.mp3';
import thud from '../public/audio/sfx/fs-449955.mp3';
import buzz from '../public/audio/sfx/fs-264779.mp3';
import switchClick from '../public/audio/sfx/fs-815493.mp3';
import stamp from '../public/audio/sfx/fs-448474.mp3';
import swoosh from '../public/audio/sfx/fs-585257.mp3';
import riser from '../public/audio/sfx/fs-685256.mp3';
import sparkle from '../public/audio/sfx/fs-745014.mp3';

export const AUDIO_FILES = {
  bgm,
  typing,
  paper,
  whoosh2,
  thud,
  buzz,
  switch: switchClick,
  stamp,
  swoosh,
  riser,
  sparkle,
} as const;
