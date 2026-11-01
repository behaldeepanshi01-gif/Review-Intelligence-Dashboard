import { motion } from 'framer-motion';
import { DemoStamp, EASE, Stage, violet } from '../ShowcaseUI';

export function Scene1() {
  return (
    <Stage>
      <div className="absolute left-[6.5vw] top-[13vh] z-10 w-[46vw]">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5, ease: EASE }}
          className="mb-[2vh] uppercase tracking-[.16em]"
          style={{ color: violet, fontSize: '.85vw', fontWeight: 700 }}
        >
          REVIEW INTELLIGENCE · AI WORKFLOW DEMO
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22, duration: 0.62, ease: EASE }}
          className="m-0"
          style={{ color: '#0F172A', fontFamily: "'Sora', sans-serif", fontSize: '5.05vw', fontWeight: 650, lineHeight: 1.05, letterSpacing: '-.075em' }}
        >
          From a review<br />to a clear next step.
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.95, duration: 0.5 }}
          className="mt-[2.2vh] max-w-[36vw]"
          style={{ color: '#64748B', fontSize: '1.2vw', lineHeight: 1.5 }}
        >
          AI helps organize themes and draft a reply. Managers decide what happens next.
        </motion.p>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.15, duration: 0.5 }}
          className="mt-[.6vh]"
          style={{ color: '#7D8998', fontSize: '.68vw' }}
        >
          Illustrative walkthrough · no live restaurant data connected
        </motion.div>
        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 1.2, duration: 0.5, ease: EASE }}
          className="mt-[2vh] inline-flex items-center gap-[.5vw] rounded-full border px-[.8vw] py-[.65vh]"
          style={{ borderColor: '#E5DDF1', background: '#FBF9FF', color: '#665080', fontSize: '.7vw', fontWeight: 600 }}
        >
          <span className="rounded-full" style={{ width: '.45vw', height: '.45vw', background: violet }} />
          7505 VA-7 · Falls Church, VA 22043
        </motion.div>
      </div>

      <motion.div
        className="ui-shadow absolute left-[55vw] top-[20vh] z-10 flex h-[43vh] w-[36vw] flex-col rounded-[1vw] border p-[1.4vw]"
        style={{ borderColor: '#E2E8F0', background: '#fff' }}
        initial={{ opacity: 0, scale: 0.72, rotate: 5, y: 42 }}
        animate={{ opacity: 1, scale: 1, rotate: 1.5, y: 0 }}
        transition={{ delay: 0.42, duration: 0.66, ease: [0.2, 0.9, 0.25, 1] }}
      >
        <div className="flex items-center justify-between border-b pb-[1.1vh]" style={{ borderColor: '#EDF0F4' }}>
          <span className="uppercase tracking-[.13em]" style={{ color: '#765F94', fontSize: '.63vw', fontWeight: 750 }}>FICTIONAL SAMPLE REVIEW</span>
          <span className="rounded-full px-[.62vw] py-[.42vh]" style={{ background: '#F4EEFD', color: '#604488', fontSize: '.57vw', fontWeight: 650 }}>Not a real guest</span>
        </div>
        <div className="flex flex-1 flex-col justify-center">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.42, duration: 0.55, ease: EASE }}
            style={{ color: '#1C293B', fontFamily: "'Sora', sans-serif", fontSize: '1.3vw', lineHeight: 1.45, letterSpacing: '-.035em' }}
          >
            “The spice balance was lovely, but our first check-in took a while.”
          </motion.div>
        </div>
        <div className="border-t pt-[.9vh]" style={{ borderColor: '#EDF0F4', color: '#8793A2', fontSize: '.57vw' }}>
          Synthetic wording · not from Mumbai Central
        </div>
        <div className="absolute -bottom-[1.35vh] left-[1.4vw] flex gap-[.55vw]">
          {[
            { label: 'Spice', bg: '#F2EAFC', color: '#65478C', delay: 5.2 },
            { label: 'Service speed', bg: '#FFF3E3', color: '#976023', delay: 5.65 },
          ].map((tag) => (
            <motion.span
              key={tag.label}
              initial={{ opacity: 0, y: 12, scale: 0.85 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ delay: tag.delay, duration: 0.45, ease: EASE }}
              className="rounded-full border px-[.8vw] py-[.62vh]"
              style={{ borderColor: '#E7E0EF', background: tag.bg, color: tag.color, fontSize: '.67vw', fontWeight: 700 }}
            >
              {tag.label}
            </motion.span>
          ))}
        </div>
      </motion.div>

      <motion.div
        className="absolute left-[57vw] top-[77vh] h-[.45vh] rounded-full"
        style={{ width: '12vw', background: violet, transformOrigin: 'left center' }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: [0, 1, 3.5], opacity: [0, 1, 0] }}
        transition={{ delay: 7.4, duration: 2.15, ease: EASE }}
      />
      <DemoStamp>DEMO ONLY · NO LIVE RESTAURANT DATA</DemoStamp>
    </Stage>
  );
}
