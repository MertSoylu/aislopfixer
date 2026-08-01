/*
  A survey-firm's site, built the way a lot of real React is: no utility classes
  at all, every style in a `*.module.css` beside the component. The design work
  is in those two files — this one only says which piece of it goes where.
*/
import styles from './page.module.css'
import entry from './entry.module.css'

function Entry({ stamp, title, children, wide }) {
  return (
    <article className={wide ? `${entry.entry} ${entry.wide}` : entry.entry}>
      <p className={entry.stamp}>{stamp}</p>
      <h3>{title}</h3>
      <p>{children}</p>
    </article>
  )
}

export default function Page() {
  return (
    <div className={styles.shell}>
      <nav className={styles.masthead}>
        <span className={styles.wordmark}>Ordnance &amp; Co</span>
        <a href="#colophon">Contact</a>
      </nav>

      <header className={styles.hero}>
        <h1 className={styles.headline}>
          We measure ground that has already been measured badly.
        </h1>
        <p className={styles.standfirst}>
          Mostly boundary disputes, mostly for people who did not expect to be in
          one. About sixty a year, all of them in the north of England.
        </p>
      </header>

      <section className={styles.plate}>
        <img src="/photos/theodolite.jpg" alt="A theodolite set up on a wet field boundary" />
      </section>

      <section className={styles.argument}>
        <h2 className={styles.subhead}>Why the old plan is usually wrong</h2>
        <p>
          A registered title plan is drawn at 1:1250 and its line is half a metre
          wide on the ground. That is not a defect — it was never meant to settle
          where a fence goes — but it is the reason two neighbours can both be
          reading the same document and both be right.
        </p>
        <p>
          What settles it is evidence: the hedge, the ditch, the 1908 conveyance
          with the stone wall in it, and occasionally a photograph of a shed.
        </p>
      </section>

      <section className={styles.work}>
        <h2 className={styles.subhead}>Three from last quarter</h2>
        <div className={styles.workGrid}>
          <Entry stamp="Boundary" title="A ditch that moved">
            The watercourse had been re-cut in the 1970s and everybody had been
            farming to the new line for fifty years. The old line still owned it.
          </Entry>
          <Entry stamp="Party wall" title="Two chimneys, one flue">
            Settled without a surveyor's award, which is the outcome nobody
            advertises because there is no fee in it.
          </Entry>
          <Entry stamp="Topographic" title="Eleven hectares of moor" wide>
            Flown, then walked, because the drone could not see under the
            bracken and the bracken was where the wall was.
          </Entry>
        </div>
      </section>

      <section className={styles.bleed}>
        <p>
          If you have had a letter from a neighbour's solicitor, send us the plan
          before you reply to it.
        </p>
      </section>

      <footer id="colophon" className={styles.colophon}>
        Ordnance &amp; Co, Chartered Land Surveyors, Hexham. Practice no. 4471.
      </footer>
    </div>
  )
}
