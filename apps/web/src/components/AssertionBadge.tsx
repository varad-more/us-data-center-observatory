/**
 * Badges that carry epistemic status into the interface.
 *
 * This component is the visual expression of Helios's central product rule: an
 * inferred value must never look like a measured one. Each badge has a distinct
 * colour, a tooltip explaining what the class means, and - for the weaker
 * classes - deliberately cautious wording.
 */
import type { AssertionClass, ConfidenceBand } from "@/lib/types";

const ASSERTION_META: Record<
  AssertionClass,
  { label: string; description: string; className: string }
> = {
  reported: {
    label: "Reported",
    description:
      "Stated directly by an authoritative source. Helios did not interpret this.",
    className: "badge badge-reported",
  },
  extracted: {
    label: "Extracted",
    description:
      "Read out of a source document by a parser. The exact text is quoted alongside it.",
    className: "badge badge-extracted",
  },
  calculated: {
    label: "Calculated",
    description:
      "Computed deterministically from other stored values, such as a distance between geometries.",
    className: "badge badge-calculated",
  },
  inferred: {
    label: "Inferred",
    description:
      "Concluded from indirect signals. This may be wrong even when every input is correct.",
    className: "badge badge-inferred",
  },
  predicted: {
    label: "Predicted",
    description: "Model output about a future or unobserved state. Not an observation.",
    className: "badge badge-predicted",
  },
  unknown: {
    label: "Unknown",
    description:
      "Explicitly not established. This is different from zero and different from not yet examined.",
    className: "badge badge-unknown",
  },
};

export function AssertionBadge({ assertion }: { assertion: AssertionClass }) {
  const meta = ASSERTION_META[assertion] ?? ASSERTION_META.unknown;
  return (
    <span className={meta.className} title={meta.description} data-testid={`badge-${assertion}`}>
      {meta.label}
    </span>
  );
}

const BAND_META: Record<ConfidenceBand, { label: string; className: string }> = {
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
