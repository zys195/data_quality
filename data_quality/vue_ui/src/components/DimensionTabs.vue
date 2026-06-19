<template>
  <div class="tabs">
    <button :class="{ active: !modelValue }" @click="$emit('update:modelValue', '')">全部</button>
    <button
      v-for="item in dimensions"
      :key="item.key"
      :class="{ active: modelValue === item.key }"
      @click="$emit('update:modelValue', item.key)"
    >
      {{ item.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { dimensions } from '../labels';

defineProps<{ modelValue: string }>();
defineEmits<{ 'update:modelValue': [value: string] }>();
</script>
