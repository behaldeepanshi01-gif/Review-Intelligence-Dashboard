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
          Mumbai Central.<br />A clearer view.
        </motion.h1>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: .9, duration: .5 }} className="mt-[1.1vh]" style={{ color: '#64748B', fontSize: '.72vw' }}>
          Demo target · 7505 VA-7 · Falls Church, VA 22043
        </motion.div>
        <motion.div initial={{ opacity: 0, scale: .94 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.1, duration: .45, ease: EASE }} className="mt-[2.5vh] inline-flex items-center gap-[.6vw] rounded-full border px-[1vw] py-[.9vh]" style={{ background: '#FBF9FF', borderColor: '#E5DDF1', color: '#624487', fontSize: '.75vw', fontWeight: 600 }}>
          <span className="rounded-full" style={{ width: '.45vw', height: '.45vw', background: '#8E64C8' }} /> Offline engine available
        </motion.div>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.3, duration: .5 }} className="mt-[3.2vh]" style={{ color: '#7B8798', fontSize: '.63vw' }}>
          Demo only · synthetic examples · no live restaurant data
        </motion.div>
      </div>
      <motion.div className="absolute z-10 flex h-[43vh] w-[36vw] flex-col rounded-[1vw] border p-[1.4vw] ui-shadow" style={{ left: '55vw', top: '20vh', borderColor: '#E2E8F0', background: '#fff' }} initial={{ opacity: 0, scale: .7, rotate: 0, y: '48vh' }} animate={{ opacity: [0, 1, 1], scale: [0.7, 1, 1], rotate: [0, 1.5, 1.5], y: ['48vh', '24vh', '0vh'] }} transition={{ delay: 7.4, duration: 2.8, ease: EASE }}>
        <div className="flex items-center justify-between border-b pb-[1.1vh]" style={{ borderColor: '#EDF0F4' }}>
          <span className="uppercase tracking-[.13em]" style={{ color: '#765F94', fontSize: '.63vw', fontWeight: 750 }}>FICTIONAL SAMPLE REVIEW</span>
          <span className="rounded-full px-[.62vw] py-[.42vh]" style={{ background: '#F4EEFD', color: '#604488', fontSize: '.57vw', fontWeight: 650 }}>Not a real guest</span>
        </div>
        <div className="flex flex-1 items-center" style={{ color: '#1C293B', fontFamily: "'Sora', sans-serif", fontSize: '1.3vw', lineHeight: 1.45, letterSpacing: '-.035em' }}>
          “The spice balance was lovely, but our first check-in took a while.”
        </div>
        <div className="border-t pt-[.9vh]" style={{ borderColor: '#EDF0F4', color: '#8793A2', fontSize: '.57vw' }}>Synthetic wording · not from Mumbai Central</div>
        <div className="absolute -bottom-[1.35vh] left-[1.4vw] flex gap-[.55vw]">
          <span className="rounded-full border px-[.8vw] py-[.62vh]" style={{ borderColor: '#E7E0EF', background: '#F2EAFC', color: '#65478C', fontSize: '.67vw', fontWeight: 700 }}>Spice</span>
          <span className="rounded-full border px-[.8vw] py-[.62vh]" style={{ borderColor: '#E7E0EF', background: '#FFF3E3', color: '#976023', fontSize: '.67vw', fontWeight: 700 }}>Service speed</span>
        </div>
      </motion.div>
      <motion.div className="absolute left-[18vw] top-[59vh] h-[.35vh] rounded-full" style={{ width: '27vw', background: violet, transformOrigin: 'left' }} initial={{ scaleX: 0 }} animate={{ scaleX: [0, 1, .03] }} transition={{ delay: 8.1, duration: 2.8, ease: EASE }} />
    </Stage>
  );
}
