const NAV = ['Product', 'Solutions', 'Pricing', 'Docs', 'Blog'];
const COLUMNS = ['Product', 'Company', 'Legal'];
const LINKS = ['Overview', 'Changelog', 'Support'];

export default function RootLayout({ children }) {
  return (
    <div className="bg-white text-gray-900">
      <header className="mx-auto max-w-6xl px-6 py-6 flex items-center justify-between">
        <a className="text-heading text-gray-900">Nomad</a>
        <ul className="flex gap-x-7">
          {NAV.map((item) => (
            <li key={item} className="text-caption uppercase text-gray-500">
              <a className="transition-colors duration-150 ease-rise hover:text-gray-900">
                {item}
              </a>
            </li>
          ))}
        </ul>
        <a className="rounded-full bg-indigo-600 px-5 py-2 text-caption uppercase text-white transition-transform duration-200 ease-settle">
          Start free
        </a>
      </header>
      {children}
      <footer className="mx-auto max-w-6xl px-6 py-16 grid grid-cols-12 gap-x-8 border-t border-gray-200">
        <p className="col-span-5 text-lede text-gray-800">
          Nomad keeps the parts of your stack that talk to customers in one
          place, so nobody has to guess which dashboard is the real one.
        </p>
        {COLUMNS.map((column) => (
          <div key={column} className="col-span-2">
            <h3 className="text-caption uppercase text-gray-500">{column}</h3>
            <ul className="mt-3">
              {LINKS.map((link) => (
                <li key={link} className="mt-2 text-body text-gray-600">
                  <a className="transition-colors duration-150 ease-rise">{link}</a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </footer>
    </div>
  );
}
