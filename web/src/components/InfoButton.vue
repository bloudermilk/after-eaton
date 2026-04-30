<script setup lang="ts">
import { ref, useTemplateRef } from "vue";

const props = defineProps<{
  title: string;
}>();

const dialog = useTemplateRef<HTMLDialogElement>("dialog");
const isOpen = ref(false);

function open() {
  dialog.value?.showModal();
  isOpen.value = true;
}

function close() {
  dialog.value?.close();
  isOpen.value = false;
}

function onBackdropClick(event: MouseEvent) {
  // Native <dialog> backdrop click target is the dialog itself; child
  // clicks bubble up. Only close when the user clicks outside the content.
  if (event.target === dialog.value) close();
}
</script>

<template>
  <button type="button" class="info-btn" :aria-label="`About: ${props.title}`" @click="open">
    <span aria-hidden="true">i</span>
  </button>
  <dialog ref="dialog" class="info-dialog" @click="onBackdropClick" @cancel="isOpen = false">
    <article class="info-dialog__inner" @click.stop>
      <header class="info-dialog__head">
        <h2>{{ props.title }}</h2>
        <button type="button" class="info-dialog__close" aria-label="Close" @click="close">
          ×
        </button>
      </header>
      <div class="info-dialog__body">
        <slot />
      </div>
    </article>
  </dialog>
</template>

<style scoped>
.info-btn {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-rule);
  background: transparent;
  color: var(--color-ink-muted);
  border-radius: 50%;
  font-family: var(--font-display);
  font-size: 13px;
  line-height: 1;
  padding: 0;
}
.info-btn:hover {
  border-color: var(--color-poppy);
  color: var(--color-poppy);
}

.info-dialog {
  border: none;
  padding: 0;
  background: transparent;
  max-width: min(560px, 92vw);
  width: 100%;
  color: var(--color-ink);
}
.info-dialog::backdrop {
  background: rgba(42, 42, 42, 0.45);
}

.info-dialog__inner {
  background: var(--color-paper);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-5) var(--space-6);
  box-shadow: var(--shadow-card);
}

.info-dialog__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}
.info-dialog__head h2 {
  margin: 0;
  font-size: var(--fs-lg);
}

.info-dialog__close {
  background: transparent;
  border: none;
  font-size: 28px;
  line-height: 1;
  color: var(--color-ink-muted);
  padding: 0 var(--space-2);
}
.info-dialog__close:hover {
  color: var(--color-poppy);
}

.info-dialog__body {
  margin-top: var(--space-3);
  font-size: var(--fs-sm);
  color: var(--color-ink);
}
.info-dialog__body :deep(p) {
  margin: 0 0 var(--space-3);
}
.info-dialog__body :deep(p:last-child) {
  margin-bottom: 0;
}
</style>
