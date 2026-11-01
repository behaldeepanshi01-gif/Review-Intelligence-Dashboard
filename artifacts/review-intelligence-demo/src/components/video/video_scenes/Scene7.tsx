import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Stage, violet } from '../ShowcaseUI';

const SOURCES = [
  { label: 'Review CSV', status: 'Not supplied', detail: 'No export connected' },
  { label: 'POS export', status: 'Not supplied', detail: 'No POS file connected' },
  { label: 'Google review data', status: 'Not imported', detail: 'No Google content used' },
];

export function Scene7() {
  return (
    <Stage>
      <BrowserFrame style={{ left: '7vw', top: '8.8vh', width: '86vw', height: '82.4vh' }}>
        <AppShell title="Demo source check" subtitle="A transparent boundary for the Mumbai Central walkthrough">
          <div className="flex h-full flex-col">
            <div className="mb-[1.1vh] flex items-center justify-between">
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: .45, ease: EASE }}
                style={{ color: '#162238', fontFamily: "'Sora', sans-serif", fontSize: '1.34vw', fontWeight: 650, letterSpacing: '-.06em' }}
              >
                One location. Sample inputs only.
              </motion.div>
              <div className="rounded-full border px-[.68vw] py-[.45vh]" style={{ background: '#FCFAFF', borderColor: '#E9E1F4', color: '#705A8E', fontSize: '.54vw' }}>TARGET · NOT CONNECTED</div>
            </div>
            <motion.div
              initial={{ opacity: 0, scale: .96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: .25, duration: .5, ease: EASE }}
              className="mb-[1.2vh] flex items-center gap-[.9vw] rounded-[.75vw] border px-[1vw] py-[1.1vh]"
              style={{ background: '#fff', borderColor: '#E2E8F0' }}
            >
              <div className="flex h-[2.2vw] w-[2.2vw] items-center justify-center rounded-[.55vw]" style={{ background: '#F2EBFC', color: violet, fontFamily: "'Sora', sans-serif", fontSize: '.8vw', fontWeight: 700 }}>M</div>
              <div className="flex-1">
                <div style={{ color: '#1C293B', fontFamily: "'Sora', sans-serif", fontSize: '.86vw', fontWeight: 650 }}>Mumbai Central · Falls Church</div>
                <div style={{ color: '#758194', fontSize: '.57vw' }}>7505 VA-7 · Falls Church, VA 22043</div>
              </div>
              <div className="rounded-full px-[.7vw] py-[.55vh]" style={{ background: '#F3EEFF', color: '#65478C', fontSize: '.54vw', fontWeight: 700 }}>DEMO TARGET ONLY</div>
            </motion.div>
            <div className="grid min-h-0 flex-1 grid-cols-3 gap-[.7vw]">
              {SOURCES.map((source, index) => (
                <motion.div
                  key={source.label}
                  initial={{ opacity: 0, y: 20, scale: .98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ delay: .55 + index * .35, duration: .5, ease: EASE }}
                  className="flex flex-col justify-between rounded-[.72vw] border p-[1vw]"
                  style={{ background: '#FBFCFE', borderColor: '#E3E8EF' }}
                >
                  <div>
                    <div className="mb-[1.1vh] uppercase tracking-[.12em]" style={{ color: '#81758F', fontSize: '.51vw', fontWeight: 700 }}>SOURCE STATUS</div>
                    <div style={{ color: '#273447', fontFamily: "'Sora', sans-serif", fontSize: '.8vw', fontWeight: 600 }}>{source.label}</div>
                  </div>
                  <div>
                    <div className="mb-[.45vh] inline-flex rounded-full px-[.65vw] py-[.48vh]" style={{ background: '#F1F4F8', color: '#5E6B7E', fontSize: '.55vw', fontWeight: 700 }}>{source.status}</div>
                    <div style={{ color: '#8A96A5', fontSize: '.53vw' }}>{source.detail}</div>
                  </div>
                  <div className="h-[.25vh] w-full rounded-full" style={{ background: '#E8ECF2' }} />
                </motion.div>
              ))}
            </div>
            <motion.div
              initial={{ opacity: 0, scaleY: .8 }}
              animate={{ opacity: 1, scaleY: 1 }}
              transition={{ delay: 1.65, duration: .45, ease: EASE }}
              className="mt-[1vh] flex items-center justify-between rounded-[.5vw] px-[.8vw] py-[.65vh]"
              style={{ background: '#F7F3FD', color: '#63478D', transformOrigin: 'top', fontSize: '.57vw' }}
            >
              <span>Fictional review text, fictional names, and illustrative values only.</span>
              <span style={{ color: violet, fontWeight: 650 }}>Nothing shown here is a real performance finding.</span>
            </motion.div>
            <div className="mt-[.7vh] flex items-center gap-[.45vw]" style={{ color: '#7B8798', fontSize: '.53vw' }}>
              <span style={{ color: violet }}>↗</span> Sample content demonstrates the workflow; it does not represent restaurant data.
            </div>
          </div>
        </AppShell>
      </BrowserFrame>
    </Stage>
  );
}
