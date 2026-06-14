<script setup lang="ts">
const props = defineProps<{
  value: number;
  label?: string;
  // Map bucket key; when present the number is clickable and selects on the map.
  bucketKey?: string;
  selectedBucket?: string | null;
}>();

const emit = defineEmits<{ select: [key: string] }>();

function onSelect(): void {
  if (props.bucketKey) emit("select", props.bucketKey);
}
</script>

<template>
  <component
    :is="bucketKey ? 'button' : 'div'"
    :type="bucketKey ? 'button' : undefined"
    class="big-number"
    :class="{
      'big-number--button': !!bucketKey,
      'is-selected': bucketKey != null && bucketKey === selectedBucket,
    }"
    :aria-pressed="bucketKey ? bucketKey === selectedBucket : undefined"
    @click="onSelect"
  >
    <span class="big-number__value">{{ value.toLocaleString() }}</span>
    <span v-if="label" class="big-number__label">{{ label }}</span>
  </component>
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

.big-number--button {
  appearance: none;
  border: 0;
  background: transparent;
  font: inherit;
  cursor: pointer;
  border-radius: var(--radius-md);
  transition: background 0.15s ease;
}

.big-number--button:hover {
  background: var(--color-paper-deep);
}

.big-number--button:focus-visible {
  outline: 2px solid var(--color-poppy);
  outline-offset: 2px;
}

.big-number--button.is-selected {
  background: var(--color-paper-deep);
  box-shadow: inset 0 0 0 1px var(--color-ink);
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
