import Entry from '../../components/Entry';
import Plate from '../../components/Plate';

const RUNS = [
  { index: '1974', year: '250 copies', title: 'The Kadıköy Ferry Timetable', note: 'The first thing printed here, and the only job the studio ever did at a loss on purpose.' },
  { index: '1979', year: '80 copies', title: 'Nine Poems, Unbound', note: 'Loose sheets in a wrapper. The poet wanted them re-orderable and was right about that.' },
  { index: '1986', year: '400 copies', title: 'A Field Guide to Rust', note: 'Six colours, all of them mixed from three. The seventh was attempted and abandoned.' },
  { index: '1993', year: '120 copies', title: 'Letters from the Bindery', note: 'Set entirely in a face we had four of, which decided the line length before the text did.' },
  { index: '2001', year: '600 copies', title: 'Catalogue of Ornament', note: 'Every sort in the cabinet, printed once, at size. Still the reference we reach for.' },
  { index: '2008', year: '45 copies', title: 'Winter Ledger', note: 'Vellum, blind tooled, and the last full leather binding done before the shear was replaced.' },
  { index: '2014', year: '300 copies', title: 'Marginalia', note: 'Printed with the margins deliberately wrong, then reprinted with them wrong the other way.' },
  { index: '2022', year: '150 copies', title: 'Impression Studies', note: 'A book about the bite of type into paper, which is a subject only a press can argue.' },
];

const PLATES = [
  { caption: 'Proof, third state', credit: '1986' },
  { caption: 'Rejected wrapper', credit: '1979' },
  { caption: 'Cabinet, drawer 4', credit: '2001' },
];

export default function Archive() {
  return (
    <main>
      <header className="wide mx-auto px-8 pt-32 pb-16 grid grid-cols-12 gap-x-10">
        <h1 className="col-span-7 text-plate font-serif text-ink">
          Fifty years of short runs
        </h1>
        <p className="col-span-4 col-start-9 text-body text-ink-soft">
          Everything the studio has printed under its own imprint, in the order it
          happened. Copies of most of it are still in the cabinet.
        </p>
      </header>
      <section className="wide mx-auto px-8 pb-24 grid grid-cols-12 gap-x-10">
        {PLATES.map((plate) => (
          <Plate key={plate.caption} caption={plate.caption} credit={plate.credit} />
        ))}
      </section>
      <section className="w-screen bg-clay py-24">
        <div className="wide mx-auto px-8 grid grid-cols-12 gap-x-10">
          <p className="col-span-6 text-lede text-paper measure">
            Nothing here was printed twice. A second edition is a different book and
            deserves a different setting.
          </p>
        </div>
      </section>
      <section className="wide mx-auto px-8 py-28 grid grid-cols-12 gap-x-10">
        <h2 className="col-span-3 text-meta uppercase tracking-plate text-ink-soft">
          The imprint
        </h2>
        <ul className="col-span-8 col-start-5 grid grid-cols-12 gap-x-10">
          {RUNS.map((run) => (
            <Entry
              key={run.index}
              index={run.index}
              year={run.year}
              title={run.title}
              note={run.note}
            />
          ))}
        </ul>
      </section>
    </main>
  );
}
