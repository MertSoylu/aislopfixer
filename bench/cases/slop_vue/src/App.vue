<!--
  The same generated landing page again, as a Vue single-file component tree.
  Nothing here is written badly: props are typed, the template is componentised,
  the loops are real loops. It is still one spacing value, one container, one
  card shape, one accent and the canonical section order — and the Vue path has
  to reach the same verdict as the HTML and JSX ones.
-->
<template>
  <main class="bg-white text-gray-900">
    <nav class="border-b border-gray-200">
      <div class="max-w-7xl mx-auto px-4 flex items-center justify-between h-16">
        <span class="text-xl font-bold text-gray-900">Tessera</span>
        <a href="#pricing" class="text-sm font-medium text-white bg-indigo-600 rounded-lg px-4 py-2 hover:bg-indigo-700 transition-all duration-300">Get Started</a>
      </div>
    </nav>

    <Section>
      <h1 class="text-5xl font-bold text-gray-900 mb-6">The data layer your team stops thinking about</h1>
      <p class="text-lg text-gray-600 mb-8">Everything you need to keep state consistent across web, mobile and the edge.</p>
      <div class="flex items-center justify-center gap-4">
        <a href="#" class="text-white bg-indigo-600 rounded-lg px-6 py-3 shadow-sm hover:bg-indigo-700 transition-all duration-300">Get Started</a>
        <a href="#" class="text-gray-700 border border-gray-200 rounded-lg px-6 py-3 hover:bg-gray-50 transition-all duration-300">Learn more</a>
      </div>
    </Section>

    <Section muted>
      <h2 class="text-4xl font-bold text-gray-900 mb-4">Features</h2>
      <p class="text-lg text-gray-600 mb-12">Powerful tools that scale with your team.</p>
      <CardGrid :items="FEATURES" />
    </Section>

    <Section>
      <h2 class="text-4xl font-bold text-gray-900 mb-4">How It Works</h2>
      <p class="text-lg text-gray-600 mb-12">Three steps from schema to production.</p>
      <CardGrid :items="STEPS" />
    </Section>

    <Section muted>
      <h2 class="text-4xl font-bold text-gray-900 mb-4">Testimonials</h2>
      <p class="text-lg text-gray-600 mb-12">What our customers say about working with us.</p>
      <CardGrid :items="QUOTES" />
    </Section>

    <Section>
      <h2 class="text-4xl font-bold text-gray-900 mb-4">Pricing</h2>
      <p class="text-lg text-gray-600 mb-12">Simple plans that grow with your team.</p>
      <CardGrid :items="PLANS" />
    </Section>

    <Section muted>
      <h2 class="text-4xl font-bold text-gray-900 mb-4">Ready to get started?</h2>
      <p class="text-lg text-gray-600 mb-8">Join thousands of teams building on Tessera today.</p>
      <a href="#" class="text-white bg-indigo-600 rounded-lg px-6 py-3 shadow-sm hover:bg-indigo-700 transition-all duration-300">Get Started</a>
    </Section>

    <footer class="border-t border-gray-200 py-20 bg-white">
      <div class="max-w-7xl mx-auto px-4 text-center">
        <p class="text-sm text-gray-500">© 2026 Tessera Labs.</p>
      </div>
    </footer>
  </main>
</template>

<script setup>
import Section from "./Section.vue";
import CardGrid from "./CardGrid.vue";

const FEATURES = [
  { title: "Realtime sync", body: "Changes propagate to every client in under fifty milliseconds." },
  { title: "Offline first", body: "Work continues without a connection and merges cleanly on return." },
  { title: "Audit history", body: "Every mutation is recorded with an author, a reason and a timestamp." },
];

const STEPS = [
  { title: "Install", body: "Add the package and point it at your existing database schema." },
  { title: "Model", body: "Describe your entities once and we generate the client and server." },
  { title: "Ship", body: "Deploy to your own infrastructure or to our managed edge runtime." },
];

const QUOTES = [
  { title: "Amara Osei", body: "We replaced four services with this and deleted eleven thousand lines." },
  { title: "Tomas Lindqvist", body: "The offline story is the only one on the market that actually works." },
  { title: "Rin Watanabe", body: "Our mobile team stopped writing sync code entirely, which is the dream." },
];

const PLANS = [
  { title: "Starter", body: "$0 per month for personal projects and evaluation." },
  { title: "Team", body: "$40 per month per seat with unlimited environments." },
  { title: "Enterprise", body: "Contact sales for on premise deployment and support." },
];
</script>
