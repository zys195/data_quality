<template>
  <div class="pager">
    <span>{{ from }} - {{ to }} / {{ total }}</span>
    <button class="secondary" :disabled="page <= 1" @click="$emit('update:page', page - 1)">上一页</button>
    <span>{{ page }} / {{ totalPages }}</span>
    <button class="secondary" :disabled="page >= totalPages" @click="$emit('update:page', page + 1)">下一页</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  page: number;
  pageSize?: number;
  total: number;
}>();

defineEmits<{
  'update:page': [value: number];
}>();

const size = computed(() => props.pageSize || 10);
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / size.value)));
const from = computed(() => (props.total === 0 ? 0 : (props.page - 1) * size.value + 1));
const to = computed(() => Math.min(props.page * size.value, props.total));
</script>
