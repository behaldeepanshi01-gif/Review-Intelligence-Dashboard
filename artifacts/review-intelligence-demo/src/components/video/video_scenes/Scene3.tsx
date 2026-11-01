import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Stage, violet } from '../ShowcaseUI';

const THEMES = ['Food', 'Spice', 'Consistency', 'Service speed', 'Staff', 'Portions', 'Price', 'Ambiance', 'Cleanliness', 'Catering', 'Seating', 'Takeout'];
const EASE_OUT = [0.16, 1, 0.3, 1] as const;

export function Scene3() {
  return (
    <Stage tone="paper">
      <BrowserFrame style={{ left: '6.5vw', width: '87vw', top: '8vh', height: '84vh' }}>
        <AppShell title="Theme intelligence" subtitle="Feedback becomes easier to read when it has a shape." active="Themes">
          <div className="flex h-full flex-col">
            <div className="mb-[1.25vh] flex items-end justify-between">
              <div>
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE_OUT }} style={{ fontFamily: "'Sora', sans-serif", fontSize: '1.45vw', letterSpacing: '-.06em', fontWeight: 650 }}>Twelve themes. One pattern.</motion.div>
                <div className="mt-[.35vh]" style={{ color: '#64748B', fontSize: '.65vw' }}>Tags bring related notes into the same conversation.</div>
              </div>
              <div className="rounded-full border px-[.72vw] py-[.48vh]" style={{ borderColor: '#E8E2F2', color: '#6D4EA0', background: '#FBF9FF', fontSize: '.56vw' }}>12 topic tags</div>
            </div>
            <div className="grid min-h-0 flex-1 grid-cols-2 gap-[.8vw]">
              {[THEMES.slice(0, 6), THEMES.slice(6)].map((column, col) => (
                <div key={col} className="flex min-h-0 flex-col justify-between gap-[.48vh]">
                  {column.map((theme, row) => {
                    const i = col * 6 + row;
                    const active = i === 1;
                    return (
                      <motion.div
                        key={theme}
                        className="flex flex-1 items-center gap-[.82vw] rounded-[.55vw] border px-[.9vw]"
                        style={{ borderColor: active ? '#D8C8F4' : '#E5EAF0', background: active ? '#F7F2FF' : '#FFFFFF' }}
                        initial={{ opacity: 0, x: col === 0 ? -18 : 18, scale: 0.98 }}
                        animate={{ opacity: 1, x: 0, scale: 1 }}
                        transition={{ delay: 0.3 + i * 0.07, duration: 0.45, ease: EASE }}
                      >
                        <div className="flex items-center justify-center rounded-[.42vw]" style={{ width: '1.55vw', height: '1.55vw', background: active ? violet : '#F1F4F8', color: active ? '#fff' : '#7B8798', fontSize: '.55vw', fontFamily: 'monospace' }}>{String(i + 1).padStart(2, '0')}</div>
                        <div className="flex-1" style={{ color: active ? '#4E2A84' : '#273447', fontSize: '.72vw', fontWeight: 600 }}>{theme}</div>
                        <motion.div className="flex items-center gap-[.25vw]" initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.5 + i * 0.09 }}>
                          {[0, 1, 2].map((n) => <span key={n} className="rounded-full" style={{ width: '.48vw', height: '.48vw', background: active ? ['#B99AE8', '#986DDC', '#7C3AED'][n] : '#D8DEE8' }} />)}
                        </motion.div>
                        <div style={{ color: '#8A96A5', fontSize: '.52vw' }}>sample tags</div>
                      </motion.div>
                    );
                  })}
                </div>
              ))}
            </div>
            <div className="mt-[.9vh] flex items-center justify-between" style={{ color: '#81758F', fontSize: '.55vw' }}>
              <span>Illustrative demo · synthetic sample data</span>
              <motion.span animate={{ color: ['#64748B', violet, violet] }} transition={{ delay: 4, duration: 1.1 }}>Spice mentions are beginning to cluster ↗</motion.span>
            </div>
          </div>
        </AppShell>
      </BrowserFrame>
    </Stage>
  );
}
