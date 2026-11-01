import { motion } from 'framer-motion';
import { DemoStamp, EASE, Stage, violet } from '../ShowcaseUI';

const cards = [
  { x: '56vw', y: '19vh', rotate: 8, label: 'SAMPLE NOTE 01', tag: 'Food', color: '#F3EEFF' },
  { x: '66vw', y: '35vh', rotate: -5, label: 'SAMPLE NOTE 02', tag: 'Service speed', color: '#FFF5E8' },
  { x: '53vw', y: '53vh', rotate: 4, label: 'SAMPLE NOTE 03', tag: 'Staff', color: '#EFF6FF' },
];

export function Scene1() {
  return (
    <Stage>
      <div className="absolute left-[7.3vw] top-[17vh] z-10" style={{ width: '44vw' }}>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.5, ease: EASE }} className="mb-[2.4vh] uppercase tracking-[.18em]" style={{ color: violet, fontSize: '1vw', fontWeight: 700 }}>
          THE OWNER’S VIEW
        </motion.div>
        <motion.h1 initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24, duration: 0.62, ease: EASE }} className="m-0" style={{ color: '#0F172A', fontFamily: "'Sora', sans-serif", fontSize: '6.5vw', fontWeight: 650, lineHeight: 1.02, letterSpacing: '-.075em' }}>
          A hundred<br />small signals.
        </motion.h1>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.05, duration: 0.5 }} className="mt-[2.4vh] max-w-[31vw]" style={{ color: '#64748B', fontSize: '1.55vw', lineHeight: 1.5 }}>
          One review at a time. What’s changing?
        </motion.p>
      </div>
      {cards.map((card, i) => (
        <motion.div
          key={card.label}
          className="ui-shadow absolute z-10 rounded-[.9vw] border p-[1.2vw]"
          style={{ left: card.x, top: card.y, width: '25vw', height: '18vh', background: '#fff', borderColor: '#E2E8F0' }}
          initial={{ opacity: 0, scale: 0.7, rotate: card.rotate + 14, y: 40 }}
          animate={{ opacity: 1, scale: 1, rotate: card.rotate, y: 0 }}
          transition={{ delay: 0.42 + i * 0.48, duration: 0.58, ease: [0.2, 0.9, 0.25, 1] }}
        >
          <div className="flex items-center justify-between">
            <span style={{ color: '#94A3B8', fontSize: '.7vw', letterSpacing: '.1em', fontWeight: 700 }}>{card.label}</span>
            <span className="rounded-full px-[.7vw] py-[.45vh]" style={{ background: card.color, color: '#5B467D', fontSize: '.7vw', fontWeight: 600 }}>{card.tag}</span>
          </div>
          <div className="mt-[1.6vh] flex gap-[.38vw]">
            {[72, 50, 84, 59].map((w, j) => <span key={j} className="rounded-full" style={{ width: `${w}%`, height: '.55vh', background: j === 0 ? '#E9E3F5' : '#EDF1F5' }} />)}
          </div>
          <div className="mt-[1.1vh] flex items-center gap-[.45vw]" style={{ color: '#8A96A5', fontSize: '.65vw' }}>
            <span className="rounded-full" style={{ width: '.5vw', height: '.5vw', background: '#CBD5E1' }} />
            Fictional feedback · illustrative
          </div>
        </motion.div>
      ))}
      <motion.div
        className="absolute left-[56vw] top-[76vh] h-[.45vh] rounded-full"
        style={{ width: '12vw', background: violet, transformOrigin: 'left center' }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: [0, 1, 4.2], opacity: [0, 1, 0] }}
        transition={{ delay: 7.5, duration: 2.2, ease: EASE }}
      />
      <DemoStamp />
    </Stage>
  );
}
