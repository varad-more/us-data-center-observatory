/**
 * Badges that carry epistemic status into the interface.
 *
 * This component is the visual expression of Helios's central product rule: an
 * inferred value must never look like a measured one.
 *
 * The assertion classes are an ordered scale, not a set of categories — reported
 * is the strongest claim Helios can make and predicted the weakest — so they are
 * graded along one sequential ramp rather than given six unrelated hues.
 *
 * Colour is the *last* of three channels that separate them, and on its own it
 * would not be enough:
 *
 *   the word    always rendered. "Inferred" says what the ramp only implies.
 *   the basis   observed claims take a solid edge, derived ones a dashed edge.
 *               This survives greyscale, print and every form of colour
 *               blindness, which is why it is modelled here as data rather than
 *               left to a per-class CSS rule that a restyle could quietly drop.
 *   the ramp    position within the scale, carrying degree.
 */
import type { AssertionClass, ConfidenceBand } from "@/lib/types";

/**
 * How the claim was arrived at, independent of how strong it is.
 *
 * `unestablished` is deliberately not a point on the scale. "Explicitly not
 * established" is a different kind of statement from "weakly established", and
 * collapsing the two is the exact error the assertion vocabulary exists to
 * prevent.
 */
export type EvidenceBasis = "observed" | "derived" | "unestablished";

const ASSERTION_META: Record<
  AssertionClass,
  {
    label: string;
    description: string;
    className: string;
    basis: EvidenceBasis;
  }
> = {
  reported: {
    label: "Reported",
    description:
      "Stated directly by an authoritative source. Helios did not interpret this.",
    className: "badge badge-reported",
    basis: "observed",
  },
  extracted: {
    label: "Extracted",
    description:
      "Read out of a source document by a parser. The exact text is quoted alongside it.",
    className: "badge badge-extracted",
    basis: "observed",
  },
  calculated: {
    label: "Calculated",
    description:
      "Computed deterministically from other stored values, such as a distance between geometries.",
    className: "badge badge-calculated",
    basis: "derived",
  },
  inferred: {
    label: "Inferred",
    description:
      "Concluded from indirect signals. This may be wrong even when every input is correct.",
    className: "badge badge-inferred",
    basis: "derived",
  },
  predicted: {
    label: "Predicted",
    description:
      "Model output about a future or unobserved state. Not an observation.",
    className: "badge badge-predicted",
    basis: "derived",
  },
  unknown: {
    label: "Unknown",
    description:
      "Explicitly not established. This is different from zero and different from not yet examined.",
    className: "badge badge-unknown",
    basis: "unestablished",
  },
};

export function AssertionBadge({ assertion }: { assertion: AssertionClass }) {
  const meta = ASSERTION_META[assertion] ?? ASSERTION_META.unknown;
  return (
    <span
      className={meta.className}
      title={meta.description}
      data-evidence-basis={meta.basis}
      data-testid={`badge-${assertion}`}
    >
      {meta.label}
    </span>
  );
}

const BAND_META: Record<ConfidenceBand, { label: string; className: string }> =
  {
    very_low: { label: "Very low", className: "band band-very-low" },
    low: { label: "Low", className: "band band-low" },
    moderate: { label: "Moderate", className: "band band-moderate" },
    high: { label: "High", className: "band band-high" },
    very_high: { label: "Very high", className: "band band-very-high" },
  };

export function ConfidenceBadge({
  confidence,
  band,
}: {
  confidence: number;
  band: ConfidenceBand;
}) {
  const meta = BAND_META[band] ?? BAND_META.very_low;
  return (
    <span
      className={meta.className}
      title={`Model confidence, not a probability of existence. Band: ${meta.label}.`}
      data-testid="confidence-badge"
    >
      <strong>{confidence.toFixed(0)}%</strong> <span>{meta.label}</span>
    </span>
  );
}

export function StatusPill({
  children,
  tone = "neutral",
  title,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "caution" | "positive" | "negative";
  title?: string;
}) {
  return (
    <span className={`pill pill-${tone}`} title={title}>
      {children}
    </span>
  );
}

/**
 * Renders the operator field.
 *
 * Naming an operator on circumstantial evidence is the single most damaging
 * error this project can make, so the "not established" state is rendered
 * prominently and explained rather than left blank.
 */
export function OperatorStatus({ status }: { status: string }) {
  if (status === "not_established") {
    return (
      <StatusPill
        tone="caution"
        title="Helios does not name an operator unless a direct filing establishes it. Ownership records name the entity holding title, which is frequently a single-purpose company with no stated parent."
      >
        Operator not established
      </StatusPill>
    );
  }
  return <StatusPill tone="neutral">{status}</StatusPill>;
}
