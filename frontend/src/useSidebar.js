import { ref } from 'vue'

const collapsed = ref(true)

export function useSidebar() {
  function toggle() { collapsed.value = !collapsed.value }
  return { collapsed, toggle }
}
