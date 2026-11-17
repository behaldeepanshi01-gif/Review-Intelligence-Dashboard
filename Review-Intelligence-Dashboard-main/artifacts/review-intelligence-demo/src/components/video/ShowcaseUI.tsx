import type { CSSProperties, ReactNode } from 'react';
import { motion } from 'framer-motion';

export const ink = '#0F172A';
export const muted = '#64748B';
export const violet = '#7C3AED';
export const line = '#E2E8F0';
export const panel = '#FBFCFE';
export const EASE = [0.16, 1, 0.3, 1] as const;

export function Stage({ children, tone = 'fog' }: { children: ReactNode; tone?: 'fog' | 'paper' | 'ink' }) {
  const background = tone === 'ink' ? '#172238' : tone === 'paper' ? '#F9FAFC' : '#EEF2F6';
  return (
    <motion.section
      className="absolute inset-0 overflow-hidden"
      style={{ backgroundColor: background }}
      initial={{ opacity: 0, scale: 1.025, filter: 'blur(5px)' }}
      animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
      exit={{ opacity: 0, scale: 0.985, filter: 'blur(4px)' }}
      transition={{ duration: 0.45, ease: EASE }}
    >
      {tone !== 'ink' && <div className="absolute inset-0 micro-grid opacity-70" />}
      <div className="video-grain absolute inset-0" />
      {children}
    </motion.section>
  );
}

export function BrowserFrame({
  children,
  className = '',
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <motion.div
      className={`ui-shadow absolute overflow-hidden rounded-[1.2vw] border ${className}`}
      style={{
        left: '9.3vw',
        top: '10.2vh',
        width: '81.4vw',
        height: '79.6vh',
        background: '#fff',
        borderColor: '#DCE3EB',
        ...style,
      }}
      initial={{ opacity: 0, y: 36, scale: 0.94 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.72, ease: EASE }}
    >
      <div
        className="flex items-center gap-[.52vw] border-b px-[1.15vw]"
        style={{ height: '4.25vh', borderColor: line, background: '#fff' }}
      >
        {['#FCA5A5', '#FCD34D', '#86EFAC'].map((color) => (
          <span key={color} className="rounded-full" style={{ width: '.58vw', height: '.58vw', background: color }} />
        ))}
        <div
          className="ml-[.62vw] rounded px-[.7vw] py-[.24vh] font-medium"
          style={{ color: muted, background: '#F1F4F8', fontSize: '.63vw', letterSpacing: '.01em' }}
        >
          demo.review-intelligence.local
        </div>
        <div className="ml-auto flex items-center gap-[.4vw]">
          <span className="rounded-full" style={{ width: '.32vw', height: '.32vw', background: '#16A34A' }} />
          <span style={{ color: '#64748B', fontSize: '.61vw' }}>Offline engine</span>
        </div>
      </div>
      <div className="h-[calc(100%-4.25vh)]">{children}</div>
    </motion.div>
  );
}

const NAV = [
  ['Overview', '◫'],
  ['Themes', '◎'],
  ['Trends', '↗'],
  ['Team', '✳'],
  ['Replies', '↳'],
];

export function AppShell({
  children,
  title = 'Overview',
  subtitle = 'A clear read on guest feedback',
  active = 'Overview',
  compact = false,
}: {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  active?: string;
  compact?: boolean;
}) {
  return (
    <div className="flex h-full min-h-0" style={{ color: ink, fontFamily: "'Inter', sans-serif" }}>
      <aside
        className="flex h-full shrink-0 flex-col border-r px-[1.1vw] py-[1.7vh]"
        style={{ width: '16.2%', borderColor: line, background: '#FCFDFE' }}
      >
        <div className="mb-[3.1vh] flex items-center gap-[.58vw]">
          <div className="flex items-center justify-center rounded-[.48vw]" style={{ width: '1.8vw', height: '1.8vw', color: '#fff', background: violet, fontFamily: "'Sora', sans-serif", fontSize: '.8vw', fontWeight: 700 }}>R</div>
          <div>
            <div style={{ fontSize: '.76vw', fontWeight: 700, letterSpacing: '-.03em' }}>Review Intelligence</div>
            <div style={{ color: muted, fontSize: '.55vw' }}>OWNER WORKSPACE</div>
          </div>
        </div>
        <div className="mb-[.8vh] uppercase tracking-[.12em]" style={{ color: '#94A3B8', fontSize: '.48vw', fontWeight: 700 }}>Demo target</div>
        <div className="mb-[2.4vh] rounded-[.48vw] border px-[.65vw] py-[.68vh]" style={{ borderColor: line, background: '#fff', fontSize: '.65vw', fontWeight: 600 }}>
          Mumbai Central <span className="float-right" style={{ color: muted }}>⌄</span>
          <div className="mt-[.35vh]" style={{ color: muted, fontSize: '.52vw', fontWeight: 400 }}>7505 VA-7 · Falls Church, VA 22043</div>
        </div>
        <div className="flex flex-col gap-[.34vh]">
          {NAV.map(([item, glyph]) => (
            <div
              key={item}
              className="flex items-center gap-[.65vw] rounded-[.48vw] px-[.7vw] py-[.9vh]"
              style={{ color: active === item ? violet : '#475569', background: active === item ? '#F3EEFF' : 'transparent', fontSize: '.66vw', fontWeight: active === item ? 650 : 500 }}
            >
              <span style={{ width: '.9vw', textAlign: 'center', fontSize: '.8vw' }}>{glyph}</span>{item}
              {item === 'Trends' && <span className="ml-auto rounded-full px-[.35vw]" style={{ background: '#FFF7ED', color: '#B45309', fontSize: '.49vw' }}>2</span>}
            </div>
          ))}
        </div>
        <div className="mt-auto rounded-[.6vw] border p-[.75vw]" style={{ borderColor: '#E9E4F4', background: '#FAF8FF' }}>
          <div style={{ color: violet, fontSize: '.56vw', fontWeight: 700 }}>DEMO MODE</div>
          <div className="mt-[.4vh]" style={{ color: '#475569', fontSize: '.58vw', lineHeight: 1.45 }}>Fictional examples only. No venue reviews connected.</div>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col px-[1.65vw] py-[1.55vh]">
        <header className="mb-[1.45vh] flex items-center justify-between">
          <div>
            <div style={{ fontFamily: "'Sora', sans-serif", fontSize: compact ? '1.05vw' : '1.22vw', fontWeight: 650, letterSpacing: '-.04em' }}>{title}</div>
            <div className="mt-[.32vh]" style={{ color: muted, fontSize: '.61vw' }}>{subtitle}</div>
          </div>
          <div className="flex items-center gap-[.58vw]">
            <div className="rounded-full border px-[.85vw] py-[.72vh]" style={{ borderColor: line, color: muted, background: '#fff', fontSize: '.59vw' }}>⌕ &nbsp; Search feedback</div>
            <div className="rounded-[.45vw] px-[.85vw] py-[.72vh]" style={{ color: '#fff', background: violet, fontSize: '.6vw', fontWeight: 600 }}>Weekly brief</div>
            <div className="flex items-center justify-center rounded-full" style={{ width: '1.65vw', height: '1.65vw', color: '#5B3D8A', background: '#EDE5F8', fontSize: '.58vw', fontWeight: 700 }}>OW</div>
          </div>
        </header>
        <div className="mb-[1.25vh] flex items-center justify-between rounded-[.42vw] border px-[.7vw] py-[.58vh]" style={{ borderColor: '#E8E2F2', background: '#FBF9FF', fontSize: '.58vw' }}>
          <span style={{ color: '#665783' }}>DEMO TARGET ONLY · Mumbai Central · No live data connected</span>
          <span style={{ color: muted }}>No CSV or POS export supplied</span>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
      </main>
    </div>
  );
}

export function StatCard({ label, value, detail, accent = violet }: { label: string; value: string; detail: string; accent?: string }) {
  return (
    <div className="rounded-[.66vw] border p-[.9vw]" style={{ borderColor: line, background: '#fff' }}>
      <div style={{ color: muted, fontSize: '.57vw' }}>{label}</div>
      <div className="mt-[.58vh]" style={{ color: ink, fontFamily: "'Sora', sans-serif", fontSize: '1.28vw', fontWeight: 650, letterSpacing: '-.06em' }}>{value}</div>
      <div className="mt-[.42vh]" style={{ color: accent, fontSize: '.54vw', fontWeight: 600 }}>{detail}</div>
    </div>
  );
}

export function Panel({ children, title, eyebrow, className = '', style }: { children: ReactNode; title?: string; eyebrow?: string; className?: string; style?: CSSProperties }) {
  return (
    <div className={`flex min-h-0 flex-col rounded-[.7vw] border p-[.9vw] ${className}`} style={{ borderColor: line, background: panel, ...style }}>
      {(title || eyebrow) && (
        <div className="mb-[1vh]">
          {eyebrow && <div className="mb-[.35vh] uppercase tracking-[.11em]" style={{ color: violet, fontSize: '.49vw', fontWeight: 700 }}>{eyebrow}</div>}
          {title && <div style={{ color: ink, fontFamily: "'Sora', sans-serif", fontSize: '.75vw', fontWeight: 600, letterSpacing: '-.03em' }}>{title}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export function TinyAvatar({ initials, color = '#EFE8FC' }: { initials: string; color?: string }) {
  return <div className="flex shrink-0 items-center justify-center rounded-full" style={{ width: '1.7vw', height: '1.7vw', background: color, color: '#58417A', fontSize: '.54vw', fontWeight: 700 }}>{initials}</div>;
}

export function DemoStamp({ children = 'SYNTHETIC SAMPLE DATA' }: { children?: string }) {
  return (
    <div className="absolute bottom-[3.7vh] right-[4vw] z-20 rounded-full border px-[.8vw] py-[.45vh] tracking-[.12em]" style={{ borderColor: 'rgba(124,58,237,.22)', color: '#6D4EA0', background: 'rgba(255,255,255,.82)', fontSize: '.55vw', fontWeight: 650 }}>
      {children}
    </div>
  );
}
