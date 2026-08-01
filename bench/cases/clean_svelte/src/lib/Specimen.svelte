<script>
  export let name;
  export let year;
  export let note;
  export let wide = false;
</script>

<article class="rule-top" class:wide class:mark={year < 1960}>
  <p class="caps">{year}</p>
  <h3 class="font-display specimen-name">{name}</h3>
  <p class="specimen-note">{note}</p>
</article>

<style>
  .specimen-name {
    font-size: 1.6875rem;
    line-height: 1.18;
    letter-spacing: -0.02em;
    margin: 0.5rem 0 0.75rem;
  }
  .specimen-note {
    font-size: 1.125rem;
    line-height: 1.65;
    color: var(--color-ink-muted);
    max-width: 52ch;
  }
  .wide .specimen-note {
    font-size: 1.375rem;
    line-height: 1.45;
  }
  .mark .caps {
    color: var(--color-mark);
  }
</style>
