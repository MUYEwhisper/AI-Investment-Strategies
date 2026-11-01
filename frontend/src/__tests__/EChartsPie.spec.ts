import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import EChartsPie from '../components/EChartsPie.vue'

const items = ['创投', '核电', '有色金属概念'].map((name, index) => ({ name, value: index + 1 }))
const wrappers: VueWrapper[] = []

function mountChart() {
  const chart = mount(EChartsPie, { props: { items, seriesName: '资金关注度' } })
  wrappers.push(chart)
  return chart
}

beforeEach(() => {
  vi.stubGlobal('echarts', { init: () => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() }) })
})

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
})

describe('HTML chart legend', () => {
  it('pages through visible names and keeps the two charts independent', async () => {
    const first = mountChart()
    const second = mountChart()
    await flushPromises()
    expect(first.get('button[aria-label="资金关注度上一页"]').attributes('disabled')).toBeDefined()
    await first.get('button[aria-label="资金关注度下一页"]').trigger('click')
    expect(first.get('.legend-name').text()).toBe('核电')
    expect(first.get('[role="status"]').text()).toBe('2/3')
    expect(second.get('.legend-name').text()).toBe('创投')
    await first.get('button[aria-label="资金关注度下一页"]').trigger('click')
    expect(first.get('.legend-name').text()).toBe('有色金属概念')
    expect(first.get('button[aria-label="资金关注度下一页"]').attributes('disabled')).toBeDefined()
    await first.get('button[aria-label="资金关注度上一页"]').trigger('click')
    expect(first.get('.legend-name').text()).toBe('核电')
  })

  it('supports arrow/Home/End keys and preserves the legend visibility toggle', async () => {
    const chart = mountChart()
    await flushPromises()
    const group = chart.get('[role="group"]')
    await group.trigger('keydown', { key: 'ArrowRight' })
    expect(chart.get('.legend-name').text()).toBe('核电')
    await group.trigger('keydown', { key: 'End' })
    expect(chart.get('[role="status"]').text()).toBe('3/3')
    await group.trigger('keydown', { key: 'Home' })
    expect(chart.get('[role="status"]').text()).toBe('1/3')
    await chart.get('.legend-current').trigger('click')
    expect(chart.get('.legend-current').attributes('aria-pressed')).toBe('false')
    await chart.get('.legend-current').trigger('click')
    expect(chart.get('.legend-current').attributes('aria-pressed')).toBe('true')
  })

  it('handles empty/invalid values and clamps the page after a data refresh', async () => {
    const chart = mountChart()
    await chart.get('[role="group"]').trigger('keydown', { key: 'End' })
    await chart.setProps({ items: [items[0]!, { name: '无效', value: Number.NaN }, { name: '零值', value: 0 }] })
    expect(chart.get('.legend-name').text()).toBe('创投')
    expect(chart.get('[role="status"]').text()).toBe('1/1')
    expect(chart.findAll('.legend-page-button').every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    await chart.setProps({ items: [] })
    expect(chart.find('[role="group"]').exists()).toBe(false)
  })
})
