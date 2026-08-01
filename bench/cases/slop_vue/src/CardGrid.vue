<template>
  <div class="grid md:grid-cols-3 gap-8">
    <Card v-for="item in items" :key="item.title" :title="item.title" :body="item.body" />
  </div>
</template>

<script setup>
import Card from "./Card.vue";
defineProps({ items: Array });
</script>
