<template>
  <div v-if="guideText && showSectionGuides" class="mb-3">
    <button @click="expanded = !expanded"
      class="text-[10px] text-brand-400 hover:text-brand-300 transition-colors flex items-center gap-1">
      <svg class="w-3 h-3 transition-transform" :class="expanded ? 'rotate-90' : ''" viewBox="0 0 16 16" fill="currentColor">
        <path d="M6 3l5 5-5 5V3z"/>
      </svg>
      {{ title }}
    </button>
    <div v-if="expanded" class="mt-2 p-3 bg-surface-800/60 rounded-lg border border-surface-700/50 text-xs text-surface-400 leading-relaxed space-y-2">
      <template v-for="(block, i) in parsedBlocks" :key="i">
        <ul v-if="block.type === 'list'" class="list-disc list-inside space-y-1 ml-1">
          <li v-for="(item, j) in block.items" :key="j">{{ item }}</li>
        </ul>
        <p v-else>{{ block.text }}</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useGuides } from '../useGuides'

const props = defineProps({
  category: { type: String, required: true },
  title: { type: String, default: 'How to read these stats' },
})

const { getSectionGuide, showSectionGuides } = useGuides()
const expanded = ref(false)

const guideText = computed(() => getSectionGuide(props.category))

const parsedBlocks = computed(() => {
  if (!guideText.value) return []
  const blocks = []
  const parts = guideText.value.split('\n\n')
  for (const part of parts) {
    const lines = part.split('\n')
    const listLines = lines.filter(l => l.startsWith('- '))
    if (listLines.length === lines.length && listLines.length > 0) {
      blocks.push({ type: 'list', items: listLines.map(l => l.slice(2)) })
    } else {
      blocks.push({ type: 'paragraph', text: part.replace(/\n/g, ' ') })
    }
  }
  return blocks
})
</script>
