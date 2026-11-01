import { useVideoPlayer, VideoCanvas, type VideoAspectRatio } from '@/lib/video';
import { AnimatePresence, motion } from 'framer-motion';
import { Scene1 } from './video_scenes/Scene1';
import { Scene2 } from './video_scenes/Scene2';
import { Scene3 } from './video_scenes/Scene3';
import { Scene4 } from './video_scenes/Scene4';
import { Scene5 } from './video_scenes/Scene5';
import { Scene6 } from './video_scenes/Scene6';
import { Scene7 } from './video_scenes/Scene7';
import { Scene8 } from './video_scenes/Scene8';
import { Scene9 } from './video_scenes/Scene9';

const SCENE_DURATIONS = {
  opening: 10000,
  overview: 14000,
  themes: 15000,
  trends: 14000,
  team: 13000,
  replies: 14000,
  locations: 14000,
  ownerBrief: 15000,
  close: 11000,
};

const VIDEO_ASPECT_RATIO: VideoAspectRatio = '16:9';
const SCENE_COMPONENTS = [Scene1, Scene2, Scene3, Scene4, Scene5, Scene6, Scene7, Scene8, Scene9];
const CURSOR_POSITIONS = [
  { left: '72vw', top: '70vh', opacity: 1 },
  { left: '72vw', top: '27vh', opacity: 1 },
  { left: '83vw', top: '41vh', opacity: 1 },
  { left: '70vw', top: '65vh', opacity: 1 },
  { left: '77vw', top: '49vh', opacity: 1 },
  { left: '77vw', top: '64vh', opacity: 1 },
  { left: '81vw', top: '42vh', opacity: 1 },
  { left: '76vw', top: '64vh', opacity: 1 },
  { left: '83vw', top: '81vh', opacity: 0 },
];

export default function VideoTemplate() {
  const { currentScene, currentSceneKey } = useVideoPlayer({
    durations: SCENE_DURATIONS,
  });
  const Scene = SCENE_COMPONENTS[currentScene];

  return (
    <VideoCanvas
      aspectRatio={VIDEO_ASPECT_RATIO}
      className="relative h-screen w-full overflow-hidden"
      style={{ backgroundColor: 'var(--color-bg-light)', fontFamily: "'Inter', sans-serif" }}
    >
      <div className="absolute inset-0 micro-grid opacity-55" />
      <AnimatePresence mode="sync">
        <Scene key={currentSceneKey} />
      </AnimatePresence>
      <motion.div
        className="pointer-events-none absolute z-50"
        animate={CURSOR_POSITIONS[currentScene]}
        transition={{ duration: 0.85, ease: [0.45, 0, 0.25, 1] }}
      >
        <svg width="30" height="30" viewBox="0 0 24 24" style={{ filter: 'drop-shadow(0 2px 5px rgba(15,23,42,.4))' }}>
          <path d="M4.8 2.2 L4.8 18.6 L9 14.9 L11.6 20.8 L14.4 19.6 L11.8 13.8 L17.4 13.4 Z" fill="#0F172A" stroke="#FFFFFF" strokeWidth="1.4" strokeLinejoin="round" />
        </svg>
      </motion.div>
      {currentScene > 0 && currentScene < 8 && (
        <motion.div
          key={`ripple-${currentSceneKey}`}
          className="pointer-events-none absolute z-40 h-[1.2vw] w-[1.2vw] rounded-full border-2"
          style={{ left: CURSOR_POSITIONS[currentScene].left, top: CURSOR_POSITIONS[currentScene].top, borderColor: '#7C3AED', translateX: '-50%', translateY: '-50%' }}
          initial={{ opacity: .8, scale: .4 }}
          animate={{ opacity: 0, scale: 3.7 }}
          transition={{ duration: .62, delay: .72, ease: 'easeOut' }}
        />
      )}
    </VideoCanvas>
  );
}
