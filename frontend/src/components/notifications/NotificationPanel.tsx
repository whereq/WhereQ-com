import { useState, useRef, useEffect } from 'react'
import { useNotifications, NotificationDTO } from '@/hooks/useNotifications'
import { useAuth } from '@/contexts/AuthContext'

const KIND_COLORS: Record<string, string> = {
  info: 'var(--accent)',
  friend: 'var(--social)',
  route: 'var(--info)',
  memorial: 'var(--memorial)',
  system: 'var(--muted)',
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function NotificationPanel() {
  const { user } = useAuth()
  const { notifications, unreadCount, markRead, markAllRead, dismiss } = useNotifications()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (!user) {
    return (
      <button className="icon-btn" title="Notifications">
        <BellIcon />
      </button>
    )
  }

  return (
    <div className="notif-panel" ref={ref}>
      <button className="icon-btn" title="Notifications" onClick={() => setOpen(!open)}>
        <BellIcon />
        {unreadCount > 0 && <span className="notif-dot">{unreadCount > 9 ? '9+' : unreadCount}</span>}
      </button>

      {open && (
        <div className="notif-dropdown">
          <div className="notif-dropdown-hd">
            <span>Notifications</span>
            {unreadCount > 0 && (
              <button className="notif-mark-all" onClick={markAllRead}>Mark all read</button>
            )}
          </div>
          <div className="notif-dropdown-body">
            {notifications.length === 0 && (
              <div className="notif-empty">No notifications</div>
            )}
            {notifications.map(n => (
              <NotifItem key={n.id} notif={n} onRead={markRead} onDismiss={dismiss} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function NotifItem({ notif, onRead, onDismiss }: {
  notif: NotificationDTO
  onRead: (id: number) => void
  onDismiss: (id: number) => void
}) {
  return (
    <div
      className={`notif-item${notif.is_read ? '' : ' unread'}`}
      onClick={() => !notif.is_read && onRead(notif.id)}
    >
      <span className="notif-item-dot" style={{ background: KIND_COLORS[notif.kind] || 'var(--muted)' }} />
      <div className="notif-item-content">
        <div className="notif-item-title">{notif.title}</div>
        {notif.body && <div className="notif-item-body">{notif.body}</div>}
        <div className="notif-item-time">{timeAgo(notif.created_at)}</div>
      </div>
      <button className="notif-item-close" onClick={e => { e.stopPropagation(); onDismiss(notif.id) }}>&times;</button>
    </div>
  )
}

function BellIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21a2 2 0 0 0 4 0" />
    </svg>
  )
}
