export default function Entry({ index, year, title, note }) {
  return (
    <li className="col-span-8 grid grid-cols-12 gap-x-10 gap-y-2 border-t border-rule pt-5 pb-9">
      <span className="col-span-2 text-meta uppercase tracking-plate text-ink-soft">
        {index}
      </span>
      <h3 className="col-span-6 text-title font-serif text-ink">{title}</h3>
      <span className="col-span-4 text-meta text-ink-soft text-right">{year}</span>
      <p className="col-span-7 col-start-3 text-body text-ink-soft">{note}</p>
    </li>
  );
}
