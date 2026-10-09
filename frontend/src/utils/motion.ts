export const MOTION = { fast: 140, normal: 220, slow: 280 } as const
const easing = 'cubic-bezier(0.2, 0.7, 0.2, 1)'
const running = new WeakMap<Element, Animation>()

export function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

export function cancelMotion(element: Element): void {
  running.get(element)?.cancel()
}

/** Complete Vue's hook on both finish and cancellation; never leave inline styles behind. */
export function playMotion(element: Element, frames: Keyframe[], duration: number, done: () => void): void {
  cancelMotion(element)
  if (prefersReducedMotion() || typeof element.animate !== 'function') {
    done()
    return
  }
  const animation = element.animate(frames, { duration, easing, fill: 'both' })
  running.set(element, animation)
  const finish = () => {
    // A cancelled animation may settle after a replacement has already started.
    // Its Vue hook must not finish the replacement transition.
    if (running.get(element) !== animation) return
    running.delete(element)
    animation.cancel()
    done()
  }
  void animation.finished.then(finish, finish)
}

export function enterPage(element: Element, done: () => void): void {
  playMotion(element, [
    { opacity: 0, transform: 'translateY(8px)' },
    { opacity: 1, transform: 'translateY(0)' },
  ], MOTION.normal, done)
}

export function enterItem(element: Element, done: () => void): void {
  playMotion(element, [
    { opacity: 0, transform: 'translateY(5px)' },
    { opacity: 1, transform: 'translateY(0)' },
  ], MOTION.fast, done)
}

export function leaveItem(element: Element, done: () => void): void {
  playMotion(element, [{ opacity: 1 }, { opacity: 0 }], MOTION.fast, done)
}
