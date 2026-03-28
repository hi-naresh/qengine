import { ref, watch } from 'vue'
import { guides, allGuides } from './guides/index.js'

// Persisted preferences
const stored = localStorage.getItem('qe_guide_prefs')
const prefs = stored ? JSON.parse(stored) : {}

const showTooltips = ref(prefs.showTooltips !== undefined ? prefs.showTooltips : true)
const showSectionGuides = ref(prefs.showSectionGuides !== undefined ? prefs.showSectionGuides : true)

function persist() {
  localStorage.setItem('qe_guide_prefs', JSON.stringify({
    showTooltips: showTooltips.value,
    showSectionGuides: showSectionGuides.value,
  }))
}

watch(showTooltips, persist)
watch(showSectionGuides, persist)

export function useGuides() {
  function getGuide(key) {
    return allGuides[key] || null
  }

  function getSectionGuide(category) {
    return guides[category]?.['_section_guide'] || null
  }

  function getStrategyGuide(category, key) {
    return guides[category]?.[key] || null
  }

  return {
    showTooltips,
    showSectionGuides,
    guides,
    allGuides,
    getGuide,
    getSectionGuide,
    getStrategyGuide,
  }
}
