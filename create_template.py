"""
Run this script once to create a sample input_template.xlsx.

Usage:
    python create_template.py

Then open input_template.xlsx and replace the example rows with your
real company names, report URLs, topics, and rubric definitions.
The schema matches the real Excel format used by the app.
"""

import pandas as pd


def create_template():
    # ── Companies sheet ────────────────────────────────────────────────────────
    # website_url is optional — include it if you want supplementary web content
    companies = pd.DataFrame([
        {
            "company_name": "Acme Corp",
            "report_url":   "https://example.com/acme-sustainability-2023.pdf",
            "website_url":  "https://example.com/sustainability",
        },
        {
            "company_name": "GreenTech Ltd",
            "report_url":   "https://example.com/greentech-esg-2023.pdf",
            "website_url":  "",
        },
    ])

    # ── Topics sheet ───────────────────────────────────────────────────────────
    # topic_id links topics to rubric rows (must match exactly, case-sensitive)
    topics = pd.DataFrame([
        {"topic_id": "T1", "topic_name": "GHG Emissions",    "description": "Scope 1, 2, and 3 greenhouse gas emissions reporting, reduction targets, and net-zero strategy"},
        {"topic_id": "T2", "topic_name": "Renewable Energy", "description": "Transition to clean and renewable electricity across own operations and supply chain"},
        {"topic_id": "T3", "topic_name": "Supply Chain",     "description": "Supplier sustainability standards, audits, and renewable energy commitments from direct suppliers"},
        {"topic_id": "T4", "topic_name": "Water Management", "description": "Water consumption reporting, efficiency targets, and watershed stewardship programs"},
    ])

    # ── Rubric sheet ───────────────────────────────────────────────────────────
    # One row per score level per topic. Scores run 0 (weakest) → 4 (strongest).
    # Add or remove score levels as needed — the parser handles any integer range.
    rubric = pd.DataFrame([
        # T1 — GHG Emissions
        {"topic_id": "T1", "score": 0, "label": "No Disclosure", "definition": "No mention of GHG emissions or climate targets in the report.",                                                       "examples": ""},
        {"topic_id": "T1", "score": 1, "label": "Awareness",     "definition": "Climate change acknowledged but no quantitative emissions data provided.",                                            "examples": "General statement about caring about climate"},
        {"topic_id": "T1", "score": 2, "label": "Developing",    "definition": "Scope 1 and 2 data reported but no Scope 3 coverage or verified targets.",                                           "examples": "Reports total emissions for current year only"},
        {"topic_id": "T1", "score": 3, "label": "Advanced",      "definition": "Scope 1, 2, and 3 reported with reduction targets and year-on-year progress tracking.",                              "examples": "Emissions down X% vs baseline, specific targets set"},
        {"topic_id": "T1", "score": 4, "label": "Leading",       "definition": "All scopes reported, third-party verified, science-based targets, net-zero roadmap with milestones.",               "examples": "SBTi aligned, external assurance, 2030 carbon neutral commitment with interim milestones"},
        # T2 — Renewable Energy
        {"topic_id": "T2", "score": 0, "label": "No Disclosure", "definition": "No mention of renewable energy or clean electricity use.",                                                            "examples": ""},
        {"topic_id": "T2", "score": 1, "label": "Awareness",     "definition": "Renewable energy referenced but no usage data or targets stated.",                                                   "examples": "States intention to use renewables in the future"},
        {"topic_id": "T2", "score": 2, "label": "Developing",    "definition": "Some renewable energy use reported but coverage is partial or limited to HQ.",                                       "examples": "Renewables used for headquarters only"},
        {"topic_id": "T2", "score": 3, "label": "Advanced",      "definition": "High renewable percentage across own operations with active supply chain program.",                                   "examples": "100% renewable for own facilities, supplier clean energy program active"},
        {"topic_id": "T2", "score": 4, "label": "Leading",       "definition": "100% renewable across operations and supply chain, verified data, community energy programs.",                       "examples": "100% clean energy for all manufacturing, Power for Impact or equivalent community program"},
        # T3 — Supply Chain
        {"topic_id": "T3", "score": 0, "label": "No Disclosure", "definition": "No mention of supply chain sustainability or supplier requirements.",                                                 "examples": ""},
        {"topic_id": "T3", "score": 1, "label": "Awareness",     "definition": "Supply chain sustainability mentioned but no program or audit details provided.",                                    "examples": "States that suppliers are expected to comply with standards"},
        {"topic_id": "T3", "score": 2, "label": "Developing",    "definition": "Supplier code of conduct exists with some auditing activity described.",                                             "examples": "Annual supplier audits conducted, basic code of conduct published"},
        {"topic_id": "T3", "score": 3, "label": "Advanced",      "definition": "Quantified supplier commitments tracked and reported with progress data.",                                           "examples": "X suppliers committed to renewables, audit results and corrective actions published"},
        {"topic_id": "T3", "score": 4, "label": "Leading",       "definition": "Verified supplier transition with binding mandates in supplier code and public accountability.",                     "examples": "320+ suppliers committed, renewable energy mandated in Supplier Code of Conduct"},
        # T4 — Water Management
        {"topic_id": "T4", "score": 0, "label": "No Disclosure", "definition": "No mention of water consumption or water management practices.",                                                      "examples": ""},
        {"topic_id": "T4", "score": 1, "label": "Awareness",     "definition": "Water identified as a material issue but no consumption data or targets provided.",                                  "examples": "States that water is an important resource"},
        {"topic_id": "T4", "score": 2, "label": "Developing",    "definition": "Water consumption data reported at corporate level but no reduction targets set.",                                   "examples": "Annual total water use figures disclosed"},
        {"topic_id": "T4", "score": 3, "label": "Advanced",      "definition": "Water data with reduction targets, facility-level reporting, and watershed programmes.",                             "examples": "Water intensity reduction targets, manufacturing site-level data disclosed"},
        {"topic_id": "T4", "score": 4, "label": "Leading",       "definition": "Verified water data, watershed restoration, and community water access initiatives in multiple regions.",            "examples": "Zero waste to landfill achieved; community water programmes in multiple countries"},
    ])

    output_file = "input_template.xlsx"
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        companies.to_excel(writer, sheet_name="companies", index=False)
        topics.to_excel(writer,    sheet_name="topics",    index=False)
        rubric.to_excel(writer,    sheet_name="rubric",    index=False)

    print(f"✓  Created: {output_file}")
    print()
    print("Next steps:")
    print("  1. Open input_template.xlsx")
    print("  2. Replace the example companies and report URLs with your real ones")
    print("  3. Adjust topics and rubric rows — add or remove as needed")
    print("  4. Run the Streamlit app:  streamlit run app.py")


if __name__ == "__main__":
    create_template()
