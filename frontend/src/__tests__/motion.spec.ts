import { afterEach, describe, expect, it, vi } from 'vitest'
import { cancelMotion, enterPage } from '../utils/motion'

afterEach(() => vi.unstubAllGlobals())

function animatedElement() {
  const element = document.createElement('div')
  const animations: { finish: () => void; cancel: ReturnType<typeof vi.fn> }[] = []
  const animate = vi.fn(() => {
    let finish!: () => void
    let reject!: () => void
    const finished = new Promise<void>((resolve, fail) => { finish = resolve; reject = fail })
    const cancel = vi.fn(() => reject())
    animations.push({ finish, cancel })
    return { finished, cancel } as unknown as Animation
  })
  element.animate = animate
  return { element, animations, animate }
}

describe('motion lifecycle', () => {
  it('does not let a cancelled hook finish the replacement animation', async () => {
    const { element, animations } = animatedElement()
    const firstDone = vi.fn()
    const nextDone = vi.fn()
    enterPage(element, firstDone)
    enterPage(element, nextDone)
    await Promise.resolve()
    expect(firstDone).not.toHaveBeenCalled()
    expect(nextDone).not.toHaveBeenCalled()
    expect(animations[1]!.cancel).not.toHaveBeenCalled()
    cancelMotion(element)
    await Promise.resolve()
    expect(nextDone).toHaveBeenCalledTimes(1)
  })

  it('removes finished effects so revisiting a view starts cleanly', async () => {
    const { element, animations } = animatedElement()
    const done = vi.fn()
    enterPage(element, done)
    animations[0]!.finish()
    await Promise.resolve()
    expect(done).toHaveBeenCalledTimes(1)
    expect(animations[0]!.cancel).toHaveBeenCalledTimes(1)
    cancelMotion(element)
    expect(animations[0]!.cancel).toHaveBeenCalledTimes(1)
  })

  it('applies the final state immediately when Windows reduces motion', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const { element, animate } = animatedElement()
    const done = vi.fn()
    enterPage(element, done)
    expect(animate).not.toHaveBeenCalled()
    expect(done).toHaveBeenCalledTimes(1)
  })
})
