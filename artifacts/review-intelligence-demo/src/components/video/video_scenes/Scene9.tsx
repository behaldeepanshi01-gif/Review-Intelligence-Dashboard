import { motion } from 'framer-motion';
import { EASE, Stage, violet } from '../ShowcaseUI';

export function Scene9() {
  return (
    <Stage>
      <div className="absolute left-[10vw] top-[12vh] h-[76vh] w-[80vw] overflow-hidden rounded-[1.2vw] border bg-white" style={{ borderColor: '#DCE3EB', boxShadow: '0 12px 36px rgba(15,23,42,.08)' }}>
        <motion.div initial={{ opacity: 1, scale: 1 }} animate={{ opacity: 0.18, scale: 0.97 }} transition={{ delay: 1.5, duration: 1.5, ease: EASE }} className="absolute inset-0">
          <div className="h-[4.2vh] border-b" style={{ borderColor: '#E2E8F0' }} />
          <div className="flex h-[calc(100%-4.2vh)]">
            <div className="w-[16%] border-r" style={{ borderColor: '#E2E8F0' }} />
            <div className="flex-1 p-[2vw]">
              <div className="mb-[2vh] h-[1.5vh] w-[24vw] rounded-full" style={{ background: '#E7EAF0' }} />
              <div className="grid h-[55vh] grid-cols-3 gap-[1vw]">{[0, 1, 2].map((i) => <div key={i} className="rounded-[.8vw] border" style={{ borderColor: '#E6EAF0', background: '#FBFCFE' }} />)}</div>
            </div>
          </div>
        </motion.div>
      </div>
      <div className="absolute left-[18vw] top-[29vh] z-10">
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .2, duration: .5, ease: EASE }} className="mb-[1.4vh] uppercase tracking-[.16em]" style={{ color: violet, fontSize: '.85vw', fontWeight: 750 }}>REVIEW INTELLIGENCE</motion.div>
        <motion.h1 initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .42, duration: .6, ease: EASE }} className="m-0" style={{ color: '#142035', fontFamily: "'Sora', sans-serif", fontSize: '4.7vw', fontWeight: 650, lineHeight: 1.06, letterSpacing: '-.075em' }}>
          Listen clearly.<br />Act thoughtfully.
        </motion.h1>
        <motion.div initial={{ opacity: 0, scale: .94 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.1, duration: .45, ease: EASE }} className="mt-[2.5vh] inline-flex items-center gap-[.6vw] rounded-full border px-[1vw] py-[.9vh]" style={{ background: '#FBF9FF', borderColor: '#E5DDF1', color: '#624487', fontSize: '.75vw', fontWeight: 600 }}>
          <span className="rounded-full" style={{ width: '.45vw', height: '.45vw', background: '#8E64C8' }} /> Offline engine available
        </motion.div>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.3, duration: .5 }} className="mt-[3.2vh]" style={{ color: '#7B8798', fontSize: '.63vw' }}>
          Synthetic demo data · fictional locations · illustrative values
        </motion.div>
      </div>
      <motion.div className="absolute z-10 flex h-[18vh] w-[25vw] flex-col justify-between rounded-[.9vw] border bg-white p-[1.2vw] ui-shadow" style={{ left: '56vw', top: '19vh', borderColor: '#E2E8F0' }} initial={{ opacity: 0, scale: .7, rotate: 0, y: '51vh' }} animate={{ opacity: [0, 1, 1], scale: [0.7, 1, 1], rotate: [0, 5, 8], y: ['51vh', '29vh', '0vh'] }} transition={{ delay: 7.4, duration: 2.8, ease: EASE }}>
        <div className="flex items-center justify-between">
          <span style={{ color: '#94A3B8', fontSize: '.62vw', letterSpacing: '.1em', fontWeight: 700 }}>SAMPLE NOTE</span>
          <span className="rounded-full px-[.6vw] py-[.4vh]" style={{ background: '#F3EEFF', color: '#604488', fontSize: '.62vw', fontWeight: 600 }}>Food</span>
        </div>
        <div className="h-[.55vh] w-[78%] rounded-full" style={{ background: '#EBEEF3' }} />
      </motion.div>
      <motion.div className="absolute left-[18vw] top-[59vh] h-[.35vh] rounded-full" style={{ width: '27vw', background: violet, transformOrigin: 'left' }} initial={{ scaleX: 0 }} animate={{ scaleX: [0, 1, .03] }} transition={{ delay: 8.1, duration: 2.8, ease: EASE }} />
    </Stage>
  );
}
