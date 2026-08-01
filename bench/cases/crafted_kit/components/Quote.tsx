export default function Quote({ name, role, words }) {
  return (
    <figure className="col-span-4 border-l border-gray-200 pl-6 animate-rise">
      <blockquote className="text-lede text-gray-800">{words}</blockquote>
      <figcaption className="mt-4 text-caption uppercase text-gray-500">
        {name} · {role}
      </figcaption>
    </figure>
  );
}
