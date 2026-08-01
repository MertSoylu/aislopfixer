/*
  The generated landing page again, this time with styled-components and not a
  single class attribute anywhere. Same six bands in the same order, same
  centred column, same three-up grid, same indigo — only the syntax changed.

  Before the CSS-in-JS reader existed this file measured as eleven empty tags.
*/
import React from 'react'
import styled from 'styled-components'

const Section = styled.section`
  padding: 80px 0;
  background: #ffffff;
`

const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  text-align: center;
`

const Title = styled.h2`
  font-size: 36px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 16px;
  text-align: center;
`

const Lede = styled.p`
  font-size: 18px;
  color: #6b7280;
  margin-bottom: 48px;
  text-align: center;
`

const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 32px;
`

const Card = styled.div`
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  text-align: center;
  transition: all 0.3s ease;
`

const CardTitle = styled.h3`
  font-size: 20px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 16px;
`

const CardText = styled.p`
  font-size: 16px;
  color: #6b7280;
`

const Button = styled.a`
  background: #4f46e5;
  color: #ffffff;
  border-radius: 16px;
  padding: 16px 32px;
  font-size: 16px;
  font-weight: 600;
  transition: all 0.3s ease;
`

export default function App() {
  return (
    <main>
      <Section>
        <Container>
          <Title>Build faster. Ship smarter. Scale effortlessly.</Title>
          <Lede>
            Everything you need to launch your next project, all in one place.
          </Lede>
          <Button href="#pricing">Get Started</Button>
        </Container>
      </Section>

      <Section>
        <Container>
          <Title>Everything you need to succeed</Title>
          <Lede>Powerful features designed to help your team move faster.</Lede>
          <Grid>
            <Card>
              <CardTitle>Lightning Fast</CardTitle>
              <CardText>Blazing fast performance out of the box.</CardText>
            </Card>
            <Card>
              <CardTitle>Enterprise Ready</CardTitle>
              <CardText>Built to scale with your growing business.</CardText>
            </Card>
            <Card>
              <CardTitle>Secure by Default</CardTitle>
              <CardText>Bank-grade security so you can rest easy.</CardText>
            </Card>
          </Grid>
        </Container>
      </Section>

      <Section>
        <Container>
          <Title>Loved by teams everywhere</Title>
          <Lede>Don't just take our word for it.</Lede>
          <Grid>
            <Card>
              <CardTitle>Sarah Johnson</CardTitle>
              <CardText>This product transformed how our team works.</CardText>
            </Card>
            <Card>
              <CardTitle>Michael Chen</CardTitle>
              <CardText>The best investment we made this year.</CardText>
            </Card>
            <Card>
              <CardTitle>Emily Rodriguez</CardTitle>
              <CardText>Incredible support and a seamless experience.</CardText>
            </Card>
          </Grid>
        </Container>
      </Section>

      <Section id="pricing">
        <Container>
          <Title>Simple, transparent pricing</Title>
          <Lede>Choose the plan that's right for you.</Lede>
          <Grid>
            <Card>
              <CardTitle>Starter</CardTitle>
              <CardText>Perfect for individuals getting started.</CardText>
            </Card>
            <Card>
              <CardTitle>Pro</CardTitle>
              <CardText>For growing teams that need more power.</CardText>
            </Card>
            <Card>
              <CardTitle>Enterprise</CardTitle>
              <CardText>Custom solutions for large organizations.</CardText>
            </Card>
          </Grid>
        </Container>
      </Section>

      <Section>
        <Container>
          <Title>Frequently asked questions</Title>
          <Lede>Everything you need to know about the product.</Lede>
          <Grid>
            <Card>
              <CardTitle>Can I cancel anytime?</CardTitle>
              <CardText>Yes, you can cancel your subscription at any time.</CardText>
            </Card>
            <Card>
              <CardTitle>Do you offer refunds?</CardTitle>
              <CardText>We offer a 30-day money-back guarantee.</CardText>
            </Card>
            <Card>
              <CardTitle>Is there a free trial?</CardTitle>
              <CardText>Yes, all plans come with a 14-day free trial.</CardText>
            </Card>
          </Grid>
        </Container>
      </Section>

      <Section>
        <Container>
          <Title>Ready to get started?</Title>
          <Lede>Join thousands of teams already building with us.</Lede>
          <Button href="#pricing">Start Free Trial</Button>
        </Container>
      </Section>
    </main>
  )
}
