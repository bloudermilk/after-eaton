<script setup lang="ts">
defineProps<{
  value: number;
  label?: string;
}>();
</script>

<template>
  <div class="big-number">
    <span class="big-number__value">{{ value.toLocaleString() }}</span>
    <span v-if="label" class="big-number__label">{{ label }}</span>
  </div>
</template>

<style scoped>
.big-number {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-3) 0;
  width: 100%;
}

.big-number__value {
  font-family: var(--font-display);
  font-size: var(--fs-display);
  color: var(--color-poppy);
  line-height: 1;
}

.big-number__label {
  font-size: var(--fs-sm);
  color: var(--color-ink-muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
</style>
