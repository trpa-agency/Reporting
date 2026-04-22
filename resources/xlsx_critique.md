# Why `2025 Transactions and Allocations Details.xlsx` cannot be the system of record

The file [`data/raw_data/2025 Transactions and Allocations Details.xlsx`](../data/raw_data/2025%20Transactions%20and%20Allocations%20Details.xlsx)
(2,030 rows × 22 columns) is the closest thing we have to a record of
TRPA's development-rights ledger. It is also unusable as one. Every
problem below comes from the current file — the counts are real, the
example strings are real, the consequences are what is happening now.

This is a companion to [`development_tracking.md`](./development_tracking.md),
which proposes the normalized schema that fixes all twelve problems.
This file exists to **communicate the problem** in under ten minutes to a
reader who has never opened the XLSX.

---

## 1. The same fact is spelled seven different ways in the same column.

`TRPA Status` contains **598 rows that all mean "the unit got built"**,
split across seven spellings: `Finaled` (285), `Project Completed` (190),
`Construction Complete` (68), `Project Complete` (29),
`Final Inspection Complete` (14), `Done` (11),
`Project Complete ` with a trailing space (1). No query that filters on
a single status value returns all of them.

**Every status-based count is wrong by default** — there is no version
of this number that is correct unless the analyst already knows all
seven synonyms.

---

## 2. A single cell encodes six separate facts.

The column `Detailed Development Type` has 115 distinct strings. A
typical value is `New Single-Family Residential ADU from Bonus Unit (Achievable)`.
That one cell carries:

- The resulting built form (Single-Family Residential)
- The source bucket the right came from (Bonus Unit)
- Whether it's an ADU (yes)
- The affordability category (Achievable)
- The project name (none here; often present in other rows)
- Whether it's a conversion and between which commodities (none here)

**No user can filter on any one of these six facts independently.**
Answering "how many ADUs were built with bonus units this year" requires
substring-matching five overlapping patterns across a column with 115
spelling variants and hoping nobody used a synonym.

---

## 3. A column name embeds the date of the last update.

The column is literally named `Status Jan 2026`. When anyone asks for a
current status in March, someone adds a `Status Mar 2026` column and
hand-updates 2,030 rows.

**The schema grows by one column every month.** In a year there are
twelve columns named after months, and the person asking a question in
2027 has no way to know which column is current — or whether the
February column was ever updated.

---

## 4. Date values are typed into the status column.

Three rows in `TRPA Status` contain `datetime.datetime(2021, 10, 21, 0, 0)`
— someone typed a date where a status string belongs. These rows crash
any `GROUP BY` on status and silently disappear from any text-based
filter. **There is no way to catch this by eye in a 2,030-row file.**

---

## 5. Commodities leak into the transaction-type column.

`Transaction Type` is supposed to say what *kind of event* this is
(allocation, transfer, conversion). Three of its 14 values aren't event
types at all — they are commodities: `Commercial Floor Area (CFA)`
(28 rows), `Residential Bonus Unit (RBU)` (11),
`Tourist Accommodation Unit (TAU)` (3).

**The column is doing two jobs and failing at both** — any pivot on
transaction type double-counts commodities, and any pivot on commodity
misses 42 rows.

---

## 6. A Unicode typo creates a silent join failure.

One row's `Allocation Number` uses `‐` (U+2010 HYPHEN) instead of `-`
(U+002D HYPHEN-MINUS). The two characters look identical on screen. Any
join from this spreadsheet back to Corral on that column **drops the row
without warning**.

Excel can't see the difference. The analyst can't see the difference.
The stakeholder's count is silently wrong by one, forever, until someone
copies the value into a tool that shows Unicode codepoints.

---

## 7. Trailing whitespace creates duplicate categories.

`Transaction Type` has `Conversion` (17 rows) and `Conversion ` (4 rows,
with a trailing space). To a human reading the file they are the same
value; to Excel, Power BI, pandas, or any SQL engine they are two
distinct categories. **Every pivot on this column reports two rows where
there should be one.**

The same problem repeats in `TRPA Status` (`Project Complete ` vs
`Project Complete`), `Local Status` (`Conditional Permit `),
`Development Right` (`Residential Allocation - CSLT - Town Center Pool `),
and `Local Jurisdiction Project #`.

---

## 8. Project-number fields contain English prose.

`TRPA/MOU Project #` is supposed to be a project identifier. Actual
values include `ERSP2019-0375 plus Revisions` (194 rows carry "plus
Revisions"), `ERSP2020-0080 (Withdrawn)` (9 rows with a parenthetical
status), and `ERSP2018-0030/ERSP2019-0088` (38 slash-joined pairs). The
column mixes an ID, a modification note, a status annotation, and
sometimes two IDs.

**No automated join on this column to Accela will ever work** without a
human-written parser, and any count of "distinct projects" is currently
fiction.

---

## 9. The APN column has three incompatible formats.

Three formats coexist in the same `APN` column: California post-2018
(`###-###-###`, 1,607 rows), Nevada (`####-##-###-###`, 258 rows), and
El Dorado pre-2018 (`###-###-##`, 165 rows).

**Any downstream join on APN has to know about all three formats**, or
it will drop the 165 El Dorado pre-2018 rows without warning. Nothing in
the column itself tells you which format a given row is in. See
[`parcel_genealogy.md`](./parcel_genealogy.md) for why the El Dorado
rows especially are a landmine.

---

## 10. Quantity hides its sign.

`Quantity` uses negative numbers to mean "debit" — 68 rows carry values
like `-1`, `-2`, `-3`, or `-300`. There is no separate column that flags
a debit.

A naive `SUM(Quantity)` silently nets credits against debits (so totals
look small) and a `COUNT` treats every debit as if it were a transaction
of its own. **Neither answer is wrong in an obvious way, and neither is
right.**

---

## 11. One in five rows has no TransactionID.

405 rows (20% of the file) have no `TransactionID`. These are things Ken
tracks that Corral doesn't know about — legitimate off-books movements.
They are also indistinguishable from rows where Ken simply forgot to
fill the ID in.

**There is no mechanism to tell the two cases apart.** Any reconciliation
between the spreadsheet and Corral has to decide, row by row, which 405
rows to ignore.

---

## 12. Two columns answer the same question with different numbers.

`Year Built` and `PM Year Built` are both populated on 1,075 rows. They
disagree on 171 of those rows (16%) — sometimes by 79 years
(`Year Built = 2024, PM Year Built = 1945`). These are two legitimately
different facts (the year TRPA considers the allocation "used" vs. the
year the physical structure was built), but nothing in the spreadsheet
says which one drives the §16.8.2 "Existing bucket" timestamp.

**Whichever column the analyst happens to pick produces a different
report.**

---

## What this means

Any dashboard, query, analyst spreadsheet, or stakeholder report built
on top of this file is quietly working around every one of these twelve
problems. Most of the workarounds live in one person's head.

The point of the proposed schema is not to make the spreadsheet
prettier — it is to put each of these facts in a place where a computer
can filter, count, and join on it without the analyst having to remember
a workaround for every column.

The spreadsheet will keep existing as a capture tool; that's fine. What
has to stop is treating it as the *source of truth* for downstream
reporting. Every critique above is a data-quality bug that **becomes
impossible** the moment the same facts live in a normalized schema with
typed columns, controlled vocabularies, and foreign keys.
