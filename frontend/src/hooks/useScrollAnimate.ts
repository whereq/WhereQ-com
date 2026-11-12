import { useEffect } from 'react'

export function useScrollAnimate() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const el = entry.target as HTMLElement
            const delay = el.dataset.delay ? parseInt(el.dataset.delay) : 0
            setTimeout(() => el.classList.add('visible'), delay)
            observer.unobserve(el)
          }
        })
      },
      { threshold: 0.12 }
    )

    const targets = document.querySelectorAll('[data-animate]')
    targets.forEach(el => observer.observe(el))

    return () => observer.disconnect()
  }, [])
}
