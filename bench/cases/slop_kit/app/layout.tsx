const NAV = ['Product', 'Features', 'Pricing', 'Docs', 'Blog', 'Company'];
const COLUMNS = ['Product', 'Company', 'Resources', 'Legal'];
const LINKS = ['Overview', 'Pricing', 'Changelog', 'Support', 'Status'];

export default function RootLayout({ children }) {
  return (
    <div className="bg-white">
      <header className="py-20 bg-white">
        <nav className="max-w-7xl mx-auto px-4 text-center">
          <a className="text-xl font-bold text-gray-900">Acme</a>
          <ul className="grid grid-cols-3 gap-8">
            {NAV.map((item) => (
              <li key={item} className="text-base text-gray-600">
                <a className="text-base text-gray-600 transition-all duration-300">{item}</a>
              </li>
            ))}
          </ul>
          <a className="bg-brand-600 text-white rounded-2xl px-6 py-3 text-base font-bold">
            Get Started
          </a>
        </nav>
      </header>
      {children}
      <footer className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 text-center">
          <div className="grid grid-cols-3 gap-8">
            {COLUMNS.map((column) => (
              <div key={column} className="text-center">
                <h3 className="text-xl font-bold text-gray-900 mb-2">{column}</h3>
                <ul className="text-base text-gray-600">
                  {LINKS.map((link) => (
                    <li key={link} className="text-base text-gray-600 mb-2">
                      <a className="text-base text-gray-600 transition-all duration-300">{link}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-500">© 2026 Acme Inc. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
