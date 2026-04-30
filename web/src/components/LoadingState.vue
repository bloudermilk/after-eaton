<template>
  <div class="loading" role="status" aria-live="polite">
    <span class="loading__spinner" aria-hidden="true"></span>
    <span>Loading data…</span>
  </div>
</template>

<style scoped>
.loading {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-6);
  color: var(--color-ink-muted);
  font-size: var(--fs-sm);
}

.loading__spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-rule);
  border-top-color: var(--color-poppy);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .loading__spinner {
    animation: none;
  }
}
</style>
