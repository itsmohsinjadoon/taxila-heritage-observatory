# Generated analytical deliverables

This directory contains only lightweight inspection records in Git. Generated
Word and Excel deliverables are intentionally excluded because they duplicate
versioned tables, figures and narrative source code.

Regenerate the current branded artifacts from the repository root:

```text
python experiments/integrated/analysis/build_experiments_results_discussion.py
node experiments/integrated/analysis/build_results_workbook.mjs
```

The builders produce:

- `Taxila_Heritage_Observatory_Experiments_Results_Discussion.docx`
- `Taxila_Heritage_Observatory_Integrated_Experiments_Results.xlsx`

Do not edit generated binaries as source documents. Update the versioned
analysis code, tables or figures and rebuild them.
