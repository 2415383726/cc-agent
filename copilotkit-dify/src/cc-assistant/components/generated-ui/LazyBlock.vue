<template>
  <div ref="elRef" class="lazy-block" :style="{ minHeight: visible ? undefined : `${minHeight}px` }">
    <slot v-if="visible" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  rootMargin?: string
  minHeight?: number
}>(), {
  rootMargin: '300px',
  minHeight: 120,
})

const elRef = ref<HTMLElement>()
const visible = ref(typeof IntersectionObserver === 'undefined')
let observer: IntersectionObserver | null = null

onMounted(() => {
  if (!elRef.value || visible.value) return

  const rect = elRef.value.getBoundingClientRect()
  const preloadDistance = Math.max(window.innerHeight * 1.5, 900)
  if (rect.bottom >= -preloadDistance && rect.top <= window.innerHeight + preloadDistance) {
    visible.value = true
    return
  }

  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        visible.value = true
        observer?.disconnect()
      }
    },
    { rootMargin: props.rootMargin },
  )
  observer.observe(elRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>
