import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Stage, violet } from '../ShowcaseUI';

const DRAFT = [
  'Thank you for letting us know.',
  'We appreciate you sharing your experience.',
  'Our team would value the chance to make your next visit feel more considered.',
];

export function Scene6() {
  return (
    <Stage>
      <BrowserFrame style={{ left: '8vw', top: '9vh', width: '84vw', height: '82vh' }}>
        <AppShell title="Reply workspace" subtitle="Fictional sample input · no reply sent" active="Replies">
          <div className="grid h-full grid-cols-[.85fr_1.15fr] gap-[.9vw]">
            <motion.div initial={{ opacity: 0, x: -18 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: .45, ease: EASE }} className="flex flex-col rounded-[.8vw] border p-[1.2vw]" style={{ background: '#fff', borderColor: '#E2E8F0' }}>
              <div className="mb-[1.2vh] flex items-center justify-between">
                <div className="uppercase tracking-[.13em]" style={{ color: '#7A6A90', fontSize: '.54vw', fontWeight: 700 }}>FICTIONAL SAMPLE · NOT A REAL REVIEW</div>
                <span className="rounded-full px-[.55vw] py-[.4vh]" style={{ background: '#FFF5E8', color: '#9A5C11', fontSize: '.5vw' }}>Spice + service speed</span>
              </div>
              <div style={{ color: '#253247', fontFamily: "'Sora', sans-serif", fontSize: '1.18vw', lineHeight: 1.43, letterSpacing: '-.04em' }}>
                The spice balance was lovely, but our first check-in took a while.
              </div>
              <div className="mt-auto border-t pt-[1vh]" style={{ borderColor: '#EEF1F5', color: '#8A96A5', fontSize: '.55vw' }}>Synthetic wording · not from Mumbai Central</div>
            </motion.div>
            <div className="relative flex flex-col rounded-[.8vw] border p-[1.2vw]" style={{ borderColor: '#DCCCF4', background: '#FCFAFF' }}>
              <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .3, duration: .4 }} className="flex items-center justify-between border-b pb-[1vh]" style={{ borderColor: '#E9E1F4' }}>
                <div>
                  <div className="uppercase tracking-[.12em]" style={{ color: violet, fontSize: '.52vw', fontWeight: 700 }}>SYNTHETIC SUGGESTED RESPONSE</div>
                  <div className="mt-[.45vh]" style={{ color: '#263247', fontFamily: "'Sora', sans-serif", fontSize: '.9vw', fontWeight: 650 }}>A thoughtful first draft.</div>
                </div>
                <span className="rounded-full border px-[.62vw] py-[.48vh]" style={{ borderColor: '#DFD2F2', color: '#685184', background: '#fff', fontSize: '.52vw' }}>Draft for manager review</span>
              </motion.div>
              <div className="flex flex-1 flex-col justify-center gap-[1.1vh] py-[1.2vh]">
                {DRAFT.map((line, i) => (
                  <motion.div key={line} initial={{ opacity: 0, y: 10, clipPath: 'inset(0 100% 0 0)' }} animate={{ opacity: 1, y: 0, clipPath: 'inset(0 0% 0 0)' }} transition={{ delay: .75 + i * .6, duration: .55, ease: EASE }} style={{ color: '#344155', fontSize: '.83vw', lineHeight: 1.45 }}>{line}</motion.div>
                ))}
              </div>
              <motion.div initial={{ opacity: 0, scale: .88 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 3.2, duration: .42, ease: EASE }} className="flex items-center justify-between border-t pt-[1vh]" style={{ borderColor: '#E9E1F4' }}>
                <div style={{ color: '#6E7B8C', fontSize: '.59vw' }}>Manager reviews before sending.</div>
                <div className="rounded-[.45vw] px-[.85vw] py-[.62vh]" style={{ background: violet, color: '#fff', fontSize: '.59vw', fontWeight: 650 }}>Approve draft</div>
              </motion.div>
              <motion.div initial={{ opacity: 0, scale: .6, rotate: -18 }} animate={{ opacity: 1, scale: 1, rotate: 0 }} transition={{ delay: 4.4, duration: .55, ease: EASE }} className="absolute -right-[.6vw] -top-[.45vh] flex h-[4.4vw] w-[4.4vw] items-center justify-center rounded-full border-[.18vw]" style={{ borderColor: '#A884D7', color: '#6B4799', background: 'rgba(255,255,255,.9)', fontSize: '.5vw', fontWeight: 800, textAlign: 'center', letterSpacing: '.08em' }}>MANAGER<br />REVIEW</motion.div>
            </div>
          </div>
        </AppShell>
      </BrowserFrame>
      <div className="absolute bottom-[3.4vh] left-[7vw] z-20" style={{ color: '#64748B', fontSize: '.68vw' }}>
        AI helps shape a reply. <strong style={{ color: violet }}>A person stays in control.</strong>
      </div>
    </Stage>
  );
}
