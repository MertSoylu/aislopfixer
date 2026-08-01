import Section from '../../components/Section';
import Card from '../../components/Card';
import Price from '../../components/Price';

const PLANS = [
  { name: 'Starter', price: '$19/mo', features: ['Up to 5 users', 'Basic analytics', 'Email support'] },
  { name: 'Growth', price: '$49/mo', features: ['Up to 5 users', 'Basic analytics', 'Email support'] },
  { name: 'Scale', price: '$99/mo', features: ['Up to 5 users', 'Basic analytics', 'Email support'] },
];

const INCLUDED = [
  { title: 'Unlimited Projects', body: 'Everything you need to run your business in one single place.' },
  { title: 'Priority Support', body: 'Everything you need to run your business in one single place.' },
  { title: 'Advanced Security', body: 'Everything you need to run your business in one single place.' },
  { title: 'Custom Branding', body: 'Everything you need to run your business in one single place.' },
  { title: 'Audit Logs', body: 'Everything you need to run your business in one single place.' },
  { title: 'SLA Guarantee', body: 'Everything you need to run your business in one single place.' },
];

const FAQ = [
  { title: 'Can I cancel anytime?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Do you offer a free trial?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Is my data secure?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Do you support SSO?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'What payment methods?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
  { title: 'Can I change plans?', body: 'Yes, you can cancel your subscription at any time from the dashboard.' },
];

export default function Pricing() {
  return (
    <main className="bg-white">
      <Section>
        <h1 className="text-5xl font-bold text-gray-900 mb-4">
          Everything you need to scale confidently
        </h1>
        <p className="text-xl text-gray-600 mb-8">
          Simple pricing that grows with your team, with no hidden fees at any tier.
        </p>
      </Section>
      <Section>
        <h2 className="text-4xl font-bold text-gray-900 mb-4">Features</h2>
        <div className="grid grid-cols-3 gap-8">
          {INCLUDED.map((item) => (
            <Card key={item.title} title={item.title} body={item.body} />
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
