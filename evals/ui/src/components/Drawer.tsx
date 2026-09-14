import { useEffect, type ReactNode } from 'react'

export default function Drawer({ title, onClose, tabs, tab, setTab, children, meta }: {
  title: ReactNode; onClose: () => void; children: ReactNode; meta?: ReactNode
  tabs?: string[]; tab?: string; setTab?: (t: string) => void
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer" role="dialog">
        <div className="drawer-head"><h2>{title}</h2>{meta}<button className="x" onClick={onClose}>Esc ✕</button></div>
        {tabs && (
          <div className="tabs">{tabs.map(t => <button key={t} className={t === tab ? 'on' : ''} onClick={() => setTab?.(t)}>{t}</button>)}</div>
        )}
        <div className="drawer-body">{children}</div>
      </div>
    </>
  )
}
