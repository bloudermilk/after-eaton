<script setup lang="ts">
import { computed } from "vue";

interface Item {
  // Map bucket key; when present the row is clickable and selects on the map.
  key?: string;
  label: string;
  value: number;
  color?: string;
}

const props = withDefaults(
  defineProps<{
    items: Item[];
    // When provided, each row shows `value / denominator` as a percent.
    denominator?: number;
    // Key of the currently selected bucket (dims the others).
    selectedBucket?: string | null;
  }>(),
  { denominator: undefined, selectedBucket: null },
);

const emit = defineEmits<{ select: [key: string] }>();

const showPct = computed(() => !!props.denominator && props.denominator > 0);

function formatPct(value: number): string {
  if (!showPct.value) return "";
  return `${((value / (props.denominator ?? 1)) * 100).toFixed(1)}%`;
}

function isDim(item: Item): boolean {
  return props.selectedBucket != null && item.key !== props.selectedBucket;
}

function onSelect(item: Item): void {
  if (item.key) emit("select", item.key);
}
</script>

<template>
  <ul class="mlist">
    <li v-for="item in items" :key="item.label">
      <button
        type="button"
        class="mlist__row"
        :class="{ 'is-dim': isDim(item), 'is-selected': item.key === selectedBucket }"
        :disabled="!item.key"
        :aria-pressed="item.key ? item.key === selectedBucket : undefined"
        @click="onSelect(item)"
      >
        <span
          class="mlist__swatch"
          :style="{ backgroundColor: item.color ?? 'var(--color-poppy)' }"
          aria-hidden="true"
        />
        <span class="mlist__label">{{ item.label }}</span>
        <span class="mlist__count">{{ item.value.toLocaleString() }}</span>
        <span v-if="showPct" class="mlist__pct">{{ formatPct(item.value) }}</span>
      </button>
    </li>
  </ul>
</template>

<style scoped>
.mlist {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 100%;
  font-size: var(--fs-sm);
}

.mlist__row {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) auto auto;
  gap: var(--space-3);
  align-items: center;
  width: 100%;
  appearance: none;
  border: 0;
  background: transparent;
  padding: var(--space-2);
  margin: 0;
  border-radius: var(--radius-sm);
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background 0.15s ease,
    opacity 0.15s ease;
}

.mlist__row:disabled {
  cursor: default;
}

.mlist__row:not(:disabled):hover {
  background: var(--color-paper-deep);
}

.mlist__row:focus-visible {
  outline: 2px solid var(--color-poppy);
  outline-offset: 1px;
}

.mlist__row.is-selected {
  background: var(--color-paper-deep);
  box-shadow: inset 0 0 0 1px var(--color-ink);
}

.mlist__row.is-dim {
  opacity: 0.4;
}

.mlist__swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.mlist__label {
  color: var(--color-ink-muted);
}

.mlist__count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--color-ink);
  text-align: right;
}

.mlist__pct {
  font-variant-numeric: tabular-nums;
  font-size: var(--fs-xs);
  color: var(--color-ink-muted);
  text-align: right;
  min-width: 3.2em;
}
</style>
