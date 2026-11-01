<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { MOTION, prefersReducedMotion } from '../utils/motion'

type PieItem = {
  name: string
  value: number
}

type EChartsLike = {
  dispose: () => void
  resize: () => void
  setOption: (option: Record<string, unknown>, opts?: Record<string, unknown>) => void
}

type EChartsGlobal = {
  init: (element: HTMLDivElement) => EChartsLike
}

const props = withDefaults(
  defineProps<{
    items: PieItem[]
    mode?: 'pie' | 'donut'
    loading?: boolean
    emptyText?: string
    seriesName?: string
  }>(),
  {
    mode: 'pie',
    loading: false,
    emptyText: '暂无可展示数据',
    seriesName: '板块分析',
  },
)

const chartRef = ref<HTMLDivElement | null>(null)
const chartItems = computed(() => props.items.filter((item) => Number.isFinite(item.value) && item.value > 0))
const legendIndex = ref(0)
const selectedLegendItems = ref<Record<string, boolean>>({})
const currentLegendItem = computed(() => chartItems.value[legendIndex.value])
const currentLegendSelected = computed(() => selectedLegendItems.value[currentLegendItem.value?.name ?? ''] !== false)
const colors = ['#2f80ed', '#19b58f', '#f97316', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#84cc16']

function changeLegendPage(offset: number): void {
  legendIndex.value = Math.max(0, Math.min(chartItems.value.length - 1, legendIndex.value + offset))
}

function toggleLegendItem(): void {
  const item = currentLegendItem.value
  if (!item) return
  selectedLegendItems.value = { ...selectedLegendItems.value, [item.name]: !currentLegendSelected.value }
  renderChart()
}

watch(chartItems, (items) => {
  legendIndex.value = Math.min(legendIndex.value, Math.max(0, items.length - 1))
})

let chartInstance: EChartsLike | null = null
let chartLoadPromise: Promise<void> | null = null
let resizeObserver: ResizeObserver | null = null

function getEChartsCtor(): EChartsGlobal | null {
  return ((window as Window & { echarts?: EChartsGlobal }).echarts ?? null) as EChartsGlobal | null
}

function ensureEChartsLoaded(): Promise<void> {
  if (getEChartsCtor()) return Promise.resolve()
  if (chartLoadPromise) return chartLoadPromise

  chartLoadPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById('echarts-cdn-script') as HTMLScriptElement | null
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('加载 ECharts 失败')), { once: true })
      return
    }

    const script = document.createElement('script')
    script.id = 'echarts-cdn-script'
    script.src = `${import.meta.env.BASE_URL}vendor/echarts-5.6.0.min.js`
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('加载 ECharts 失败'))
    document.head.appendChild(script)
  })

  return chartLoadPromise
}

function buildOption(): Record<string, unknown> {
  const hasData = chartItems.value.length > 0
  const radius = props.mode === 'donut' ? ['64%', '90%'] : ['0%', '90%']

  return {
    animation: !prefersReducedMotion(),
    animationDuration: MOTION.slow,
    animationDurationUpdate: MOTION.normal,
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: '{b}<br/>{a}: {c}',
    },
    legend: {
      show: false,
      selected: selectedLegendItems.value,
    },
    graphic: hasData
      ? undefined
      : [
          {
            type: 'text',
            left: 'center',
            top: 'middle',
            style: {
              text: props.loading ? '加载中...' : props.emptyText,
              fill: '#6b7c93',
              fontSize: 14,
              fontWeight: 600,
            },
          },
        ],
    series: hasData ? [
      {
        name: props.seriesName,
        type: 'pie',
        radius,
        center: ['50%', '50%'],
        minAngle: hasData ? 3 : 0,
        avoidLabelOverlap: true,
        label: {
          show: false,
        },
        emphasis: {
          scaleSize: 4,
          label: {
            show: false,
          },
        },
        labelLine: {
          show: false,
        },
        itemStyle: {
          borderColor: 'rgba(255, 255, 255, 0.95)',
          borderWidth: 2,
        },
        data: chartItems.value,
        color: colors,
      },
    ] : [],
  }
}

function renderChart(): void {
  const echarts = getEChartsCtor()
  if (!echarts || !chartRef.value) return

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  chartInstance.setOption(buildOption(), { notMerge: true })
}

async function initChart(): Promise<void> {
  try {
    await ensureEChartsLoaded()
    renderChart()
  } catch {
    // 组件内部已用 empty graphic 承接，无需向上抛出。
  }
}

function handleResize(): void {
  if (chartRef.value?.clientWidth && chartRef.value.clientHeight) chartInstance?.resize()
}

watch(
  () => [props.items, props.loading, props.emptyText, props.mode, props.seriesName] as const,
  () => {
    renderChart()
  },
  { deep: true },
)

onMounted(async () => {
  if (typeof ResizeObserver !== 'undefined' && chartRef.value) {
    resizeObserver = new ResizeObserver(handleResize)
    resizeObserver.observe(chartRef.value)
  }
  await initChart()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<template>
  <div class="echarts-pie">
    <div ref="chartRef" class="echarts-canvas"></div>
    <div
      v-if="currentLegendItem"
      class="chart-legend"
      role="group"
      :aria-label="`${seriesName}图例分页`"
      @keydown.left.prevent="changeLegendPage(-1)"
      @keydown.right.prevent="changeLegendPage(1)"
      @keydown.home.prevent="legendIndex = 0"
      @keydown.end.prevent="legendIndex = chartItems.length - 1"
    >
      <button
        class="legend-current"
        type="button"
        :title="currentLegendItem.name"
        :aria-label="`${currentLegendItem.name}，${currentLegendSelected ? '点击隐藏' : '点击显示'}`"
        :aria-pressed="currentLegendSelected"
        @click="toggleLegendItem"
      >
        <span class="legend-swatch" :style="{ background: currentLegendSelected ? colors[legendIndex % colors.length] : '#aaa' }" aria-hidden="true"></span>
        <span class="legend-name">{{ currentLegendItem.name }}</span>
      </button>
      <div class="legend-navigation">
        <button type="button" class="legend-page-button" :aria-label="`${seriesName}上一页`" :disabled="legendIndex === 0" @click="changeLegendPage(-1)">
          <span aria-hidden="true">‹</span>
        </button>
        <span class="legend-page-count" role="status" aria-live="polite">{{ legendIndex + 1 }}/{{ chartItems.length }}</span>
        <button type="button" class="legend-page-button" :aria-label="`${seriesName}下一页`" :disabled="legendIndex >= chartItems.length - 1" @click="changeLegendPage(1)">
          <span aria-hidden="true">›</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.echarts-pie {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  width: 100%;
  height: 100%;
  min-height: 190px;
}

.echarts-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.chart-legend {
  display: grid;
  gap: 2px;
  min-width: 0;
  min-height: 48px;
  color: #475569;
  font-size: 11px;
}

.legend-current {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.legend-swatch {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
}

.legend-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.legend-navigation {
  display: grid;
  grid-template-columns: minmax(28px, 1fr) auto minmax(28px, 1fr);
  align-items: center;
  gap: 3px;
}

.legend-page-button {
  height: 28px;
  min-width: 28px;
  padding: 0 4px;
  border: 1px solid #d5dee8;
  border-radius: 4px;
  background: #f7f9fb;
  color: #2f4554;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.legend-page-button:hover:not(:disabled) {
  border-color: #77add6;
  background: #eef7ff;
}

.legend-page-button:disabled {
  color: #aaa;
  cursor: default;
}

.legend-page-button:focus-visible,
.legend-current:focus-visible {
  outline: 2px solid #2f80ed;
  outline-offset: 1px;
}

.legend-page-count {
  min-width: 25px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
</style>
