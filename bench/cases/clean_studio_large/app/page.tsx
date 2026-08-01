import Entry from '../components/Entry';
import Plate from '../components/Plate';

const PRESSES = [
  { index: '01', year: '1974', title: 'Heidelberg Windmill', note: 'Bought secondhand from a shuttered newspaper in Bursa; it still throws ink when the room is cold.' },
  { index: '02', year: '1981', title: 'Vandercook No. 4', note: 'Proof press. Slow, forgiving, and the only machine here anyone is allowed to learn on.' },
  { index: '03', year: '1996', title: 'Stanhope Iron Hand', note: 'A gift. Two people are needed to pull one impression, which is the point of keeping it.' },
  { index: '04', year: '2011', title: 'Guillotine, restored', note: 'Rebuilt over four winters. The blade is the original; everything that holds it is not.' },
  { index: '05', year: '2019', title: 'Polymer platemaker', note: 'The one concession to the century. It makes lead affordable again for short runs.' },
  { index: '06', year: '1958', title: 'Ludlow slug caster', note: 'Runs twice a year, for posters, and fills the room with a smell nobody has agreed to describe.' },
  { index: '07', year: '2003', title: 'Board shear', note: 'German, heavy, and square to a tenth of a millimetre after a morning of adjustment.' },
  { index: '08', year: '1989', title: 'Nipping press', note: 'Does one job. Does it for as long as the sheet needs, which is usually longer than expected.' },
];

const PLATES = [
  { caption: 'Bodoni, 48pt', credit: 'Cast 1968' },
  { caption: 'Wood type, condensed', credit: 'Unattributed' },
  { caption: 'Ornament sorts', credit: 'Hamilton' },
  { caption: 'Brass rule, 6pt', credit: 'Shop-made' },
];

const NOTES = [
  { index: 'i', year: 'Paper', title: 'Cotton rag, 300gsm', note: 'Milled in Amalfi. It takes a deep bite and dries to a colour photographs never quite get.' },
  { index: 'ii', year: 'Ink', title: 'Oil-based, mixed here', note: 'Every colour on this page was mixed on a slab by someone who then had to clean the slab.' },
  { index: 'iii', year: 'Type', title: 'Lead and polymer', note: 'Lead for the display sizes, polymer for text. Nobody can tell, and that is the argument for it.' },
  { index: 'iv', year: 'Thread', title: 'Waxed linen, 18/3', note: 'Bought in bulk once, in 1998, and there is still enough of it to outlive the current lease.' },
  { index: 'v', year: 'Time', title: 'Four days a sheet', note: 'Two for the press, one for the ink to stop moving, one for someone to decide it is finished.' },
];

export default function Home() {
  return (
    <main>
      <header className="plate">
        <div className="wide mx-auto px-8 grid grid-cols-12 gap-x-10">
          <h1 className="col-span-9 text-plate font-serif text-ink">
            A press that leaves marks
          </h1>
          <p className="col-span-5 col-start-2 mt-8 text-lede text-ink-soft measure">
            Five machines, one room, and about four hundred kilos of lead. We print
            in short runs for people who want the impression to show.
          </p>
          <a className="col-span-3 col-start-10 mt-8 text-meta uppercase tracking-plate text-clay rounded-pill border border-rule px-5 py-3 transition-colors duration-150 ease-plate">
            Book the bindery
          </a>
        </div>
      </header>
      <section className="wide mx-auto px-8 py-28 grid grid-cols-12 gap-x-10">
        <h2 className="col-span-3 text-meta uppercase tracking-plate text-ink-soft">
          The machines
        </h2>
        <ul className="col-span-8 col-start-5 grid grid-cols-12 gap-x-10">
          {PRESSES.map((press) => (
            <Entry
              key={press.index}
              index={press.index}
              year={press.year}
              title={press.title}
              note={press.note}
            />
          ))}
        </ul>
      </section>
      <section className="w-screen bg-ink py-40">
        <div className="wide mx-auto px-8 grid grid-cols-12 gap-x-10">
          <blockquote className="col-span-7 text-title font-serif text-paper">
            “The impression is the record of a force. Flatten it and you are printing
            a picture of printing.”
          </blockquote>
          <cite className="col-span-3 col-start-9 text-meta uppercase tracking-plate text-rule">
            Selma Arat, foreman
          </cite>
        </div>
      </section>
      <section className="wide mx-auto px-8 py-24 grid grid-cols-12 gap-x-10">
        {PLATES.map((plate) => (
          <Plate key={plate.caption} caption={plate.caption} credit={plate.credit} />
        ))}
      </section>
      <section className="wide mx-auto px-8 pb-36 grid grid-cols-12 gap-x-10">
        <h2 className="col-span-4 text-title font-serif text-ink">
          What goes into a sheet
        </h2>
        <ul className="col-span-8 grid grid-cols-12 gap-x-10">
          {NOTES.map((note) => (
            <Entry
              key={note.index}
              index={note.index}
              year={note.year}
              title={note.title}
              note={note.note}
            />
          ))}
        </ul>
      </section>
    </main>
  );
}
