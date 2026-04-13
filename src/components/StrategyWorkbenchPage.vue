<script setup lang="ts">
import DecisionWorkbench from './DecisionWorkbench.vue'
import type { StockApiPayload } from '../services/stocks'

defineOptions({
  name: 'StrategyWorkbenchPage',
})

type WorkbenchStock = StockApiPayload & {
  id?: string
}

const props = defineProps<{
  watchlist: WorkbenchStock[]
  selectedStock?: WorkbenchStock | null
}>()
</script>

<template>
  <DecisionWorkbench :watchlist="watchlist" :selected-stock="selectedStock ?? null" />
</template>
