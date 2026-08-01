<template>
  <section :class="['py-20', muted ? 'bg-gray-50' : 'bg-white']">
    <div class="max-w-7xl mx-auto px-4 text-center">
      <slot />
    </div>
  </section>
</template>

<script setup>
defineProps({ muted: Boolean });
</script>
