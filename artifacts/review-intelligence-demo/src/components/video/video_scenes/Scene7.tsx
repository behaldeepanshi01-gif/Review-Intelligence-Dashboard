import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Panel, Stage, violet } from '../ShowcaseUI';

const LOCATIONS = [
  { name: 'North Room', accent: '#7C3AED', values: [0.47, 0.75, 0.36] },
  { name: 'Lantern Yard', accent: '#9B80C5', values: [0.67, 0.44, 0.6] },
  { name: 'Fieldhouse', accent: '#B6A7CC', values: [0.82, 0.59, 0.42] },
];
const ROWS = ['Service speed', 'Cleanliness', 'Portions'];

export function Scene7() {
  return (
    <Stage>
      <BrowserFrame style={{ left: '6.3vw', top: '8.8vh', width: '87.4vw', height: '82.4vh' }}>
        <AppShell title="Location patterns" subtitle="Compare themes across a fictional restaurant group" active="Overview">
          <div className="flex h-full flex-col">
            <div className="mb-[1.1vh] flex items-center justify-between">
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .45, ease: EASE }} style={{ color: '#162238', fontFamily: "'Sora', sans-serif", fontSize: '1.34vw', fontWeight: 650, letterSpacing: '-.06em' }}>See the whole group.</motion.div>
              <div className="rounded-full border px-[.68vw] py-[.45vh]" style={{ background: '#FCFAFF', borderColor: '#E9E1F4', color: '#705A8E', fontSize: '.54vw' }}>Fictional locations</div>
            </div>
            <div className="grid min-h-0 flex-1 grid-cols-3 gap-[.72vw]">
              {LOCATIONS.map((location, index) => (
                <motion.div key={location.name} initial={{ opacity: 0, y: 20, rotateY: index === 0 ? -4 : index === 2 ? 4 : 0 }} animate={{ opacity: 1, y: 0, rotateY: 0 }} transition={{ delay: .2 + index * .24, duration: .5, ease: EASE }}>
                  <Panel className="h-full" title={location.name} eyebrow={`DEMO LOCATION 0${index + 1}`}>
                    <div className="mb-[.85vh] flex items-center gap-[.4vw]">
                      <span className="rounded-full" style={{ width: '.48vw', height: '.48vw', background: location.accent }} />
                      <span style={{ color: '#64748B', fontSize: '.54vw' }}>Illustrative theme mentions</span>
                    </div>
                    <div className="flex flex-1 flex-col justify-between">
                      {ROWS.map((row, r) => (
                        <div key={row}>
                          <div className="mb-[.42vh] flex justify-between" style={{ color: '#677589', fontSize: '.54vw' }}>
                            <span>{row}</span><span>sample</span>
                          </div>
                          <div className="h-[1.25vh] overflow-hidden rounded-full" style={{ background: '#EDF1F5' }}>
                            <motion.div initial={{ scaleX: 0 }} animate={{ scaleX: location.values[r] }} transition={{ delay: .8 + index * .16 + r * .2, duration: .6, ease: EASE }} className="h-full rounded-full" style={{ background: location.accent, transformOrigin: 'left' }} />
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="mt-[1.1vh] border-t pt-[.9vh]" style={{ borderColor: '#EEF1F5', color: '#8A96A5', fontSize: '.52vw' }}>Sample pattern · not a location score</div>
                  </Panel>
                </motion.div>
              ))}
            </div>
            <div className="mt-[.85vh] flex items-center justify-between" style={{ color: '#7B8798', fontSize: '.54vw' }}>
              <span>North Room · Lantern Yard · Fieldhouse — all fictional</span>
              <span style={{ color: violet }}>Compare conversations, not winners.</span>
            </div>
          </div>
        </AppShell>
      </BrowserFrame>
    </Stage>
  );
}
