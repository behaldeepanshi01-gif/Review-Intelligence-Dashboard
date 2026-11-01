import { motion } from 'framer-motion';
import { AppShell, BrowserFrame, EASE, Panel, Stage, TinyAvatar, violet } from '../ShowcaseUI';

const PEOPLE = [
  { name: 'Maya Chen', role: 'Fictional team member', initials: 'MC', note: 'Warm welcome at the door.', tint: '#F3EEFF' },
  { name: 'Jonah Reed', role: 'Fictional team member', initials: 'JR', note: 'Checked in at just the right time.', tint: '#FFF3E5' },
];

export function Scene5() {
  return (
    <Stage tone="paper">
      <BrowserFrame style={{ left: '10vw', top: '11vh', width: '80vw', height: '78vh' }}>
        <AppShell title="Team signals" subtitle="Notice who guests are mentioning" active="Team">
          <div className="grid h-full grid-cols-[.7fr_1.3fr] gap-[1vw]">
            <div className="flex flex-col justify-center pr-[1.2vw]">
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }} className="mb-[1.4vh] uppercase tracking-[.13em]" style={{ color: violet, fontSize: '.61vw', fontWeight: 700 }}>STAFF PRAISE</motion.div>
              <motion.h2 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24, duration: 0.5, ease: EASE }} className="m-0" style={{ color: '#142035', fontFamily: "'Sora', sans-serif", fontSize: '2.2vw', lineHeight: 1.12, letterSpacing: '-.065em' }}>Names worth<br />noticing.</motion.h2>
              <motion.div initial={{ opacity: 0, scaleX: 0 }} animate={{ opacity: 1, scaleX: 1 }} transition={{ delay: 0.9, duration: 0.5 }} className="mt-[1.5vh] h-[.32vh] w-[7vw] origin-left rounded-full" style={{ background: violet }} />
              <p className="mt-[1.6vh] max-w-[19vw]" style={{ color: '#64748B', fontSize: '.78vw', lineHeight: 1.55 }}>A human signal for a team huddle, not just a star rating.</p>
              <div className="mt-[1.5vh] rounded-full border px-[.7vw] py-[.55vh] self-start" style={{ borderColor: '#E9E1F4', color: '#705A8E', background: '#FCFAFF', fontSize: '.54vw' }}>Fictional names · synthetic feedback</div>
            </div>
            <div className="flex flex-col justify-center gap-[1.25vh]">
              {PEOPLE.map((person, i) => (
                <motion.div
                  key={person.name}
                  className="ui-shadow rounded-[.8vw] border p-[1.1vw]"
                  style={{ background: '#fff', borderColor: '#E3E8EF' }}
                  initial={{ opacity: 0, x: 36, rotate: i ? 1.5 : -1 }}
                  animate={{ opacity: 1, x: 0, rotate: 0 }}
                  transition={{ delay: 0.4 + i * 0.42, duration: 0.58, ease: EASE }}
                >
                  <div className="flex items-center gap-[.8vw]">
                    <TinyAvatar initials={person.initials} color={person.tint} />
                    <div className="flex-1">
                      <div style={{ color: '#233044', fontFamily: "'Sora', sans-serif", fontSize: '.88vw', fontWeight: 650 }}>{person.name}</div>
                      <div style={{ color: '#8A96A5', fontSize: '.56vw' }}>{person.role}</div>
                    </div>
                    <div className="rounded-full px-[.7vw] py-[.52vh]" style={{ color: '#674493', background: '#F3EEFB', fontSize: '.57vw', fontWeight: 650 }}>Staff praise</div>
                  </div>
                  <div className="mt-[1.2vh] border-t pt-[1.2vh]" style={{ borderColor: '#EEF1F5', color: '#4A586B', fontSize: '.78vw' }}>
                    <span style={{ color: violet, fontFamily: "'Sora', sans-serif", fontSize: '1.35vw' }}>“</span> {person.note}
                  </div>
                </motion.div>
              ))}
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.9, duration: 0.45 }} className="flex items-center gap-[.55vw] pl-[.3vw]" style={{ color: '#6B788B', fontSize: '.61vw' }}>
                <span style={{ color: violet }}>✳</span> A positive note can make the next team conversation more specific.
              </motion.div>
            </div>
          </div>
        </AppShell>
      </BrowserFrame>
    </Stage>
  );
}
