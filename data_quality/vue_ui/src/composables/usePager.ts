import { computed, ref, watch } from 'vue';

export function usePager(pageSize = 10) {
  const page = ref(1);

  function reset() {
    page.value = 1;
  }

  function setPage(value: number) {
    page.value = Math.max(1, Math.floor(value || 1));
  }

  function paginate<T>(items: T[]) {
    const total = items.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const current = Math.min(page.value, totalPages);
    if (current !== page.value) {
      page.value = current;
    }
    const start = (current - 1) * pageSize;
    const slice = computed(() => items.slice(start, start + pageSize));
    return { page, total, totalPages, start, slice };
  }

  return { page, pageSize, setPage, reset, paginate };
}
