# Draft — five confirmations before we build the ledger

**To:** Ken
**From:** Mason
**Subject:** Five confirmations before we build the development-rights ledger

> Draft. Edit freely before sending.

---

Hi Ken,

I'm scoping the v1 build of the development-rights ledger — the SQL model
that'll sit in our SDE-registered DB and drive cumulative accounting
reports. Before we cut any DDL, I want to confirm five things with you.
Each has a proposed answer in brackets; a ✓ or a one-line override is all
I need.

**1. What does "ECM" stand for in `TdrTransactionECMRetirement`?**
My read: *Excess Coverage Mitigation* — retirement of a development right
to offset excess coverage elsewhere. The sending side records
BaileyRating + IPES score, which fits. Correct?
*[proposed: Excess Coverage Mitigation]*

**2. Pool sub-structure inventory.** The cumulative accounting framework
names three CSLT sub-pools (Single-Family, Multi-Family, Town Center).
Are there similar sub-pools for other jurisdictions — or CFA area-plan
sub-pools — that aren't obvious from `dbo.CommodityPool` names? If yes,
is there a list anywhere I can reuse for the `Account` seed load?
*[proposed: just CSLT's three; every other jurisdiction is one pool per commodity]*

**3. MaxCapacity authoritative source.** The 2013 Regional Plan sets
2,600 residential units total — that's clear. What's the authoritative
source for the per-commodity maxima (TAU, CFA sq ft, RBU count, PAOT
pools)?
*[proposed: pull from the 2023 public cumulative accounting report unless you
point me elsewhere]*

**4. ADU modeling.** Corral's `ResidentialAllocationUseType` has only
Single-Family and Multi-Family — no ADU. Should ADUs be modeled as:
- (a) a third use type alongside Single/Multi,
- (b) a flag on an existing SFRUU allocation,
- (c) a separate `Commodity` value ("ADU"),
- (d) something else I haven't thought of?

*[proposed: (c) separate commodity — matches how the annual report already
breaks ADU counts out]*

**5. 2012–2015 existing-development backfill.** For the years Corral's
`AuditLog` doesn't cover (pre-2016), the
`ExistingResidential_2012_2025_unstacked.csv` is the only source we have.
Is that CSV the authoritative baseline you'd stand behind, or is there a
better source I should use?
*[proposed: accept the CSV as `SourceSystem='legacy_seed'` with provenance
flagged on every imported row]*

Happy to grab 30 min by phone if that's faster than email. Blocking the
build on 1, 2, 4, 5 — I can backstop 3 from the public report if I don't
hear back.

Thanks,
Mason
