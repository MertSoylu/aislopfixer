export function Hero() {
  return (
    <section className="hero">
      {/* TODO: wire up real CTA */}
      <h1>Unlock the power of next-level productivity</h1>
      <p>
        revolutionize the way you work and elevate your team to be best-in-class.
      </p>
      <a href="#">Get started</a>
      // aislopfixer: <img> missing alt attribute
      <img src="https://picsum.photos/800/400" />
      <a href="mailto:hello@example.com">Contact sales</a>
    </section>
  );
}
