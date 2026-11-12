import { useEffect, useRef, useState } from 'react'

function easeOutQuart(t: number) {
  return 1 - Math.pow(1 - t, 4)
}

export function useCountUp(target: number, duration = 2000, suffix = '') {
  const [display, setDisplay] = useState('0' + suffix)
  const observed = useRef(false)
  const ref = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && !observed.current) {
        observed.current = true
        observer.disconnect()

        const start = performance.now()
        const tick = (now: number) => {
          const elapsed = now - start
          const progress = Math.min(elapsed / duration, 1)
          const value = Math.round(easeOutQuart(progress) * target)
          setDisplay(
            target >= 1_000_000
              ? (value / 1_000_000).toFixed(1) + 'M' + suffix
              : target >= 1_000
              ? (value / 1_000).toFixed(0) + 'K' + suffix
              : value + suffix
          )
          if (progress < 1) requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      }
    }, { threshold: 0.3 })

    observer.observe(el)
    return () => observer.disconnect()
  }, [target, duration, suffix])

  return { ref, display }
}
