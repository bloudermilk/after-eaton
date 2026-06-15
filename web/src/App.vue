<script setup lang="ts">
import { computed, watchEffect } from "vue";
import { useRoute } from "vue-router";

import SiteHeader from "@/components/Header.vue";
import SiteFooter from "@/components/Footer.vue";
import LoadingState from "@/components/LoadingState.vue";
import ErrorState from "@/components/ErrorState.vue";
import StaleBanner from "@/components/StaleBanner.vue";
import { useDataset } from "@/composables/useDataset";

const { loading, error, isStale, generatedAt, summary, qcReport } = useDataset();
const route = useRoute();

// The Methodology page renders only METHODOLOGY.md and doesn't need data —
// don't gate it on dataset loading.
const dataRequired = computed(() => route.name !== "methodology");

// The home route is a full-viewport map split with no page scroll, so suppress
// the global footer. Its links/as-of live in the header's About modal instead.
const isHome = computed(() => route.name === "home");

// On home, pin the app shell to the viewport height so the cards rail and map
// scroll internally instead of the whole page (see base.css `.route-home`).
watchEffect(() => {
  document.documentElement.classList.toggle("route-home", isHome.value);
});

const shouldGate = computed(() => {
  if (!dataRequired.value) return false;
  return loading.value || !!error.value || !summary.value || !qcReport.value;
});
</script>

<template>
  <SiteHeader />
  <StaleBanner v-if="isStale && generatedAt" :generated-at="generatedAt" />
  <template v-if="shouldGate">
    <main>
      <ErrorState v-if="error" :error="error as Error" />
      <LoadingState v-else />
    </main>
  </template>
  <RouterView v-else />
  <SiteFooter v-if="!isHome" />
</template>
