import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Panel, Stage, StatCard, TinyAvatar, violet } from '../ShowcaseUI';

const rows = [
  ['Food', 'Sample note tagged', 'All locations'],
  ['Service speed', 'Trend to review', 'Recent sample'],
  ['Staff', 'Praise by name', '2 mentions'],
  ['Ambiance', 'Theme captured', 'Illustrative'],
];

export function Scene2() {
  return (
    <Stage>
      <BrowserFrame>
        <AppShell title="Overview" subtitle="A clear read on guest feedback">
          <motion.div className="flex h-full flex-col gap-[1.2vh]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.45 }}>
            <motion.div className="grid grid-cols-4 gap-[.65vw]" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.45, ease: EASE }}>
              <StatCard label="Sample reviews" value="128" detail="Illustrative value" />
              <StatCard label="Themes tagged" value="12" detail="Across the demo" />
              <StatCard label="Needs a look" value="02" detail="Rising sample themes" accent="#B45309" />
              <StatCard label="Reply drafts" value="04" detail="Manager review" accent="#4F46A5" />
            </motion.div>
            <div className="grid min-h-0 flex-1 grid-cols-[1.17fr_.83fr] gap-[.72vw]">
              <motion.div className="min-h-0" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.8, duration: 0.5, ease: EASE }}>
                <Panel className="h-full" title="Recent sample activity" eyebrow="Illustrative feed">
                  <div className="flex min-h-0 flex-1 flex-col justify-between">
                    {rows.map(([tag, detail, loc], i) => (
                      <div key={tag} className="flex items-center gap-[.7vw] border-t py-[.8vh]" style={{ borderColor: '#EEF1F5' }}>
                        <TinyAvatar initials={['F', 'S', 'T', 'A'][i]} color={['#F3EEFF', '#FFF4E5', '#EFF6FF', '#ECFDF5'][i]} />
                        <div className="min-w-0 flex-1">
                          <div style={{ color: '#263245', fontSize: '.65vw', fontWeight: 600 }}>{tag}</div>
                          <div style={{ color: '#8994A4', fontSize: '.55vw' }}>{detail}</div>
                        </div>
                        <div className="rounded-full px-[.55vw] py-[.42vh]" style={{ background: '#F1F4F8', color: '#64748B', fontSize: '.51vw' }}>{loc}</div>
                      </div>
                    ))}
                  </div>
                </Panel>
              </motion.div>
              <motion.div className="min-h-0" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1, duration: 0.5, ease: EASE }}>
                <Panel className="h-full" title="Themes in this sample" eyebrow="Across locations">
                  <div className="mb-[.9vh] flex items-center justify-between" style={{ color: '#8A96A5', fontSize: '.53vw' }}><span>Illustrative mention pattern</span><span>Sample</span></div>
                  <div className="flex min-h-0 flex-1 flex-col justify-between">
                    {['Food', 'Service speed', 'Staff', 'Price', 'Ambiance'].map((label, i) => (
                      <div key={label} className="flex items-center gap-[.5vw]">
                        <div style={{ width: '4.7vw', color: '#526073', fontSize: '.56vw' }}>{label}</div>
                        <div className="h-[.75vh] flex-1 overflow-hidden rounded-full" style={{ background: '#EEF2F6' }}>
                          <motion.div className="h-full rounded-full" style={{ background: i === 1 ? '#7C3AED' : '#C9BEDB', transformOrigin: 'left' }} initial={{ scaleX: 0 }} animate={{ scaleX: [0, [0.74, 0.48, 0.62, 0.35, 0.25][i]] }} transition={{ delay: 1.1 + i * 0.12, duration: 0.7, ease: EASE }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-[.9vh] flex items-center gap-[.35vw]" style={{ color: violet, fontSize: '.52vw', fontWeight: 600 }}><span>↗</span>Patterns, not isolated comments</div>
                </Panel>
              </motion.div>
            </div>
          </motion.div>
        </AppShell>
      </BrowserFrame>
      <div className="absolute left-[4.5vw] top-[46vh] z-20 max-w-[10vw]" style={{ color: '#5D4B78', fontSize: '.72vw', lineHeight: 1.5 }}>
        One view.<br /><strong style={{ color: violet }}>Every location.</strong>
      </div>
    </Stage>
  );
}
