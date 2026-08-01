export default function Card({ title, body }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 text-center transition-all duration-300 hover:shadow-sm">
      <div className="w-12 h-12 rounded-2xl bg-brand-100 mx-auto mb-4"></div>
      <h3 className="text-xl font-bold text-gray-900 mb-2">{title}</h3>
      <p className="text-base text-gray-600">{body}</p>
    </div>
  );
}
