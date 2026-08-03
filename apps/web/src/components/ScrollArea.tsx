/**
 * A horizontally scrolling box that a keyboard can actually reach.
 *
 * The wide tables and charts on this site sit in `overflow-x: auto` containers.
 * A plain `<div>` with overflow is scrollable with a mouse or a finger and, in
 * several of these, reachable by no other means: the chart boxes contain a
 * single `<svg>` and nothing focusable, so a keyboard user could not see the
 * right-hand half of the plot at all. That is WCAG 2.1.1, and it is invisible in
 * every screenshot, which is why it survived a redesign.
 *
 * `tabindex="0"` puts the box in the tab order so the arrow keys scroll it.
 * `role="region"` plus a name is what makes that stop mean something when it is
 * announced — landing on an unnamed generic box mid-document is worse than not
 * stopping. The label is required for the same reason: it is the only thing that
 * tells you what you have just been dropped into.
 *
 * Chrome and Firefox now focus scrollable regions on their own; Safari does not,
 * and the accessible name is ours to supply in every browser.
 */
export function ScrollArea({
  label,
  className,
  children,
}: {
  label: string;
  className: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className} tabIndex={0} role="region" aria-label={label}>
      {children}
    </div>
  );
}
