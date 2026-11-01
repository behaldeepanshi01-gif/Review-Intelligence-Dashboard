import { motion } from 'framer-motion';
import { BrowserFrame, EASE, Stage, violet } from '../ShowcaseUI';

const sections = [
  { label: 'WHAT GUESTS NOTICED', text: 'Service-speed mentions appear more often in the latest sample.', delay: 1.3 },
  { label: 'WHO GUESTS PRAISED', text: 'Maya Chen · Jonah Reed', delay: 3.0 },
  { label: 'WHAT TO REVIEW', text: 'Discuss pacing during the next team huddle.', delay: 4.6 },
];

export function Scene8() {
  return (
    <Stage tone="paper">
      <BrowserFrame style={{ left: '13vw', top: '7.2vh', width: '74vw', height: '86vh' }}>
        <div className="relative flex h-full flex-col overflow-hidden bg-white px-[5.3vw] py-[4.3vh]">
          <div className="absolute bottom-0 left-0 top-0 w-[.48vw]" style={{ background: violet }} />
          <div className="flex items-center justify-between">
            <div className="uppercase tracking-[.16em]" style={{ color: violet, fontSize: '.65vw', fontWeight: 750 }}>REVIEW INTELLIGENCE · OWNER NOTE</div>
            <div className="rounded-full border px-[.74vw] py-[.48vh]" style={{ borderColor: '#E8E2F2', background: '#FBF9FF', color: '#705A8E', fontSize: '.54vw' }}>ILLUSTRATIVE WEEKLY SUMMARY</div>
          </div>
          <motion.h1 initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .2, duration: .6, ease: EASE }} className="mb-[1.15vh] mt-[2.3vh]" style={{ color: '#142035', fontFamily: "'Sora', sans-serif", fontSize: '3.35vw', fontWeight: 650, lineHeight: 1.06, letterSpacing: '-.075em' }}>
            A week, made clear.
          </motion.h1>
          <motion.div initial={{ opacity: 0, scaleX: 0 }} animate={{ opacity: 1, scaleX: 1 }} transition={{ delay: .65, duration: .7, ease: EASE }} className="mb-[2.1vh] h-[.28vh] w-[43vw] origin-left rounded-full" style={{ background: '#DDD1EF' }} />
          <div className="flex min-h-0 flex-1 flex-col">
            {sections.map((section, i) => (
              <motion.div key={section.label} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: section.delay, duration: .5, ease: EASE }} className="grid grid-cols-[12vw_1fr] gap-[1.2vw] border-b py-[1.45vh]" style={{ borderColor: '#E9EDF2' }}>
                <div className="pt-[.25vh] uppercase tracking-[.12em]" style={{ color: '#7A6A90', fontSize: '.58vw', fontWeight: 700 }}>{section.label}</div>
                <div style={{ color: i === 2 ? '#283649' : '#5D6A7C', fontFamily: i === 2 ? "'Sora', sans-serif" : "'Inter', sans-serif", fontSize: i === 2 ? '1.24vw' : '.86vw', lineHeight: 1.45, fontWeight: i === 2 ? 600 : 500 }}>{section.text}</div>
              </motion.div>
            ))}
          </div>
          <div className="mt-[1vh] flex items-center justify-between" style={{ color: '#8B95A4', fontSize: '.56vw' }}>
            <span>Sample phrasing only · all names and inputs are synthetic</span>
            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 6.5 }} style={{ color: violet, fontWeight: 600 }}>A useful next conversation.</motion.span>
          </div>
          <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: [0, 1, .04] }} transition={{ delay: 10.9, duration: 2.6, ease: EASE }} className="absolute left-0 top-0 h-full w-[.48vw] origin-left" style={{ background: violet }} />
        </div>
      </BrowserFrame>
    </Stage>
  );
}
