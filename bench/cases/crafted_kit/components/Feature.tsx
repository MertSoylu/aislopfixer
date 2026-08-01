export default function Feature({ title, body, wide }) {
  return (
    <div className="col-span-4 rounded-xl border border-gray-200 p-8 transition-shadow duration-200 ease-settle hover:shadow-lg">
      <h3 className="text-heading text-gray-900">{title}</h3>
      <p className="mt-3 text-body text-gray-600">{body}</p>
      <span className="mt-6 block text-caption uppercase text-indigo-600">
        {wide}
      </span>
    </div>
  );
}
