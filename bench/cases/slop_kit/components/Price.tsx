export default function Price({ name, price, features }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 text-center transition-all duration-300">
      <h3 className="text-xl font-bold text-gray-900 mb-2">{name}</h3>
      <p className="text-4xl font-bold text-gray-900 mb-4">{price}</p>
      <ul className="text-base text-gray-600 mb-6">
        {features.map((f) => (
          <li key={f} className="text-base text-gray-600 mb-2">
            {f}
          </li>
        ))}
      </ul>
      <a className="bg-brand-600 text-white rounded-2xl px-6 py-3 text-base font-bold transition-all duration-300">
        Get Started
      </a>
    </div>
  );
}
