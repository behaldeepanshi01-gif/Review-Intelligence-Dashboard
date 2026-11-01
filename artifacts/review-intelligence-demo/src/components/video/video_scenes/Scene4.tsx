import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Panel, Stage, violet } from '../ShowcaseUI';

const POINTS = [6, 9, 13, 17];

export function Scene4() {
  return (
    <Stage>
      <BrowserFrame style={{ left: '11vw', top: '10vh', width: '78vw', height: '80vh' }}>
        <AppShell title="Rising themes" subtitle="Mumbai Central · illustrative example only" active="Trends">
          <div className="grid h-full grid-cols-[.78fr_1.22fr] gap-[.9vw]">
            <div className="flex flex-col justify-center">
              <motion.div initial={{ opacity: 0, x: -18 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.48, ease: EASE }} className="mb-[1.1vh] uppercase tracking-[.15em]" style={{ color: violet, fontSize: '.6vw', fontWeight: 700 }}>EXAMPLE ALERT · FICTIONAL DATA</motion.div>
              <motion.h2 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.55, ease: EASE }} className="m-0" style={{ fontFamily: "'Sora', sans-serif", fontSize: '2.5vw', lineHeight: 1.1, letterSpacing: '-.07em', color: '#172238' }}>A signal to<br />examine.</motion.h2>
              <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.7, duration: 0.45 }} className="mt-[2.2vh] rounded-[.72vw] border p-[1vw]" style={{ borderColor: '#F0DCC0', background: '#FFFBF5' }}>
                <div className="flex items-center gap-[.5vw]">
                  <span className="rounded-full px-[.55vw] py-[.4vh]" style={{ color: '#9A5C11', background: '#FFF0D9', fontSize: '.54vw', fontWeight: 700 }}>ILLUSTRATIVE ALERT</span>
                  <span style={{ color: '#253247', fontSize: '.78vw', fontWeight: 650 }}>Service speed</span>
                </div>
                <div className="mt-[.75vh]" style={{ color: '#68778B', fontSize: '.61vw', lineHeight: 1.5 }}>Synthetic example trend · not calculated from venue reviews.</div>
              </motion.div>
              <div className="mt-[1.25vh] max-w-[20vw]" style={{ color: '#8A96A5', fontSize: '.52vw', lineHeight: 1.5 }}>Not a finding about Mumbai Central. No review data connected.</div>
            </div>
            <Panel className="h-full" title="Example service-speed mentions" eyebrow="Illustrative values only">
              <div className="flex items-end justify-between px-[.5vw] pt-[1vh]" style={{ height: '68%' }}>
                {POINTS.map((point, i) => (
                  <div key={point} className="flex h-full flex-1 flex-col items-center justify-end gap-[.65vh]">
                    <motion.div
                      className="flex items-start justify-center rounded-t-[.4vw] pt-[.55vh]"
                      style={{ width: '3.1vw', height: `${(point / 18) * 100}%`, background: i === 3 ? 'linear-gradient(180deg,#9A70E6,#7C3AED)' : '#E3DAF0', transformOrigin: 'bottom' }}
                      initial={{ scaleY: 0 }}
                      animate={{ scaleY: 1 }}
                      transition={{ delay: 0.65 + i * 0.28, duration: 0.55, ease: EASE }}
                    >
                      <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.1 + i * 0.28 }} style={{ color: i === 3 ? '#fff' : '#78668F', fontSize: '.61vw', fontWeight: 700 }}>{point}</motion.span>
                    </motion.div>
                    <div style={{ color: '#8893A2', fontSize: '.54vw' }}>Sample {i + 1}</div>
                  </div>
                ))}
              </div>
              <div className="mt-[1vh] h-px" style={{ background: '#E8ECF1' }} />
              <div className="mt-[1vh] flex items-center justify-between">
                <span style={{ color: '#6B788B', fontSize: '.58vw' }}>Synthetic sample mentions · no measured data</span>
                <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 2, duration: 1.2, ease: EASE }} className="h-[.3vh] w-[48%] rounded-full" style={{ background: violet, transformOrigin: 'left' }} />
              </div>
              <div className="mt-auto flex items-center gap-[.55vw] rounded-[.5vw] px-[.72vw] py-[.65vh]" style={{ background: '#F7F3FD', color: '#63478D', fontSize: '.57vw' }}>
                <span style={{ color: violet }}>↗</span> A demo prompt for a manager to explore—not a venue finding.
              </div>
            </Panel>
          </div>
        </AppShell>
      </BrowserFrame>
    </Stage>
  );
}
