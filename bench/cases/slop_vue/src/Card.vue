<template>
  <div class="rounded-2xl border border-gray-200 p-6 shadow-sm">
    <div class="w-12 h-12 rounded-lg bg-indigo-50 mb-4"></div>
    <h3 class="text-xl font-semibold text-gray-900 mb-2">{{ title }}</h3>
    <p class="text-gray-600">{{ body }}</p>
  </div>
</template>

<script setup>
defineProps({ title: String, body: String });
</script>
