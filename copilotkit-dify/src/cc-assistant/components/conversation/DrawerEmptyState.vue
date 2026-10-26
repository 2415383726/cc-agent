<template>
  <div class="drawer-empty-state">
    <div class="drawer-empty-copy">
      <h2>有什么可以帮你？</h2>
      <p>选择一个入口，或直接在下方输入问题。</p>
    </div>

    <section v-for="section in sections" :key="section.title" class="drawer-empty-section">
      <h3>{{ section.title }}</h3>
      <div class="drawer-empty-grid">
        <button v-for="item in section.items" :key="`${section.title}:${item.title}`" type="button"
          class="drawer-empty-action" @click="$emit('select', item.message)">
          <span>{{ item.title }}</span>
          <small>{{ item.description }}</small>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { drawerEmptyStateSections } from '../../lib/drawerEmptyState'

defineEmits<{
  select: [message: string]
}>()

const sections = drawerEmptyStateSections
</script>
