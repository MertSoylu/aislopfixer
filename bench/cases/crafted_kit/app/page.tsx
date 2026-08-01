import Feature from '../components/Feature';
import Quote from '../components/Quote';

const LOGOS = ['Northwind', 'Contoso', 'Fabrikam', 'Initech', 'Globex'];

const FEATURES = [
  { title: 'One inbox', body: 'Every channel your customers actually use, landing in the same thread instead of five.', wide: 'Email · SMS · in-app' },
  { title: 'Answers, not tickets', body: 'Drafts written from your own docs, with the passage they came from attached.', wide: 'Grounded replies' },
  { title: 'Handover that sticks', body: 'The context moves with the conversation, so nobody re-asks what was already answered.', wide: 'Shared history' },
  { title: 'Numbers you can act on', body: 'Response times by team and by hour, not one average nobody can do anything with.', wide: 'Reporting' },
];

const QUOTES = [
  { name: 'Ada Kern', role: 'Head of Support, Contoso', words: 'We cut first-response time in half without hiring, which is the only metric our CFO reads.' },
  { name: 'Malik Osei', role: 'CTO, Northwind', words: 'The handover context is the part that surprised us. Nothing gets re-asked any more.' },
];

export default function Home() {
  return (
    <main>
      <section className="mx-auto max-w-6xl px-6 pt-28 pb-24 grid grid-cols-12 gap-x-8">
        <h1 className="col-span-8 text-display text-gray-900 animate-rise">
          Support that reads the room
        </h1>
        <p className="col-span-5 mt-6 text-lede text-gray-600">
          Nomad puts every customer conversation on one timeline and drafts the
          reply from your own documentation.
        </p>
        <div className="col-span-4 col-start-9 mt-6 flex gap-x-4">
          <a className="rounded-full bg-indigo-600 px-6 py-3 text-caption uppercase text-white transition-transform duration-200 ease-settle">
            Start free
          </a>
          <a className="rounded-full border border-gray-200 px-6 py-3 text-caption uppercase text-gray-700 transition-colors duration-150 ease-rise">
            Book a demo
          </a>
        </div>
        <div className="col-span-3 col-start-10 mt-16 animate-drift">
          <div className="aspect-square rounded-xl bg-indigo-50"></div>
        </div>
      </section>
      <section className="mx-auto max-w-6xl px-6 py-10 border-y border-gray-200">
        <ul className="flex justify-between">
          {LOGOS.map((logo) => (
            <li key={logo} className="text-caption uppercase text-gray-400">
              {logo}
            </li>
          ))}
        </ul>
      </section>
      <section className="mx-auto max-w-6xl px-6 py-24 grid grid-cols-12 gap-x-8 gap-y-8">
        <h2 className="col-span-5 text-heading text-gray-900">
          Four things it does, and nothing else
        </h2>
        {FEATURES.map((feature) => (
          <Feature
            key={feature.title}
            title={feature.title}
            body={feature.body}
            wide={feature.wide}
          />
        ))}
      </section>
      <section className="w-screen bg-gray-900 py-28">
        <div className="mx-auto max-w-6xl px-6 grid grid-cols-12 gap-x-8">
          <p className="col-span-7 text-display text-white">
            Nine minutes saved per conversation, measured across 40 000 threads.
          </p>
          <p className="col-span-3 col-start-10 text-body text-gray-400">
            Median across all Nomad accounts in the last quarter, excluding
            automated acknowledgements.
          </p>
        </div>
      </section>
      <section className="mx-auto max-w-6xl px-6 py-24 grid grid-cols-12 gap-x-8">
        <h2 className="col-span-12 text-heading text-gray-900 mb-10">
          What teams say after a quarter
        </h2>
        {QUOTES.map((quote) => (
          <Quote
            key={quote.name}
            name={quote.name}
            role={quote.role}
            words={quote.words}
          />
        ))}
      </section>
      <section className="mx-auto max-w-3xl px-6 py-32 text-center">
        <h2 className="text-display text-gray-900">Try it on one inbox</h2>
        <p className="mt-5 text-lede text-gray-600">
          Connect a single channel and see the difference before you move the
          rest of the team.
        </p>
        <a className="mt-8 inline-block rounded-full bg-indigo-600 px-7 py-3 text-caption uppercase text-white transition-transform duration-200 ease-settle">
          Start free
        </a>
      </section>
    </main>
  );
}
