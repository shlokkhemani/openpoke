import type { HistoryItem } from '../api'

export default function Chat({ history, turns }: { history?: HistoryItem[]; turns?: string[] }) {
  return (
    <div className="chat">
      {(history ?? []).map((h, i) =>
        h.filler ? (
          <div key={i} className="bubble filler">… N tokens of unrelated chat inserted here at size N …</div>
        ) : (
          <div key={i} className={`bubble ${h.role}`}>
            <span className="who">{h.role === 'user' ? 'user' : h.role === 'reply' ? 'poke' : 'worker callback'}</span>
            {typeof h.content === 'string' ? h.content : (
              <i>{h.content?.prefix ?? ''}… generated {h.content?.generate} ({h.content?.company ?? ''}{h.content?.terms ? `, ${Object.values(h.content.terms).join(' / ')}` : ''}), {String(h.content?.tokens)} tokens …</i>
            )}
          </div>
        ),
      )}
      {(turns ?? []).map((t, i) => (
        <div key={`t${i}`} className="bubble probe"><span className="who">turn {i + 1} (sent during the run)</span>{t}</div>
      ))}
    </div>
  )
}
