export default function Plate({ caption, credit }) {
  return (
    <figure className="col-span-5 mb-14">
      <div className="aspect-[4/5] bg-clay rounded-panel shadow-lift"></div>
      <figcaption className="mt-3 text-meta uppercase tracking-plate text-ink-soft">
        {caption} — {credit}
      </figcaption>
    </figure>
  );
}
