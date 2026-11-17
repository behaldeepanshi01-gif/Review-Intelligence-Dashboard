import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Stage, violet } from '../ShowcaseUI';

const THEMES = ['Food', 'Spice', 'Consistency', 'Service speed', 'Staff', 'Portions', 'Price', 'Ambiance', 'Cleanliness', 'Catering', 'Seating', 'Takeout'];
const EASE_OUT = [0.16, 1, 0.3, 1] as const;

export function Scene3() {
  return (
    <Stage tone="paper">
      <BrowserFrame style={{ left: '6.5vw', width: '87vw', top: '8vh', height: '84vh' }}>
        <AppShell title="Theme intelligence" subtitle="Mumbai Central · fictional demo example" active="Themes">
          <div className="flex h-full flex-col">
            <div className="mb-[.95vh] flex items-end justify-between">
              <div>
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE_OUT }} style={{ fontFamily: "'Sora', sans-serif", fontSize: '1.35vw', letterSpacing: '-.06em', fontWeight: 650 }}>Clear wording tags. Unclear wording asks a manager.</motion.div>
                <div className="mt-[.28vh]" style={{ color: '#64748B', fontSize: '.62vw' }}>Uncertain phrasing is flagged for manager review instead of guessing praise or a complaint.</div>
              </div>
              <div className="rounded-full border px-[.72vw] py-[.44vh]" style={{ borderColor: '#E8E2F2', color: '#6D4EA0', background: '#FBF9FF', fontSize: '.54vw' }}>SYNTHETIC EXAMPLE · NOT A REAL REVIEW</div>
            </div>
            <motion.div
              initial={{ opacity: 0, scaleY: 0.8 }}
              animate={{ opacity: 1, scaleY: 1 }}
              transition={{ delay: 0.25, duration: 0.45, ease: EASE }}
              className="mb-[.55vh] flex items-center gap-[.75vw] rounded-[.5vw] border px-[.82vw] py-[.52vh]"
              style={{ borderColor: '#E5DDF1', background: '#FCFAFF', transformOrigin: 'top' }}
            >
              <span className="whitespace-nowrap uppercase tracking-[.12em]" style={{ color: '#735B92', fontSize: '.49vw', fontWeight: 750 }}>FICTIONAL SAMPLE</span>
              <span style={{ color: '#344155', fontSize: '.66vw' }}>“The spice balance was lovely, but our first check-in took a while.”</span>
              <span className="ml-auto whitespace-nowrap rounded-full px-[.55vw] py-[.28vh]" style={{ background: '#F2EAFC', color: '#65478C', fontSize: '.49vw', fontWeight: 700 }}>Spice + Service speed</span>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, scaleY: 0.8 }}
              animate={{ opacity: 1, scaleY: 1 }}
              transition={{ delay: 0.5, duration: 0.45, ease: EASE }}
              className="mb-[.75vh] flex items-center gap-[.75vw] rounded-[.5vw] border px-[.82vw] py-[.52vh]"
              style={{ borderColor: '#F0DCC0', background: '#FFFBF5', transformOrigin: 'top' }}
            >
              <span className="whitespace-nowrap uppercase tracking-[.12em]" style={{ color: '#9A5C11', fontSize: '.49vw', fontWeight: 750 }}>FICTIONAL UNCLEAR EXAMPLE</span>
              <span style={{ color: '#344155', fontSize: '.66vw' }}>“Are the prices fair? Maybe — not sure.”</span>
              <span className="ml-auto whitespace-nowrap rounded-full px-[.55vw] py-[.28vh]" style={{ background: '#FFF0D9', color: '#9A5C11', fontSize: '.49vw', fontWeight: 700 }}>Price · Needs manager review</span>
            </motion.div>
            <div className="grid min-h-0 flex-1 grid-cols-2 gap-[.8vw]">
              {[THEMES.slice(0, 6), THEMES.slice(6)].map((column, col) => (
                <div key={col} className="flex min-h-0 flex-col justify-between gap-[.42vh]">
                  {column.map((theme, row) => {
                    const i = col * 6 + row;
                    const active = i === 1 || i === 3;
                    const needsReview = i === 6;
                    const borderColor = active ? '#D8C8F4' : needsReview ? '#F0DCC0' : '#E5EAF0';
                    const background = active ? '#F7F2FF' : needsReview ? '#FFFBF5' : '#FFFFFF';
                    const badgeBg = active ? violet : needsReview ? '#D97706' : '#F1F4F8';
                    const badgeColor = active || needsReview ? '#fff' : '#7B8798';
                    const labelColor = active ? '#4E2A84' : needsReview ? '#9A5C11' : '#273447';
                    return (
                      <motion.div
                        key={theme}
                        className="flex flex-1 items-center gap-[.82vw] rounded-[.55vw] border px-[.9vw]"
                        style={{ borderColor, background }}
                        initial={{ opacity: 0, x: col === 0 ? -18 : 18, scale: 0.98 }}
                        animate={{ opacity: 1, x: 0, scale: 1 }}
                        transition={{ delay: 0.3 + i * 0.07, duration: 0.45, ease: EASE }}
                      >
                        <div className="flex items-center justify-center rounded-[.42vw]" style={{ width: '1.5vw', height: '1.5vw', background: badgeBg, color: badgeColor, fontSize: '.54vw', fontFamily: 'monospace' }}>{String(i + 1).padStart(2, '0')}</div>
                        <div className="flex-1" style={{ color: labelColor, fontSize: '.7vw', fontWeight: 600 }}>{theme}</div>
                        <motion.div className="flex items-center gap-[.25vw]" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.5 + i * 0.09 }}>
                          {[0, 1, 2].map((n) => (
                            <span
                              key={n}
                              className="rounded-full"
                              style={{
                                width: '.46vw',
                                height: '.46vw',
                                background: active
                                  ? ['#B99AE8', '#986DDC', '#7C3AED'][n]
                                  : needsReview
                                    ? ['#FCD34D', '#F59E0B', '#D97706'][n]
                                    : '#D8DEE8',
                              }}
                            />
                          ))}
                        </motion.div>
                        <div style={{ color: needsReview ? '#9A5C11' : '#8A96A5', fontSize: '.51vw', fontWeight: needsReview ? 700 : 400 }}>
                          {needsReview ? 'Needs manager review' : active ? 'tagged' : 'sample tags'}
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              ))}
            </div>
            <div className="mt-[.75vh] flex items-center justify-between" style={{ color: '#81758F', fontSize: '.54vw' }}>
              <span>All 12 product themes · synthetic examples · not from Mumbai Central</span>
              <motion.span animate={{ color: ['#64748B', violet, violet] }} transition={{ delay: 4, duration: 1.1 }}>Clear → Spice + Service speed · Unclear → Price (manager review) ↗</motion.span>
            </div>
          </div>
        </AppShell>
      </BrowserFrame>
    </Stage>
  );
}
