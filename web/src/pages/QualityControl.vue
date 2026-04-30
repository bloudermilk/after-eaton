<script setup lang="ts">
import { computed, ref } from "vue";

import { DATA_PATHS } from "@/constants";
import { useDataset } from "@/composables/useDataset";
import type { RecordWarning, ThresholdCheck, WarningSeverity } from "@/types";

const { qcReport } = useDataset();

// Some thresholds are rates (0–1 fractions like description_parse_rate); others
// are absolute counts (min_completed_rebuilds, tract_partitions_into_block_groups).
// Format the rate-shaped ones as percents and leave counts as plain numbers.
function isRateCheck(t: ThresholdCheck): boolean {
  return t.name.endsWith("_rate");
}

function formatThresholdValue(t: ThresholdCheck, value: number): string {
  if (isRateCheck(t)) {
    return `${(value * 100).toFixed(1)}%`;
  }
  return value.toLocaleString();
}

type SortKey = "ain" | "code" | "severity";
const sortKey = ref<SortKey>("code");
const filterSeverity = ref<"all" | WarningSeverity>("all");

const sortedWarnings = computed<RecordWarning[]>(() => {
  if (!qcReport.value) return [];
  const filtered = qcReport.value.warnings.filter((w) =>
    filterSeverity.value === "all" ? true : w.severity === filterSeverity.value,
  );
  const k = sortKey.value;
  return [...filtered].sort((a, b) => a[k].localeCompare(b[k]));
});

const warningCountsByCode = computed(() => {
  if (!qcReport.value) return [] as { code: string; count: number }[];
  const counts = new Map<string, number>();
  for (const w of qcReport.value.warnings) {
    counts.set(w.code, (counts.get(w.code) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([code, count]) => ({ code, count }))
    .sort((a, b) => b.count - a.count);
});
</script>

<template>
  <main v-if="qcReport" class="qc">
    <header class="qc__header">
      <h1>Quality control</h1>
      <p>
        Every pipeline run produces a QC report covering hard-fail thresholds and per-record
        warnings. The current run was generated
        <strong>{{ new Date(qcReport.generated_at).toLocaleString() }}</strong
        >.
      </p>
    </header>

    <section>
      <h2>Thresholds</h2>
      <p class="qc__lede">
        Each threshold gates the publish step. If any threshold fails, the pipeline aborts and no
        new data is released.
      </p>
      <div class="qc__table-wrap">
        <table class="qc__table">
          <thead>
            <tr>
              <th>Check</th>
              <th>Actual</th>
              <th>Threshold</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in qcReport.thresholds" :key="t.name">
              <td>
                <code>{{ t.name }}</code>
              </td>
              <td>{{ formatThresholdValue(t, t.actual) }}</td>
              <td>{{ formatThresholdValue(t, t.threshold) }}</td>
              <td>
                <span class="badge" :class="t.passed ? 'badge--pass' : 'badge--fail'">
                  {{ t.passed ? "Pass" : "Fail" }}
                </span>
              </td>
              <td class="qc__detail">{{ t.detail }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section>
      <h2>Per-record warnings</h2>
      <p class="qc__lede">
        <strong>{{ qcReport.warnings.length.toLocaleString() }}</strong> warnings across
        {{ qcReport.total_parcels.toLocaleString() }} parcels.
        <span class="qc__legend">
          <em>data</em> warnings count toward the <code>warning_rate</code> threshold;
          <em>info</em> warnings surface real-world ambiguity and don't gate the run.
        </span>
      </p>

      <details class="qc__rollup">
        <summary>Counts by code</summary>
        <ul>
          <li v-for="row in warningCountsByCode" :key="row.code">
            <code>{{ row.code }}</code>
            <span>{{ row.count.toLocaleString() }}</span>
          </li>
        </ul>
      </details>

      <div class="qc__controls">
        <label>
          Severity
          <select v-model="filterSeverity">
            <option value="all">All</option>
            <option value="data">data</option>
            <option value="info">info</option>
          </select>
        </label>
        <label>
          Sort by
          <select v-model="sortKey">
            <option value="code">Code</option>
            <option value="severity">Severity</option>
            <option value="ain">AIN</option>
          </select>
        </label>
      </div>

      <div class="qc__table-wrap">
        <table class="qc__table qc__table--warnings">
          <thead>
            <tr>
              <th>AIN</th>
              <th>Code</th>
              <th>Severity</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in sortedWarnings" :key="`${w.ain}-${w.code}-${w.detail}`">
              <td>
                <code>{{ w.ain }}</code>
              </td>
              <td>
                <code>{{ w.code }}</code>
              </td>
              <td>
                <span class="badge" :class="`badge--sev-${w.severity}`">{{ w.severity }}</span>
              </td>
              <td class="qc__detail">{{ w.detail }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="qc__raw">
        <a :href="DATA_PATHS.qcReport" download>Download raw qc-report.json</a>
      </p>
    </section>
  </main>
</template>

<style scoped>
.qc {
  max-width: 920px;
}

.qc__header {
  margin-bottom: var(--space-7);
}
.qc__header p {
  color: var(--color-ink-muted);
}

.qc__lede {
  color: var(--color-ink-muted);
  font-size: var(--fs-sm);
  margin-bottom: var(--space-4);
}

.qc__legend em {
  background: var(--color-paper-deep);
  font-style: normal;
  padding: 1px 5px;
  border-radius: var(--radius-sm);
}

.qc__rollup {
  margin: var(--space-4) 0;
  background: var(--color-paper-deep);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
}
.qc__rollup summary {
  cursor: pointer;
  font-weight: 600;
  font-size: var(--fs-sm);
}
.qc__rollup ul {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--space-2);
  font-size: var(--fs-sm);
}
.qc__rollup li {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px dotted var(--color-rule);
  padding: var(--space-1) 0;
}

.qc__controls {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3) var(--space-4);
  align-items: center;
  margin: var(--space-4) 0;
  font-size: var(--fs-sm);
}
.qc__controls select {
  margin-left: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-rule);
  background: var(--color-paper);
  font: inherit;
}

/* Tables can outgrow narrow viewports — let them scroll horizontally with a
   floor on table width so columns stay legible rather than collapsing. The
   layout is `auto` so columns size to their content (the CHECK column has
   long names like `tract_partitions_into_block_groups` and would otherwise
   overflow into the Actual column). */
.qc__table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.qc__table {
  table-layout: auto;
  width: 100%;
  min-width: 720px;
}
.qc__table th,
.qc__table td {
  white-space: nowrap;
}
.qc__table th:last-child,
.qc__table td:last-child {
  white-space: normal;
}
.qc__table--warnings {
  min-width: 560px;
}
.qc__table code {
  font-size: 0.92em;
  background: var(--color-paper-deep);
  padding: 1px 5px;
  border-radius: var(--radius-sm);
}
.qc__detail {
  word-break: break-word;
  color: var(--color-ink-muted);
}

.qc__table--warnings {
  margin-top: var(--space-3);
}

.qc__raw {
  margin-top: var(--space-5);
  font-size: var(--fs-sm);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.badge--pass {
  background: rgba(62, 107, 74, 0.15);
  color: var(--color-success);
}
.badge--fail {
  background: rgba(179, 73, 49, 0.15);
  color: var(--color-danger);
}
.badge--sev-data {
  background: rgba(179, 73, 49, 0.12);
  color: var(--color-danger);
}
.badge--sev-info {
  background: rgba(94, 122, 110, 0.18);
  color: var(--color-deodara);
}
</style>
