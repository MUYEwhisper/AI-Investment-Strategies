<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

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

let chartInstance: EChartsLike | null = null
let chartLoadPromise: Promise<void> | null = null

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
    script.src = 'https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js'
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('加载 ECharts 失败'))
    document.head.appendChild(script)
  })

  return chartLoadPromise
}

function buildOption(): Record<string, unknown> {
  const hasData = props.items.length > 0
  const radius = props.mode === 'donut' ? ['56%', '78%'] : ['0%', '78%']

  return {
    animationDuration: 400,
    tooltip: {
      trigger: 'item',
      formatter: '{b}<br/>{a}: {c}',
    },
    legend: {
      type: 'scroll',
      bottom: 0,
      left: 'center',
      icon: 'rect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: {
        color: '#475569',
        fontSize: 11,
      },
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
    series: [
      {
        name: props.seriesName,
        type: 'pie',
        radius,
        center: ['50%', '44%'],
        minAngle: hasData ? 3 : 0,
        avoidLabelOverlap: true,
        label: {
          show: false,
        },
        emphasis: {
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
        data: props.items,
        color: ['#2f80ed', '#19b58f', '#f97316', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#84cc16'],
      },
    ],
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
  chartInstance?.resize()
}

watch(
  () => [props.items, props.loading, props.emptyText, props.mode, props.seriesName] as const,
  () => {
    renderChart()
  },
  { deep: true },
)

onMounted(async () => {
  await initChart()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})
</script>

<template>
  <div ref="chartRef" class="echarts-pie"></div>
</template>

<style scoped>
.echarts-pie {
  width: 100%;
  height: 100%;
  min-height: 190px;
}
</style>
