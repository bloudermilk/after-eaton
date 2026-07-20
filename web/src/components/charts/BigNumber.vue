<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    value: number;
    label?: string;
    // Map bucket key; when present the number is clickable and selects on the map.
    bucketKey?: string;
    // Keys of the currently selected buckets (dims this one when others are set).
    selectedBuckets?: string[];
    // Tint for the value, matching this bucket's map-dot color. Defaults to poppy.
    color?: string;
    // When set (>0), render the value as a percentage of this denominator below
    // the count — e.g. "12.3% of damaged/destroyed homes".
    denominator?: number;
  }>(),
  {
    label: undefined,
    bucketKey: undefined,
    selectedBuckets: () => [],
    color: undefined,
    denominator: undefined,
  },
);

const pctLabel = (): string | null => {
  if (!props.denominator || props.denominator <= 0) return null;
  return `${((props.value / props.denominator) * 100).toFixed(1)}%`;
};

// `additive` carries the Shift modifier so the parent can build a filter set.
const emit = defineEmits<{ select: [key: string, additive: boolean] }>();

const isSelected = (): boolean =>
  props.bucketKey != null && props.selectedBuckets.includes(props.bucketKey);
const isDim = (): boolean =>
  props.bucketKey != null && props.selectedBuckets.length > 0 && !isSelected();

function onSelect(event: MouseEvent): void {
  if (props.bucketKey) emit("select", props.bucketKey, event.shiftKey);
}
</script>

<template>
  <component
    :is="bucketKey ? 'button' : 'div'"
    :type="bucketKey ? 'button' : undefined"
    class="big-number"
    :class="{
      'big-number--button': !!bucketKey,
      'is-selected': isSelected(),
      'is-dim': isDim(),
    }"
    :aria-pressed="bucketKey ? isSelected() : undefined"
    @click="onSelect($event)"
  >
    <span class="big-number__value" :style="color ? { color } : undefined">{{
      value.toLocaleString()
    }}</span>
    <span v-if="pctLabel()" class="big-number__pct">{{ pctLabel() }}</span>
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

.big-number--button.is-dim {
  opacity: 0.4;
}

.big-number__value {
  font-family: var(--font-display);
  font-size: var(--fs-display);
  color: var(--color-poppy);
  line-height: 1;
}

.big-number__pct {
  font-size: var(--fs-sm);
  color: var(--color-ink-muted);
  line-height: 1;
}

.big-number__label {
  font-size: var(--fs-sm);
  color: var(--color-ink-muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
</style>
