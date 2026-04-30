import { computed, readonly, ref } from "vue";

import { DATA_PATHS, STALE_AFTER_MS } from "@/constants";
import type { QcReport, Summary } from "@/types";

const summary = ref<Summary | null>(null);
const qcReport = ref<QcReport | null>(null);
const error = ref<Error | null>(null);
const loading = ref(false);

let inflight: Promise<void> | null = null;

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`Failed to fetch ${path}: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const [s, q] = await Promise.all([
      fetchJson<Summary>(DATA_PATHS.summary),
      fetchJson<QcReport>(DATA_PATHS.qcReport),
    ]);
    summary.value = s;
    qcReport.value = q;
  } catch (err) {
    error.value = err instanceof Error ? err : new Error(String(err));
  } finally {
    loading.value = false;
  }
}

export function useDataset() {
  if (!inflight && !summary.value && !error.value) {
    inflight = load();
  }

  const generatedAt = computed(() => (summary.value ? new Date(summary.value.generated_at) : null));

  const isStale = computed(() => {
    if (!generatedAt.value) return false;
    return Date.now() - generatedAt.value.getTime() > STALE_AFTER_MS;
  });

  return {
    summary: readonly(summary),
    qcReport: readonly(qcReport),
    loading: readonly(loading),
    error: readonly(error),
    isStale,
    generatedAt,
    reload: () => {
      inflight = load();
      return inflight;
    },
  };
}
