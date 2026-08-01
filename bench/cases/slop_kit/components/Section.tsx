export default function Section({ children }) {
  return (
    <section className="py-20 bg-white">
      <div className="max-w-7xl mx-auto px-4 text-center">{children}</div>
    </section>
  );
}
