import Entry from '../../components/Entry';
import Plate from '../../components/Plate';

const BINDINGS = [
  { index: '01', year: '3 weeks', title: 'Coptic, exposed spine', note: 'Opens flat, which matters more than it sounds when the book is meant to be worked in.' },
  { index: '02', year: '5 weeks', title: 'Quarter leather', note: 'Goatskin over cloth. The spine takes the wear, the boards take the light, and both age.' },
  { index: '03', year: '2 weeks', title: 'Japanese stab', note: 'Four holes, waxed linen, no adhesive anywhere in it. The cheapest thing we do properly.' },
  { index: '04', year: '8 weeks', title: 'Full vellum, blind tooled', note: 'Rare, expensive and slow. We take two a year and turn down the rest without apology.' },
];

const PLATES = [
  { caption: 'Sewing frame', credit: 'In use' },
  { caption: 'Backing hammer', credit: 'Sheffield' },
];

export default function Bindery() {
  return (
    <main>
      <header className="wide mx-auto px-8 pt-32 pb-20 grid grid-cols-12 gap-x-10">
        <h1 className="col-span-8 text-plate font-serif text-ink">
          Four bindings, and why we stopped at four
        </h1>
        <p className="col-span-4 col-start-9 text-body text-ink-soft">
          A bindery that offers everything is a bindery that has practised nothing.
          These are the structures we can do without thinking about them.
        </p>
      </header>
      <section className="w-screen bg-moss py-32">
        <div className="wide mx-auto px-8 grid grid-cols-12 gap-x-10">
          <p className="col-span-6 text-lede text-paper measure">
            Everything here is sewn. Nothing is glued at the spine, because glue is a
            decision about how long the book is allowed to last.
          </p>
          <span className="col-span-3 col-start-10 text-meta uppercase tracking-plate text-rule text-right">
            No adhesive spines
          </span>
        </div>
      </section>
      <section className="wide mx-auto px-8 py-28 grid grid-cols-12 gap-x-10">
        <h2 className="col-span-3 text-meta uppercase tracking-plate text-ink-soft">
          Structures
        </h2>
        <ul className="col-span-8 col-start-5 grid grid-cols-12 gap-x-10">
          {BINDINGS.map((binding) => (
            <Entry
              key={binding.index}
              index={binding.index}
              year={binding.year}
              title={binding.title}
              note={binding.note}
            />
          ))}
        </ul>
      </section>
      <section className="wide mx-auto px-8 pb-32 grid grid-cols-12 gap-x-10">
        {PLATES.map((plate) => (
          <Plate key={plate.caption} caption={plate.caption} credit={plate.credit} />
        ))}
        <p className="col-span-2 text-body text-ink-soft">
          Both tools were here before any of us and will outlast the lease.
        </p>
      </section>
    </main>
  );
}
