<template>
  <header class="site-header">
    <div class="site-header__inner">
      <RouterLink to="/" class="site-header__brand" aria-label="After Eaton — home">
        <span class="site-header__name">After Eaton</span>
      </RouterLink>
    </div>
  </header>
</template>

<style scoped>
.site-header {
  border-bottom: 1px solid var(--color-rule);
  background: linear-gradient(180deg, var(--color-paper) 0%, transparent 100%);
}

.site-header__inner {
  max-width: var(--container-max);
  margin: 0 auto;
  padding: var(--space-4) var(--space-5);
  display: flex;
  align-items: center;
  gap: var(--space-5);
  flex-wrap: wrap;
}

.site-header__brand {
  display: flex;
  align-items: center;
  text-decoration: none;
  color: var(--color-ink);
}
.site-header__brand:hover {
  color: var(--color-poppy);
}

.site-header__name {
  font-family: var(--font-display);
  font-size: var(--fs-lg);
  letter-spacing: 0.01em;
}

@media (max-width: 720px) {
  .site-header__inner {
    padding: var(--space-3) var(--space-4);
  }
}
</style>
