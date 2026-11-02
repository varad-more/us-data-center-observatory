# Tableau workbook

`us-data-center-observatory.twbx` presents the observatory dataset in Tableau:
five dashboards over five Hyper extracts, packaged so it opens in Tableau
Desktop or Tableau Public with nothing else on disk.

| Dashboard | What it shows |
|---|---|
| **Where they are** | Every facility OpenStreetMap records, mapped and coloured by what was mapped (building, campus land, point, construction), with headline counts and a by-state breakdown |
| **Power and grid** | LBNL's national electricity total split across mapped buildings by floor area, by state and by county, against each state's bulk transmission (substations ≥ 230 kV) |
| **Through time** | Facilities on the map month by month, for the nation or any state (the Region picker), OpenStreetMap edits by year, and LBNL's reported and projected national electricity |
| **Under construction** | Records mapped as under construction: where, and how much land |
| **About the data** | The assertion classes and what the workbook never claims |

## Reading it

The site's rules hold here too, built into the calculated fields rather than left
to the reader:

- **An unknown is never a zero.** A point record has no area, a region with no
  mapped building has no MW estimate, and a state whose plants are all untagged
  has no capacity figure. Each shows as absent, not as 0.
- **Every MW figure is inferred.** It is a floor-area share of a reported
  national total and an upper bound, never a meter reading, and its caption says
  so.
- **Dates are mapping dates.** OpenStreetMap carries no build dates. The years
  before 2017 are coloured apart because the data-centre tag was still being
  adopted.
- **A removal is "removed from OpenStreetMap"**, never a demolition.

## Rebuilding

The workbook is generated from the committed CSVs, not saved out of Tableau:

```bash
pip install -e ".[tableau]"   # Tableau's Hyper API, for the extracts
make tableau
```

Run it after `make poll` so the workbook carries the same snapshot as the site.
`scripts/observatory/build_tableau_workbook.py` is the source. Each data source
connects to its own extract (Tableau Public accepts only extracts), the
dashboards are laid out in code, and `tests/unit/test_tableau_workbook.py`
checks that every field, formula, zone and window refers to something that
exists.

To publish, open the file in Tableau Public and use **File → Save to Tableau
Public**.
