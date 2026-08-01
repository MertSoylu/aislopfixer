// Generated Next.js landing page. Component-per-section, typed props, clean
// code — and one spacing value, one container, one card shape, one accent, the
// canonical section order. The JSX path has to reach the same verdict as the
// HTML one; if it does not, most real projects would be invisible to the tool.
import type { ReactNode } from "react";

type Feature = { title: string; body: string };

const FEATURES: Feature[] = [
  { title: "Realtime sync", body: "Changes propagate to every client in under fifty milliseconds." },
  { title: "Offline first", body: "Work continues without a connection and merges cleanly on return." },
  { title: "Audit history", body: "Every mutation is recorded with an author, a reason and a timestamp." },
];

const STEPS: Feature[] = [
  { title: "Install", body: "Add the package and point it at your existing database schema." },
  { title: "Model", body: "Describe your entities once and we generate the client and server." },
  { title: "Ship", body: "Deploy to your own infrastructure or to our managed edge runtime." },
];

const QUOTES: Feature[] = [
  { title: "Amara Osei", body: "We replaced four services with this and deleted eleven thousand lines." },
  { title: "Tomas Lindqvist", body: "The offline story is the only one on the market that actually works." },
  { title: "Rin Watanabe", body: "Our mobile team stopped writing sync code entirely, which is the dream." },
];

function Section({ id, tone, children }: { id?: string; tone?: "muted"; children: ReactNode }) {
  return (
    <section id={id} className={`py-20 ${tone === "muted" ? "bg-gray-50" : "bg-white"}`}>
      <div className="max-w-7xl mx-auto px-4 text-center">{children}</div>
    </section>
  );
}

function Card({ title, body }: Feature) {
  return (
    <div className="rounded-2xl border border-gray-200 p-6 shadow-sm">
      <div className="w-12 h-12 rounded-lg bg-indigo-50 mb-4" />
      <h3 className="text-xl font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-gray-600">{body}</p>
    </div>
  );
}

function Grid({ items }: { items: Feature[] }) {
  return (
    <div className="grid md:grid-cols-3 gap-8">
      {items.map((item) => (
        <Card key={item.title} {...item} />
      ))}
    </div>
  );
}

export default function Page() {
  return (
    <main className="bg-white text-gray-900">
      <nav className="border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-16">
          <span className="text-xl font-bold text-gray-900">Tessera</span>
          <a href="#pricing" className="text-sm font-medium text-white bg-indigo-600 rounded-lg px-4 py-2 hover:bg-indigo-700 transition-all duration-300">
            Get Started
          </a>
        </div>
      </nav>

      <Section>
        <h1 className="text-5xl font-bold text-gray-900 mb-6">The data layer your team stops thinking about</h1>
        <p className="text-lg text-gray-600 mb-8">
          Everything you need to keep state consistent across web, mobile and the edge.
        </p>
        <div className="flex items-center justify-center gap-4">
          <a href="#" className="text-white bg-indigo-600 rounded-lg px-6 py-3 shadow-sm hover:bg-indigo-700 transition-all duration-300">Get Started</a>
          <a href="#" className="text-gray-700 border border-gray-200 rounded-lg px-6 py-3 hover:bg-gray-50 transition-all duration-300">Learn more</a>
        </div>
      </Section>

      <Section tone="muted">
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Features</h2>
        <p className="text-lg text-gray-600 mb-12">Powerful tools that scale with your team.</p>
        <Grid items={FEATURES} />
      </Section>

      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">How It Works</h2>
        <p className="text-lg text-gray-600 mb-12">Three steps from schema to production.</p>
        <Grid items={STEPS} />
      </Section>

      <Section tone="muted">
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Testimonials</h2>
        <p className="text-lg text-gray-600 mb-12">What our customers say about working with us.</p>
        <Grid items={QUOTES} />
      </Section>

      <Section id="pricing">
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Pricing</h2>
        <p className="text-lg text-gray-600 mb-12">Simple plans that grow with your team.</p>
        <Grid
          items={[
            { title: "Starter", body: "$0 per month for personal projects and evaluation." },
            { title: "Team", body: "$40 per month per seat with unlimited environments." },
            { title: "Enterprise", body: "Contact sales for on premise deployment and support." },
          ]}
        />
      </Section>

      <Section tone="muted">
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Ready to get started?</h2>
        <p className="text-lg text-gray-600 mb-8">Join thousands of teams building on Tessera today.</p>
        <a href="#" className="text-white bg-indigo-600 rounded-lg px-6 py-3 shadow-sm hover:bg-indigo-700 transition-all duration-300">Get Started</a>
      </Section>

      <footer className="border-t border-gray-200 py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 text-center">
          <p className="text-sm text-gray-500">© 2026 Tessera Labs.</p>
        </div>
      </footer>
    </main>
  );
}
