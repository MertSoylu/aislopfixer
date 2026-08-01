const ROOMS = ['Letterpress', 'Bindery', 'Type foundry', 'Archive'];
const CONTACT = ['Sudurgu Sk. 14, Kadıköy', 'Weekdays 10.00–18.00', 'studio@marbling.press'];

export default function RootLayout({ children }) {
  return (
    <div className="bg-paper font-serif text-ink">
      <nav className="wide mx-auto px-8 pt-7 pb-5 grid grid-cols-12 gap-x-10 items-baseline">
        <a className="col-span-3 text-title font-serif text-ink">Marbling Press</a>
        <ul className="col-span-6 col-start-6 flex gap-x-8">
          {ROOMS.map((room) => (
            <li key={room} className="text-meta uppercase tracking-plate text-ink-soft">
              <a className="text-meta text-ink-soft transition-colors duration-150 ease-plate">
                {room}
              </a>
            </li>
          ))}
        </ul>
        <a className="col-span-2 text-meta uppercase tracking-plate text-clay text-right">
          Visit
        </a>
      </nav>
      {children}
      <footer className="wide mx-auto px-8 pt-16 pb-24 grid grid-cols-12 gap-x-10 rule">
        <p className="col-span-5 text-lede font-serif text-ink">
          We set type by hand because the hand leaves marks a grid cannot.
        </p>
        <ul className="col-span-3 col-start-8">
          {CONTACT.map((line) => (
            <li key={line} className="text-body text-ink-soft mb-1">
              {line}
            </li>
          ))}
        </ul>
        <span className="col-span-2 text-meta uppercase tracking-plate text-ink-soft text-right">
          Est. 1974
        </span>
      </footer>
    </div>
  );
}
