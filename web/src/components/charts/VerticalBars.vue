<script setup lang="ts">
import { computed } from "vue";

interface Bucket {
  // Map bucket key; when present the column is clickable and selects on the map.
  key?: string;
  label: string;
  value: number;
  color?: string;
}

const props = defineProps<{
  buckets: Bucket[];
  // Universe size (e.g. all parcels actually rebuilding) — used as
  // denominator when rendering each bar's percent label.
  denominator?: number;
  // Key of the currently selected bucket (dims the others).
  selectedBucket?: string | null;
}>();

const emit = defineEmits<{ select: [key: string] }>();

const max = computed(() => Math.max(1, ...props.buckets.map((b) => b.value)));

function pctLabel(value: number): string {
  if (!props.denominator || props.denominator <= 0) return "";
  return `${((value / props.denominator) * 100).toFixed(1)}%`;
}

function isDim(b: Bucket): boolean {
  return props.selectedBucket != null && b.key !== props.selectedBucket;
}

function onSelect(b: Bucket): void {
  if (b.key) emit("select", b.key);
}
</script>

<template>
  <!-- One button per bucket spanning the whole column (percentage, bar, count,
       label) so the entire column is the clickable/selectable target, with a
       metric-list-style background + outline on hover/selection. Each column is
       a `subgrid` so the four rows still align across columns, and the grid's
       `1fr` label row makes the chart fill the card exactly (no overflow). -->
  <div class="vbars" :style="{ gridTemplateColumns: `repeat(${buckets.length}, minmax(0, 1fr))` }">
    <button
      v-for="bucket in buckets"
      :key="bucket.label"
      type="button"
      class="vbars__col"
      :class="{ 'is-dim': isDim(bucket), 'is-selected': bucket.key === selectedBucket }"
      :disabled="!bucket.key"
      :aria-pressed="bucket.key ? bucket.key === selectedBucket : undefined"
      :aria-label="`${bucket.label}: ${bucket.value.toLocaleString()}`"
      @click="onSelect(bucket)"
    >
      <span class="vbars__pct">{{ pctLabel(bucket.value) }}</span>
      <span class="vbars__bar-area">
        <span
          class="vbars__bar"
          :style="{
            height: `${(bucket.value / max) * 100}%`,
            backgroundColor: bucket.color ?? 'var(--color-poppy)',
          }"
        />
      </span>
      <span class="vbars__count">{{ bucket.value.toLocaleString() }}</span>
      <span class="vbars__label">{{ bucket.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.vbars {
  display: grid;
  grid-template-rows: auto 70px auto 1fr;
  grid-auto-flow: column;
  /* No gap between columns — the separation is the columns' own padding now, so
     the active highlight has breathing room instead of hugging the content. */
  column-gap: 0;
  row-gap: var(--space-1);
  width: 100%;
  /* Pull up into the (excessive) subtitle gap and add matching clearance below,
     so the selected column's outline doesn't touch the card border. The two
     offsets cancel, so the card's overall height is unchanged. */
  margin-top: calc(-1 * var(--space-2));
  padding-bottom: var(--space-2);
}

.vbars__col {
  /* Span the four rows so the whole column is one clickable button. */
  grid-row: 1 / -1;
  display: grid;
  grid-template-rows: subgrid;
  /* Horizontal padding restores the original inter-column separation (space-1
     per side → space-2 between neighbors); vertical padding gives the highlight
     top/bottom breathing room. The grid's 1fr label row absorbs it, so the
     chart still fills the card without overflowing. */
  padding: var(--space-2) var(--space-1);
  /* button reset */
  appearance: none;
  border: 0;
  background: transparent;
  font: inherit;
  color: inherit;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition:
    background 0.15s ease,
    box-shadow 0.15s ease,
    opacity 0.15s ease;
}

.vbars__col:disabled {
  cursor: default;
}

.vbars__col:not(:disabled):hover {
  background: var(--color-paper-deep);
}

.vbars__col:focus-visible {
  outline: 2px solid var(--color-poppy);
  outline-offset: 1px;
}

.vbars__col.is-selected {
  background: var(--color-paper-deep);
  box-shadow: inset 0 0 0 1px var(--color-ink);
}

.vbars__col.is-dim {
  opacity: 0.3;
}

.vbars__pct {
  align-self: end;
  text-align: center;
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
  color: var(--color-ink-muted);
}

.vbars__bar-area {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  width: 100%;
}

.vbars__bar {
  width: 80%;
  min-height: 2px;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
}

.vbars__count {
  text-align: center;
  font-size: var(--fs-sm);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-ink);
}

.vbars__label {
  align-self: start;
  text-align: center;
  font-size: var(--fs-xs);
  color: var(--color-ink-muted);
  line-height: 1.25;
  hyphens: auto;
  word-break: break-word;
}

@media (max-width: 480px) {
  .vbars {
    grid-template-rows: auto 55px auto 1fr;
  }
  .vbars__label {
    font-size: 0.7rem;
  }
}
</style>
