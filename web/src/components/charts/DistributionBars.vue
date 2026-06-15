<script setup lang="ts">
import { computed } from "vue";

interface Bucket {
  // Map bucket key; when present the bar is clickable and selects on the map.
  key?: string;
  label: string;
  value: number;
  color?: string;
}

const props = withDefaults(
  defineProps<{
    buckets: Bucket[];
    // When provided, each row shows `value / denominator` as a percent. The
    // denominator is the universe of relevant parcels (e.g. parcels actually
    // rebuilding), which can differ from the chart total when buckets only
    // cover part of that universe.
    denominator?: number;
    // Keys of the currently selected buckets (dims the rest).
    selectedBuckets?: string[];
  }>(),
  { denominator: undefined, selectedBuckets: () => [] },
);

// `additive` carries the Shift modifier so the parent can build a filter set.
const emit = defineEmits<{ select: [key: string, additive: boolean] }>();

const max = computed(() => Math.max(1, ...props.buckets.map((b) => b.value)));
const showPct = computed(() => !!props.denominator && props.denominator > 0);

function formatPct(value: number): string {
  if (!showPct.value) return "";
  return `${((value / (props.denominator ?? 1)) * 100).toFixed(1)}%`;
}

function isSelected(b: Bucket): boolean {
  return b.key != null && props.selectedBuckets.includes(b.key);
}

function isDim(b: Bucket): boolean {
  return props.selectedBuckets.length > 0 && !isSelected(b);
}

function onSelect(b: Bucket, event: MouseEvent): void {
  if (b.key) emit("select", b.key, event.shiftKey);
}
</script>

<template>
  <!-- Single grid (label / bar / count / pct) with `display: contents` on the
       row li so each row's cells align to the parent grid columns. Without
       this, count widths shift the percent column row-to-row. -->
  <ul class="dist__grid" :class="{ 'dist__grid--with-pct': showPct }">
    <li v-for="bucket in buckets" :key="bucket.label" class="dist__row">
      <div class="dist__label" :class="{ 'is-dim': isDim(bucket) }">{{ bucket.label }}</div>
      <button
        type="button"
        class="dist__bar-track"
        :class="{ 'is-dim': isDim(bucket), 'is-selected': isSelected(bucket) }"
        :disabled="!bucket.key"
        :aria-pressed="bucket.key ? isSelected(bucket) : undefined"
        :aria-label="`${bucket.label}: ${bucket.value.toLocaleString()}`"
        @click="onSelect(bucket, $event)"
      >
        <div
          class="dist__bar"
          :style="{
            width: `${(bucket.value / max) * 100}%`,
            backgroundColor: bucket.color ?? 'var(--color-poppy)',
          }"
        />
      </button>
      <div class="dist__count" :class="{ 'is-dim': isDim(bucket) }">
        {{ bucket.value.toLocaleString() }}
      </div>
      <div v-if="showPct" class="dist__pct" :class="{ 'is-dim': isDim(bucket) }">
        {{ formatPct(bucket.value) }}
      </div>
    </li>
  </ul>
</template>

<style scoped>
.dist__grid {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: minmax(110px, 1fr) minmax(0, 2fr) auto;
  align-items: center;
  column-gap: var(--space-3);
  row-gap: var(--space-3);
  font-size: var(--fs-sm);
}
.dist__grid--with-pct {
  grid-template-columns: minmax(110px, 1fr) minmax(0, 2fr) auto auto;
}

.dist__row {
  display: contents;
}

.dist__label {
  color: var(--color-ink-muted);
}

.dist__bar-track {
  background: var(--color-alluvial-soft);
  border-radius: var(--radius-sm);
  height: 14px;
  overflow: hidden;
  appearance: none;
  border: 0;
  padding: 0;
  width: 100%;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.dist__bar-track:disabled {
  cursor: default;
}

.dist__bar-track:focus-visible {
  outline: 2px solid var(--color-poppy);
  outline-offset: 2px;
}

.dist__bar-track.is-selected {
  box-shadow: inset 0 0 0 2px var(--color-ink);
}

.dist__bar {
  height: 100%;
  border-radius: var(--radius-sm);
  min-width: 2px;
}

.is-dim {
  opacity: 0.3;
}

.dist__count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--color-ink);
  text-align: right;
}

.dist__pct {
  font-variant-numeric: tabular-nums;
  font-size: var(--fs-xs);
  color: var(--color-ink-muted);
  text-align: right;
}

/* On narrow viewports drop back to a per-row sub-grid so the bar can take a
   full row of its own — `display: contents` doesn't compose with row-stacked
   layouts, so we re-promote the row to a grid container here. */
@media (max-width: 480px) {
  .dist__grid,
  .dist__grid--with-pct {
    grid-template-columns: 1fr;
    row-gap: var(--space-4);
  }
  .dist__row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    grid-template-areas:
      "label count pct"
      "bar bar bar";
    column-gap: var(--space-2);
    row-gap: var(--space-1);
    align-items: center;
  }
  .dist__label {
    grid-area: label;
  }
  .dist__bar-track {
    grid-area: bar;
  }
  .dist__count {
    grid-area: count;
  }
  .dist__pct {
    grid-area: pct;
  }
}
</style>
