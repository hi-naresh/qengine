<template>
  <span class="relative group/tip inline-flex items-center gap-1" :class="showTooltips ? 'cursor-help' : ''">
    <slot />
    <svg v-if="guideText && showTooltips" class="w-2.5 h-2.5 text-surface-600 group-hover/tip:text-brand-400 transition-colors shrink-0" viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 2.5a1 1 0 110 2 1 1 0 010-2zM9.5 11a.5.5 0 01-.5.5H7a.5.5 0 010-1h.5V8H7a.5.5 0 010-1h1a.5.5 0 01.5.5v3h.5a.5.5 0 01.5.5z"/>
    </svg>
    <div v-if="guideText && showTooltips"
      class="absolute z-50 mb-1.5 px-2.5 py-1.5 w-56
             bg-surface-900 border border-surface-600 rounded-lg shadow-xl
             text-[11px] leading-relaxed
             normal-case tracking-normal font-normal text-surface-300
             opacity-0 invisible group-hover/tip:opacity-100 group-hover/tip:visible
             transition-all duration-150 pointer-events-none"
      :class="position === 'below' ? 'top-full mt-1.5' : 'bottom-full'"
      :style="alignStyle">
      {{ guideText }}
      <div class="absolute border-4 border-transparent"
        :class="position === 'below'
          ? 'bottom-full left-1/2 -translate-x-1/2 mb-px border-b-surface-600'
          : 'top-full left-1/2 -translate-x-1/2 -mt-px border-t-surface-600'">
      </div>
    </div>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useGuides } from '../useGuides'

const props = defineProps({
  metricKey: { type: String, required: true },
  position: { type: String, default: 'above' }, // 'above' or 'below'
  align: { type: String, default: 'center' }, // 'center', 'left', 'right'
})

const { showTooltips, getGuide } = useGuides()
const fullText = computed(() => getGuide(props.metricKey))
// Show first 1-2 sentences in tooltip (keep it brief)
const guideText = computed(() => {
  if (!fullText.value) return null
  const sentences = fullText.value.match(/[^.!?]+[.!?]+/g)
  if (!sentences) return fullText.value
  const short = sentences.slice(0, 2).join('').trim()
  return short.length < fullText.value.length ? short : fullText.value
})

const alignStyle = computed(() => {
  if (props.align === 'left') return { left: '0' }
  if (props.align === 'right') return { right: '0' }
  return { left: '50%', transform: 'translateX(-50%)' }
})
</script>
