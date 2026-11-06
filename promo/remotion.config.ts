import { Config } from '@remotion/cli/config';

// 帧输出用 jpeg（本片是亮场 UI，jpeg 质量 92 肉眼看不出差别，渲染快一倍多）
Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(92);
Config.setOverwriteOutput(true);
// 本机 Chrome 走 ANGLE 的 GL 后端最稳（headless shell 起不来的那台机器上验证过）
Config.setChromiumOpenGlRenderer('angle');
Config.setConcurrency(8);
