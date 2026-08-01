import Section from '../components/Section';
import Card from '../components/Card';
import Price from '../components/Price';

const LOGOS = ['Northwind', 'Contoso', 'Fabrikam', 'Initech', 'Umbrella', 'Globex'];

const FEATURES = [
  { title: 'Lightning Fast', body: 'Built for speed so your team can ship faster than ever before.' },
  { title: 'Enterprise Ready', body: 'Built for speed so your team can ship faster than ever before.' },
  { title: 'Secure by Default', body: 'Built for speed so your team can ship faster than ever before.' },
  { title: 'Seamless Integration', body: 'Built for speed so your team can ship faster than ever before.' },
  { title: 'Powerful Analytics', body: 'Built for speed so your team can ship faster than ever before.' },
  { title: 'Team Collaboration', body: 'Built for speed so your team can ship faster than ever before.' },
];

const STEPS = [
  { title: 'Step 1', body: 'Connect your data in a single click and let the platform do the rest.' },
  { title: 'Step 2', body: 'Connect your data in a single click and let the platform do the rest.' },
  { title: 'Step 3', body: 'Connect your data in a single click and let the platform do the rest.' },
];

const QUOTES = [
  { title: 'Jane Doe, CTO', body: 'This product completely transformed the way our team works together.' },
  { title: 'John Roe, CEO', body: 'This product completely transformed the way our team works together.' },
  { title: 'Ana Silva, VP', body: 'This product completely transformed the way our team works together.' },
  { title: 'Li Wei, Founder', body: 'This product completely transformed the way our team works together.' },
  { title: 'Sam Poe, Lead', body: 'This product completely transformed the way our team works together.' },
  { title: 'Kim Ora, Head', body: 'This product completely transformed the way our team works together.' },
];

const PLANS = [
  { name: 'Starter', price: '$19/mo', features: ['Up to 5 users', 'Basic analytics', 'Email support'] },
  { name: 'Growth', price: '$49/mo', features: ['Up to 5 users', 'Basic analytics', 'Email support'] },
  { name: 'Scale', price: '$99/mo', features: ['Up to 5 users', 'Basic analytics', 'Email support'] },
];

const FAQ = [
  { title: 'Can I cancel anytime?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Do you offer a free trial?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Is my data secure?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Do you support SSO?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'What payment methods?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Can I change plans?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
];

export default function Home() {
  return (
    <main className="bg-white">
      <Section>
        <h1 className="text-5xl font-bold text-gray-900 mb-4">
          Everything you need to ship faster
        </h1>
        <p className="text-xl text-gray-600 mb-8">
          The all-in-one platform that helps modern teams build, launch and scale
          without the busywork.
        </p>
        <div className="grid grid-cols-3 gap-8">
          <a className="bg-brand-600 text-white rounded-2xl px-6 py-3 text-base font-bold transition-all duration-300">
            Get Started Free
          </a>
          <a className="bg-white text-gray-900 rounded-2xl px-6 py-3 text-base font-bold border border-gray-200 transition-all duration-300">
            Learn More
          </a>
        </div>
        <p className="text-sm text-gray-500">No credit card required</p>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Trusted by teams</h2>
        <div className="grid grid-cols-3 gap-8">
          {LOGOS.map((logo) => (
            <div key={logo} className="text-base text-gray-600 text-center">
              {logo}
            </div>
          ))}
        </div>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Features</h2>
        <p className="text-xl text-gray-600 mb-8">
          Everything you need to run your business in one place.
        </p>
        <div className="grid grid-cols-3 gap-8">
          {FEATURES.map((feature) => (
            <Card key={feature.title} title={feature.title} body={feature.body} />
          ))}
        </div>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">How It Works</h2>
        <div className="grid grid-cols-3 gap-8">
          {STEPS.map((step) => (
            <Card key={step.title} title={step.title} body={step.body} />
          ))}
        </div>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Testimonials</h2>
        <div className="grid grid-cols-3 gap-8">
          {QUOTES.map((quote) => (
            <Card key={quote.title} title={quote.title} body={quote.body} />
          ))}
        </div>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Simple, transparent pricing</h2>
        <div className="grid grid-cols-3 gap-8">
          {PLANS.map((plan) => (
            <Price key={plan.name} name={plan.name} price={plan.price} features={plan.features} />
          ))}
        </div>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Frequently Asked Questions</h2>
        <div className="grid grid-cols-3 gap-8">
          {FAQ.map((item) => (
            <Card key={item.title} title={item.title} body={item.body} />
          ))}
        </div>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Ready to get started?</h2>
        <p className="text-xl text-gray-600 mb-8">
          Join thousands of teams already building with Acme.
        </p>
        <a className="bg-brand-600 text-white rounded-2xl px-6 py-3 text-base font-bold transition-all duration-300">
          Get Started Free
        </a>
      </Section>
    </main>
  );
}
