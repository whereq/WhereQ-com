import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

export interface NotificationDTO {
  id: number
  user_id: number
  title: string
  body: string | null
  kind: string
  is_read: boolean
  created_at: string
}

export function useNotifications() {
  const [notifications, setNotifications] = useState<NotificationDTO[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)

  const fetch = useCallback(async () => {
    if (!isAuthenticated()) return
    setLoading(true)
    try {
      const [notifs, countRes] = await Promise.all([
        api.get<NotificationDTO[]>('/notifications'),
        api.get<{ count: number }>('/notifications/unread-count'),
      ])
      setNotifications(notifs)
      setUnreadCount(countRes.count)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const markRead = useCallback(async (id: number) => {
    await api.patch<NotificationDTO>(`/notifications/${id}/read`)
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
    setUnreadCount(prev => Math.max(0, prev - 1))
  }, [])

  const markAllRead = useCallback(async () => {
    await api.post('/notifications/read-all')
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
    setUnreadCount(0)
  }, [])

  const dismiss = useCallback(async (id: number) => {
    await api.delete(`/notifications/${id}`)
    setNotifications(prev => prev.filter(n => n.id !== id))
    setUnreadCount(prev => {
      const wasUnread = notifications.find(n => n.id === id && !n.is_read)
      return wasUnread ? Math.max(0, prev - 1) : prev
    })
  }, [notifications])

  return { notifications, unreadCount, loading, markRead, markAllRead, dismiss, refresh: fetch }
}
