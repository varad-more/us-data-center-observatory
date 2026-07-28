# Goals and outcomes

## The problem

Hyperscale data-centre development happens in public before it is announced. A
parcel assembly, a rezoning application, an air permit for backup generators, a
transmission interconnection request — each is filed with some agency, and each
is a public record.

They are also scattered. County assessors, state utility commissions and federal
environmental databases each publish in their own format, on their own schedule,
under their own access posture. The industry itself publishes almost nothing:
the buying entity is routinely a shell LLC, and the first plain-language
confirmation is often a ribbon-cutting. So the records exist and nobody reads
them together, which means communities, journalists and grid planners hear about
a project after the decisions are made.

## The goal

**Make data-centre development legible from primary public records, early,
without ever inventing what the records do not say.**

The second clause constrains the first. Being early is not difficult if you are
willing to guess — a plausible map of "likely data centres" could be assembled
in a weekend and would be worth nothing, because no reader could tell which
parts to trust. The whole difficulty of this project is being early *and* being
able to show the work. Every hard decision in it has been a trade between reach
and provability, and reach has never won.

## Outcomes

What Helios produces, concretely:

| Outcome | What it means in practice |
|---|---|
| **A published observatory** | Site profiles, timelines, a map and analytics at [varad-more.github.io/project-helios](https://varad-more.github.io/project-helios/) — every figure carrying its assertion class and resolving to the document it came from |
| **An immutable evidence store** | Content-addressed payload bytes with fetch dates. Any published claim traces back to the source bytes, and a new version is minted only when the document genuinely changed |
| **A registry that publishes its own gaps** | Every source Helios reads *and* every source it cannot, with the reason. The absence of a site from Helios is a statement about coverage, never about the world |
| **An explainable score** | Every contribution cites exactly one evidence row. `helios explain AZ-MESA-001` reconstructs the whole chain |
| **A reproducible pipeline** | `make bootstrap` runs offline from recorded fixtures. CI regenerates the published snapshot and proves the committed one is still what the pipeline actually produces |

## The rule that governs all of it

*An inferred value must never be rendered like a reported one.*

Six classes, closed vocabulary: `reported`, `extracted`, `calculated`,
`inferred`, `predicted`, `unknown`. Every genuinely hard question in this
project has been settled by applying that rule literally, and two corollaries
have been earned the hard way:

- **A withdrawn source must not render like a planned one.** "Not built yet"
  and "taken away by the publisher" are different promises to a reader.
- **A declared reason that never reaches a reader is not declared.** Five of six
  access limitations were stored correctly and rendered nowhere; storing the
  explanation is only half of publishing it.

## What success looks like

Testable, and mostly already tested:

1. A reader can tell, on any individual figure, whether a party filed it or
   Helios derived it — without consulting the documentation, and without relying
   on colour alone.
2. Every coverage gap has a name and a stated reason on `/sources`, and the
   coverage summary counts them.
3. The published snapshot regenerates from fixtures in CI, so the deployed site
   is provably a pipeline output rather than a hand-maintained file.
4. No number appears in the API or the UI that Helios cannot source. Substation
   capacity is the standing example: not obtainable, therefore not estimated,
   therefore absent.
5. A site outside the pilot region can be minted correctly, so that national
   coverage is a data problem rather than a code problem.

## Non-goals

- **Operator attribution by inference.** Shell-company signals are review flags,
  never attributions. Helios names sites by project code.
- **Any figure with no obtainable source.** Substation capacity and utilisation
  are the concrete cases; there will be others, and the answer is the same.
- **Completeness.** Helios is an observatory, not a census. Absence of evidence
  is published as a coverage gap, not as a negative finding.
- **Satellite pipelines, commercial data-centre directories, trained ML models,
  Kafka and Kubernetes.** See [ADR 0002](adr/0002-no-kafka-no-kubernetes.md);
  the directories are licence- and provenance-incompatible.

## Using this document

Two questions, and they sort most proposals:

- **Does this make one of the five outcomes truer?** If yes, it is feature work
  and belongs in a plan.
- **Would a reader be misled without it?** If yes, it is cleanup worth doing
  now, whatever its size. A stored-but-unrendered field, a stale status, or a
  status a reader would misread all fail this test, and all three have shipped
  as real bugs in this repository.

Work that answers neither is optional, and should be labelled as such rather
than smuggled in as maintenance.
