<!--
  The clean twin of slop_vue: a single-file-component project that was designed.
  Named tokens instead of palette shades, four band rhythms, three measures, an
  asymmetric catalogue grid, left-aligned headings everywhere, one full-bleed
  break, and copy whose lengths differ because the sentences differ.

  It also exercises the dialect the tool has to read: `class:` directives, an
  `{#each}` loop over a real array, and a component that carries its own
  `<style>`. If the engine cannot separate this from slop_vue, it is measuring
  Svelte, not design.
-->
<script>
  import Specimen from "$lib/Specimen.svelte";
  import "../app.css";

  const SPECIMENS = [
    { name: "Grotesque No. 9", year: 1906, note: "Cut for tram timetables, which is why the digits are narrower than the caps. We reissued it because nothing modern survives being set at six point on a wet platform sign." },
    { name: "Pellworm", year: 1974, note: "A shipping-forecast face. Two weights, no italic, and a comma the size of a thumbprint." },
    { name: "Arbour", year: 2019, note: "Our own. Drawn for long reading on bad screens: tall x-height, shallow contrast, and a period you can find at a glance." },
    { name: "Kestrel Mono", year: 1988, note: "Rescued from a plotter driver. The zero has a slash and we are not taking questions about it." },
  ];

  let dense = false;
</script>

<nav class="border-b border-[var(--color-rule)]">
  <div class="mx-auto max-w-[78rem] px-7 flex items-baseline justify-between h-[4rem]">
    <span class="font-display text-[1.375rem] tracking-[-0.03em]">Kern &amp; Sons</span>
    <div class="flex items-baseline gap-9">
      <a href="#catalogue" class="control text-[0.9375rem] text-[var(--color-ink-muted)]">Catalogue</a>
      <a href="#press" class="control text-[0.9375rem] text-[var(--color-ink-muted)]">The press</a>
      <a href="#licence" class="control text-[0.9375rem] text-[var(--color-signal)] underline underline-offset-[6px]">Licensing</a>
    </div>
  </div>
</nav>

<header class="pt-[9rem] pb-[4rem]">
  <div class="mx-auto max-w-[78rem] px-7 grid md:grid-cols-12 gap-x-9">
    <h1 class="md:col-span-8 font-display text-[3.75rem] leading-[0.92] tracking-[-0.03em]">
      Four hundred metal faces, eleven of them worth digitising.
    </h1>
    <p class="md:col-span-3 md:col-start-10 self-end text-[1.125rem] leading-[1.65] text-[var(--color-ink-muted)] max-w-[38ch]">
      A foundry in a former print works in Leipzig. We cut new type slowly and
      reissue old type only when the original was solving a problem that still exists.
    </p>
  </div>
</header>

<section class="pb-[5.5rem]">
  <figure class="w-screen relative left-1/2 -translate-x-1/2">
    <img src="/media/press.avif" alt="A Heidelberg cylinder press mid-run" class="w-full h-[30rem] object-cover">
    <figcaption class="mx-auto max-w-[78rem] px-7 pt-4 caps">
      The 1957 cylinder, still pulling proofs every Thursday.
    </figcaption>
  </figure>
</section>

<section id="catalogue" class="py-[5.5rem] bg-[var(--color-shell)]">
  <div class="mx-auto max-w-[78rem] px-7">
    <h2 class="font-display text-[2.375rem] leading-[1.05] tracking-[-0.025em] mb-3">Catalogue</h2>
    <p class="text-[1.125rem] leading-[1.65] text-[var(--color-ink-muted)] max-w-[52ch] mb-[3.5rem]">
      Eleven families, priced per weight. Trials are unlimited and unwatermarked;
      we would rather you found out early that a face is wrong for you.
    </p>

    <div class="grid md:grid-cols-12 gap-x-9 gap-y-[4rem]" class:dense>
      {#each SPECIMENS as item, i}
        <div class:md:col-span-7={i === 0} class="md:col-span-5">
          <Specimen name={item.name} year={item.year} note={item.note} wide={i === 0} />
        </div>
      {/each}
    </div>
  </div>
</section>

<section id="press" class="py-[9rem]">
  <div class="mx-auto max-w-[58rem] px-7">
    <h2 class="font-display text-[2.375rem] leading-[1.05] tracking-[-0.025em] mb-9">What the press is for</h2>
    <div class="grid md:grid-cols-2 gap-x-[3.5rem] gap-y-[2rem] text-[1.125rem] leading-[1.7] text-[var(--color-ink-muted)]">
      <p>
        Every face we sell has been printed on paper before it has been sold as a file.
        Screens forgive a lot; a cylinder press forgives nothing, and the flaws it finds
        are the ones that show up later at fourteen point.
      </p>
      <p>
        We keep the press because it settles arguments.
      </p>
      <p>
        The digitisations are drawn from the proofs, not from scans of printed specimens.
        A scan carries the ink spread of one particular day, and that spread is not a
        property of the letter.
      </p>
      <p>
        Nothing in the catalogue is generated, interpolated or auto-hinted. Eleven
        families in nineteen years is the honest rate.
      </p>
    </div>
  </div>
</section>

<section id="licence" class="py-[3.25rem] bg-[var(--color-ink)] text-[var(--color-paper)]">
  <div class="mx-auto max-w-[78rem] px-7 grid md:grid-cols-12 gap-x-9 items-end">
    <h2 class="md:col-span-7 font-display text-[2.75rem] leading-[1.0] tracking-[-0.03em]">
      Licences are per foundry, not per seat.
    </h2>
    <p class="md:col-span-4 md:col-start-9 text-[1.125rem] leading-[1.65]">
      <a href="mailto:setting@kernandsons.de" class="control underline underline-offset-[6px]">setting@kernandsons.de</a><br>
      Leipzig, Thursdays only.
    </p>
  </div>
</section>

<footer class="py-[2rem] border-t border-[var(--color-rule)]">
  <div class="mx-auto max-w-[78rem] px-7 flex justify-between caps">
    <span>Kern &amp; Sons GmbH</span>
    <span>Set in Lyon Text and Untitled Sans</span>
  </div>
</footer>
