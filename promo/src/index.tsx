import { Composition, registerRoot } from 'remotion';
import { POT_PROMO_DEFAULTS, PotPromo } from './PotPromo';
import { DURATION_IN_FRAMES, FPS, HEIGHT, WIDTH } from './timeline';

/** 唯一 Composition：1920×1080 / 30fps / 1200f（design-spec 已定死的画幅时长） */
const Root: React.FC = () => (
  <Composition
    id="PotPromo"
    component={PotPromo}
    durationInFrames={DURATION_IN_FRAMES}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
    defaultProps={POT_PROMO_DEFAULTS}
  />
);

registerRoot(Root);
